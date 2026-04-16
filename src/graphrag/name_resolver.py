"""藥品名稱正規化 — 接受英文通用名稱（不依賴內部 DB）。"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# main_ingredients 多成分分隔符
_INGREDIENT_SEP = ";;"
# 去除 (EQ TO ...) 或 (eq to ...) 後綴
_EQ_TO_RE = re.compile(r"\s*\(eq\s+to\b[^)]*\)", re.IGNORECASE)


def normalize(name: str) -> str:
    """正規化藥名：lower + strip。"""
    return name.lower().strip()


def split_ingredients(main_ingredients: str) -> List[str]:
    """從多成分字串拆出個別成分名（大寫、去 EQ TO 後綴）。

    範例:
        "ACETAMINOPHEN (EQ TO PARACETAMOL);;CAFFEINE ANHYDROUS"
        → ["ACETAMINOPHEN", "CAFFEINE ANHYDROUS"]
    """
    seen: set = set()
    result: List[str] = []
    for raw in main_ingredients.split(_INGREDIENT_SEP):
        cleaned = _EQ_TO_RE.sub("", raw).strip()
        key = cleaned.upper()
        if key and key not in seen:
            seen.add(key)
            result.append(cleaned.upper())
    return result


def _is_ascii_name(name: str) -> bool:
    """判斷是否為英文名稱（ASCII 範圍）。"""
    return all(ord(c) < 128 for c in name)


def _default_entry(name: str) -> dict:
    """回傳 resolve_drug_names 的預設結構。"""
    if _is_ascii_name(name):
        ing = [name.upper()]
        qname = name.upper()
    else:
        ing = []
        qname = name
    return {
        "ingredients": ing,
        "permits": [],
        "in_whitelist": False,
        "ambiguous": False,
        "permit_number": None,
        "name_cn": None,
        "name_en": name if _is_ascii_name(name) else None,
        "query_name": qname,
    }


async def resolve_drug_names(
    drug_names: List[str],
    db_manager: Any = None,
) -> Dict[str, dict]:
    """將輸入藥名正規化，僅接受英文通用名稱。

    此版本不依賴內部資料庫。中文藥名無法解析，會回傳空 ingredients。

    Args:
        drug_names: 用戶輸入的藥名列表（僅支援英文通用名稱）
        db_manager: 保留參數以維持介面相容，傳入任何值均被忽略

    Returns:
        dict，key=輸入名，value=resolve schema
    """
    result: Dict[str, dict] = {}

    for name in drug_names:
        if not _is_ascii_name(name):
            logger.warning(
                f"藥名 '{name}' 包含非 ASCII 字元，此版本僅支援英文通用名稱，已略過"
            )
        result[name] = _default_entry(name)

    return result


async def get_whitelist_sample(db_manager: Any = None, limit: int = 200) -> List[str]:
    """此版本不依賴 DB，回傳空列表。"""
    return []
