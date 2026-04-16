"""FDA API 客戶端 — 查詢 drug label 並處理錯誤與重試。"""

import logging
from typing import Optional
from urllib.parse import quote

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from graphrag.config import GraphRAGConfig

logger = logging.getLogger(__name__)


class FDANotFoundError(Exception):
    """藥品名在 FDA 查無資料。"""


class FDAServiceError(Exception):
    """FDA API 服務異常（5xx / 網路錯誤）。"""


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, FDAServiceError):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    return False


@retry(
    retry=retry_if_exception_type((FDAServiceError, httpx.TransportError)),
    stop=stop_after_attempt(GraphRAGConfig.FDA_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
async def fetch_label(generic_name: str) -> dict:
    """向 FDA API 查詢藥品 label，回傳 results[0]。

    Args:
        generic_name: 英文 generic name（來自 drug_permits.name_en）

    Returns:
        FDA results[0] dict，包含 drug_interactions 等欄位

    Raises:
        FDANotFoundError: 404 或 0 結果
        FDAServiceError: 5xx 或網路錯誤
    """
    encoded = quote(f'"{generic_name}"')
    # _exists_:drug_interactions 過濾掉只有 warnings 但無 interactions 欄位的 OTC label，
    # 避免 ok_no_interactions 快取遮蔽後續有用的 label
    url = (
        f"{GraphRAGConfig.FDA_API_BASE}/drug/label.json"
        f"?search=openfda.generic_name:{encoded}+AND+_exists_:drug_interactions&limit=1"
    )

    logger.info(f"FDA 查詢: {generic_name}")

    async with httpx.AsyncClient(timeout=GraphRAGConfig.FDA_TIMEOUT) as client:
        try:
            resp = await client.get(url)
        except httpx.TransportError as e:
            raise httpx.TransportError(f"FDA 網路錯誤: {e}") from e

        if resp.status_code == 404:
            raise FDANotFoundError(f"FDA 無此藥品資料: {generic_name}")

        if resp.status_code == 429:
            raise FDAServiceError(f"FDA API 流量限制 (429): {generic_name}")

        if resp.status_code >= 500:
            raise FDAServiceError(f"FDA 服務異常 ({resp.status_code}): {generic_name}")

        if 400 <= resp.status_code < 500:
            # 4xx 是永久性錯誤（查詢格式錯誤或查無資料），不應重試
            raise FDANotFoundError(f"FDA 無效查詢 ({resp.status_code}): {generic_name}")

        if resp.status_code != 200:
            raise FDAServiceError(f"FDA 非預期回應 ({resp.status_code}): {generic_name}")

        data = resp.json()
        results = data.get("results", [])
        if not results:
            raise FDANotFoundError(f"FDA 回傳 0 筆結果: {generic_name}")

        logger.info(f"FDA 查詢成功: {generic_name}")
        return results[0]


def extract_interaction_text(fda_result: dict) -> Optional[str]:
    """從 FDA label result 取出 drug_interactions 文字。

    FDA 的 drug_interactions 是 list[str]，合併為單一字串。
    """
    interactions = fda_result.get("drug_interactions", [])
    if not interactions:
        return None
    return " ".join(interactions).strip()


def extract_openfda_section(fda_result: dict) -> dict:
    """取出 openfda metadata section。"""
    return fda_result.get("openfda", {})
