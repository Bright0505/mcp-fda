"""ingestion.py 單元測試。"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── openai（extractor 用）
_openai_stub = types.ModuleType("openai")
_openai_stub.AsyncOpenAI = MagicMock
sys.modules.setdefault("openai", _openai_stub)

# ─── graphrag.extractor（各測試直接 patch extract_interactions）
_extractor_stub = types.ModuleType("graphrag.extractor")
_extractor_stub.extract_interactions = AsyncMock(return_value=[])
sys.modules["graphrag.extractor"] = _extractor_stub

# ─── graphrag.store.base
_store_base_stub = types.ModuleType("graphrag.store.base")


class _FakeStore:
    pass


_store_base_stub.GraphRAGStore = _FakeStore
sys.modules.setdefault("graphrag.store", types.ModuleType("graphrag.store"))
sys.modules["graphrag.store.base"] = _store_base_stub

import graphrag.ingestion  # noqa: E402
from graphrag.ingestion import ingest_drug  # noqa: E402
from graphrag.fda_client import FDANotFoundError  # noqa: E402


# ─── 快取命中 ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_drug_cache_hit():
    """cache 命中時不調用 FDA，直接回 cached。"""
    store = MagicMock()
    store.check_cache = AsyncMock(return_value="skip")

    with patch("graphrag.ingestion.fetch_label") as mock_fetch:
        result = await ingest_drug("acetaminophen", store=store, db_manager=None)

    mock_fetch.assert_not_called()
    assert result["status"] == "cached"
    assert result["interaction_count"] == 0


# ─── FDA 查無（not_found）────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_drug_not_found():
    """FDA 404 → status=not_found，寫 fetch_log。"""
    store = MagicMock()
    store.check_cache = AsyncMock(return_value=None)
    store.upsert_fetch_log = AsyncMock()

    with patch("graphrag.ingestion.fetch_label", side_effect=FDANotFoundError("404")):
        result = await ingest_drug("unknown_xyz", store=store, db_manager=None)

    assert result["status"] == "not_found"
    store.upsert_fetch_log.assert_called_once()
    assert store.upsert_fetch_log.call_args[0][1] == "not_found"


# ─── FDA 有 drug_interactions → 寫入圖譜 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_drug_with_interactions():
    """fda_result 有 drug_interactions → 呼叫 extractor + 寫 store（無 ChromaDB）。"""
    fda_result = {
        "drug_interactions": ["Do not take with warfarin."],
        "openfda": {"brand_name": ["Tylenol"], "generic_name": ["ACETAMINOPHEN"]},
    }
    extracted = [
        {
            "drug_1": "ACETAMINOPHEN",
            "drug_2": "Warfarin",
            "relation": "monitor_closely",
            "severity": "moderate",
            "evidence": "May increase anticoagulant effect.",
        }
    ]

    store = MagicMock()
    store.check_cache = AsyncMock(return_value=None)
    store.upsert_entity = AsyncMock(return_value=1)
    store.get_entity_id = AsyncMock(return_value=None)
    store.upsert_fetch_log = AsyncMock()
    store.insert_interaction = AsyncMock()

    with (
        patch("graphrag.ingestion.fetch_label", return_value=fda_result),
        patch("graphrag.ingestion.extract_interactions", return_value=extracted),
        patch("graphrag.ingestion.get_whitelist_sample", return_value=[]),
    ):
        result = await ingest_drug(
            "ACETAMINOPHEN",
            store=store,
            db_manager=None,
            in_whitelist=True,
        )

    assert result["status"] == "ok"
    assert result["interaction_count"] == 1
    store.insert_interaction.assert_called_once()


# ─── FDA label 無 drug_interactions 欄位 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_drug_no_interactions_field():
    """fda_result 無 drug_interactions → ok_no_interactions，不呼叫 extractor。"""
    fda_result = {
        "warnings": ["Severe liver damage warning."],
        "openfda": {},
    }

    store = MagicMock()
    store.check_cache = AsyncMock(return_value=None)
    store.upsert_entity = AsyncMock(return_value=1)
    store.upsert_fetch_log = AsyncMock()

    with (
        patch("graphrag.ingestion.fetch_label", return_value=fda_result),
        patch("graphrag.ingestion.extract_interactions") as mock_extract,
    ):
        result = await ingest_drug("ACETAMINOPHEN", store=store, db_manager=None)

    assert result["status"] == "ok_no_interactions"
    mock_extract.assert_not_called()


# ─── force_refresh 跳過快取 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_drug_force_refresh():
    """force_refresh=True 應跳過 cache，直接呼叫 FDA。"""
    fda_result = {
        "drug_interactions": ["Avoid with alcohol."],
        "openfda": {},
    }

    store = MagicMock()
    store.upsert_entity = AsyncMock(return_value=1)
    store.upsert_fetch_log = AsyncMock()
    store.get_entity_id = AsyncMock(return_value=None)
    store.insert_interaction = AsyncMock()

    with (
        patch("graphrag.ingestion.fetch_label", return_value=fda_result) as mock_fetch,
        patch("graphrag.ingestion.extract_interactions", return_value=[]),
        patch("graphrag.ingestion.get_whitelist_sample", return_value=[]),
    ):
        result = await ingest_drug(
            "ALCOHOL", store=store, db_manager=None, force_refresh=True
        )

    mock_fetch.assert_called_once()
    store.check_cache.assert_not_called()
