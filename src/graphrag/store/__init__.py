"""GraphRAGStore factory — 依環境變數選擇儲存後端。"""

import logging
import os
from typing import Optional

from graphrag.store.base import GraphRAGStore

logger = logging.getLogger(__name__)

_store: Optional[GraphRAGStore] = None


async def get_store() -> GraphRAGStore:
    """取得（或初始化）GraphRAGStore 單例。

    依 GRAPHRAG_DB_TYPE 環境變數選擇後端：
    - 'sqlite'      （預設）→ SQLiteGraphRAGStore，儲存於 GRAPHRAG_SQLITE_PATH
    - 'postgresql'  → PostgreSQLGraphRAGStore，使用 GRAPHRAG_PG_* 環境變數
    """
    global _store
    if _store is None:
        db_type = os.getenv("GRAPHRAG_DB_TYPE", "sqlite").lower()

        if db_type == "postgresql":
            from graphrag.store.postgres_store import PostgreSQLGraphRAGStore
            _store = PostgreSQLGraphRAGStore()
            logger.info("GraphRAGStore: PostgreSQL 模式")
        else:
            from graphrag.store.sqlite_store import SQLiteGraphRAGStore
            _store = SQLiteGraphRAGStore()
            logger.info("GraphRAGStore: SQLite 模式（預設）")

        await _store.initialize()

    return _store


async def close_store() -> None:
    """關閉現有 store 連線（適用於測試或 graceful shutdown）。"""
    global _store
    if _store is not None:
        await _store.close()
        _store = None
