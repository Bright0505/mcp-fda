"""GraphRAGStore 抽象介面 — 定義圖譜資料的讀寫操作。"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class GraphRAGStore(ABC):
    """可插拔的 GraphRAG 儲存後端抽象介面。

    實作此介面以支援不同的儲存後端（SQLite / PostgreSQL）。
    所有方法皆為 async，呼叫端不需知道底層實作。
    """

    @abstractmethod
    async def initialize(self) -> None:
        """建立資料表（CREATE TABLE IF NOT EXISTS）並執行初始設定。"""

    @abstractmethod
    async def close(self) -> None:
        """關閉連線並釋放資源。"""

    @abstractmethod
    async def check_cache(self, name_norm: str) -> Optional[str]:
        """確認 FDA 查詢快取狀態。

        Returns:
            'skip'     — TTL 內已成功查詢，可略過
            'not_found'— FDA 查無此藥，不需重試
            None       — 需重新查詢（未快取或已過期）
        """

    @abstractmethod
    async def upsert_fetch_log(
        self,
        name_norm: str,
        status: str,
        http_code: Optional[int] = None,
        error_message: Optional[str] = None,
        interaction_count: int = 0,
    ) -> None:
        """更新或插入 FDA 查詢追蹤記錄。"""

    @abstractmethod
    async def upsert_entity(
        self,
        generic_name: str,
        display_name_cn: Optional[str] = None,
        permit_number: Optional[str] = None,
        in_whitelist: bool = False,
        source: str = "fda",
        openfda: Optional[dict] = None,
        brand_names: Optional[List[str]] = None,
    ) -> int:
        """Upsert 藥品實體，回傳 entity_id。"""

    @abstractmethod
    async def get_entity_id(self, name_norm: str) -> Optional[int]:
        """依正規化名稱查詢 entity_id，不存在回傳 None。"""

    @abstractmethod
    async def get_entity_ids(
        self, name_norms: List[str]
    ) -> Dict[str, Optional[int]]:
        """批次查詢多個正規化名稱的 entity_id。"""

    @abstractmethod
    async def insert_interaction(
        self,
        drug_1_id: int,
        drug_2_name: str,
        drug_2_id: Optional[int],
        relation: str,
        severity: str,
        description_id: str,
        evidence_snippet: str,
    ) -> None:
        """插入一筆交互作用關係。"""

    @abstractmethod
    async def graph_query(
        self,
        entity_ids: List[int],
        severity_filter: Optional[str] = None,
    ) -> List[dict]:
        """雙向圖譜查詢：回傳與指定實體有交互作用的所有記錄。

        Args:
            entity_ids: graphrag_drug_entities 的 entity_id 列表
            severity_filter: None/'all'/'major'/'moderate+'

        Returns:
            List of dicts with keys:
              drug_1, drug_1_cn, drug_2, drug_2_cn, drug_2_in_whitelist,
              relation, severity, evidence_snippet, description_id, extracted_at
        """
