"""name_resolver.py 單元測試。"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from graphrag.name_resolver import (
    normalize,
    split_ingredients,
    _is_ascii_name,
    resolve_drug_names,
)


# ─── split_ingredients ────────────────────────────────────────────────────────


def test_split_ingredients_single():
    assert split_ingredients("ACETAMINOPHEN") == ["ACETAMINOPHEN"]


def test_split_ingredients_with_eq_to():
    result = split_ingredients("ACETAMINOPHEN (EQ TO PARACETAMOL)")
    assert result == ["ACETAMINOPHEN"]


def test_split_ingredients_multi():
    mi = "ACETAMINOPHEN (EQ TO PARACETAMOL);;CAFFEINE ANHYDROUS"
    assert split_ingredients(mi) == ["ACETAMINOPHEN", "CAFFEINE ANHYDROUS"]


def test_split_ingredients_case_insensitive_eq_to():
    result = split_ingredients("Ibuprofen (eq to Ibuprofen acid);;Pseudoephedrine HCL")
    assert result == ["IBUPROFEN", "PSEUDOEPHEDRINE HCL"]


def test_split_ingredients_dedup():
    mi = "ASPIRIN;;ASPIRIN (EQ TO SALICYLATE)"
    assert split_ingredients(mi) == ["ASPIRIN"]


def test_split_ingredients_empty_segment():
    mi = ";;ACETAMINOPHEN;;"
    result = split_ingredients(mi)
    assert result == ["ACETAMINOPHEN"]


def test_split_ingredients_empty_string():
    assert split_ingredients("") == []


# ─── _is_ascii_name ───────────────────────────────────────────────────────────


def test_is_ascii_english():
    assert _is_ascii_name("ACETAMINOPHEN") is True


def test_is_ascii_with_spaces():
    assert _is_ascii_name("Caffeine Anhydrous") is True


def test_is_ascii_chinese():
    assert _is_ascii_name("斯斯解痛錠") is False


def test_is_ascii_mixed():
    assert _is_ascii_name("Acetaminophen 乙醯胺酚") is False


# ─── resolve_drug_names ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_english_returns_uppercase_ingredient():
    result = await resolve_drug_names(["ACETAMINOPHEN", "Warfarin"])
    assert result["ACETAMINOPHEN"]["ingredients"] == ["ACETAMINOPHEN"]
    assert result["Warfarin"]["ingredients"] == ["WARFARIN"]
    assert result["ACETAMINOPHEN"]["in_whitelist"] is False


@pytest.mark.asyncio
async def test_resolve_chinese_returns_empty_ingredients():
    result = await resolve_drug_names(["斯斯解痛錠"])
    assert result["斯斯解痛錠"]["ingredients"] == []
    assert result["斯斯解痛錠"]["in_whitelist"] is False


@pytest.mark.asyncio
async def test_resolve_db_manager_ignored():
    """db_manager 傳入任何值均被忽略，英文名稱照常解析。"""
    db = MagicMock()
    db.execute_query_async = AsyncMock(side_effect=RuntimeError("should not be called"))
    result = await resolve_drug_names(["ASPIRIN"], db)
    db.execute_query_async.assert_not_called()
    assert result["ASPIRIN"]["ingredients"] == ["ASPIRIN"]


@pytest.mark.asyncio
async def test_resolve_multiple_mixed():
    """英文與中文混合輸入：英文有 ingredients，中文為空。"""
    result = await resolve_drug_names(["warfarin", "普拿疼"])
    assert result["warfarin"]["ingredients"] == ["WARFARIN"]
    assert result["普拿疼"]["ingredients"] == []


@pytest.mark.asyncio
async def test_resolve_query_name_uppercase():
    result = await resolve_drug_names(["aspirin"])
    assert result["aspirin"]["query_name"] == "ASPIRIN"
