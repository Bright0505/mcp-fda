"""fda_client.py 單元測試。"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from graphrag.fda_client import (
    FDANotFoundError,
    FDAServiceError,
    fetch_label,
    extract_interaction_text,
    extract_openfda_section,
)


# ─── URL 格式驗證 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_label_url_contains_exists_filter():
    """fetch_label 的 URL 必須包含 _exists_:drug_interactions 過濾。"""
    captured_url = []

    async def mock_get(url, **kwargs):
        captured_url.append(url)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = {
            "results": [{"drug_interactions": ["Do not take with alcohol."], "openfda": {}}]
        }
        return resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await fetch_label("ACETAMINOPHEN")

    assert captured_url, "未發出 HTTP 請求"
    url = captured_url[0]
    assert "_exists_:drug_interactions" in url, (
        f"URL 缺少 _exists_:drug_interactions 過濾：{url}"
    )
    assert "ACETAMINOPHEN" in url.upper()


# ─── 正常回傳 ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_label_success():
    payload = {
        "results": [{
            "drug_interactions": ["Do not use with MAOIs."],
            "openfda": {"generic_name": ["ACETAMINOPHEN"], "brand_name": ["Tylenol"]},
        }]
    }

    async def mock_get(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = payload
        return resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_label("ACETAMINOPHEN")

    assert result["drug_interactions"] == ["Do not use with MAOIs."]


# ─── 404 → FDANotFoundError ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_label_404_raises_not_found():
    async def mock_get(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 404
        return resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(FDANotFoundError):
            await fetch_label("UNKNOWN_DRUG_XYZ")


# ─── 0 results → FDANotFoundError ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_label_empty_results_raises_not_found():
    async def mock_get(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = {"results": []}
        return resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(FDANotFoundError):
            await fetch_label("NONEXISTENT")


# ─── 5xx → FDAServiceError ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_label_500_raises_service_error():
    async def mock_get(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 500
        return resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(FDAServiceError):
            await fetch_label("WARFARIN")


# ─── extract helpers ─────────────────────────────────────────────────────────


def test_extract_interaction_text_present():
    result = {"drug_interactions": ["Do not use with alcohol.", "Avoid MAOIs."]}
    text = extract_interaction_text(result)
    assert "alcohol" in text
    assert "MAOI" in text


def test_extract_interaction_text_missing():
    assert extract_interaction_text({}) is None
    assert extract_interaction_text({"drug_interactions": []}) is None


def test_extract_openfda_section():
    result = {"openfda": {"generic_name": ["WARFARIN"]}, "other": "ignored"}
    assert extract_openfda_section(result) == {"generic_name": ["WARFARIN"]}


def test_extract_openfda_section_missing():
    assert extract_openfda_section({}) == {}
