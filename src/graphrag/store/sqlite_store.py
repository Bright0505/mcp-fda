"""SQLite GraphRAG 儲存後端（預設）。

使用 aiosqlite 非同步驅動，零外部服務依賴。
資料庫路徑由 GRAPHRAG_SQLITE_PATH 控制（預設 ./data/graphrag.db，相對於
執行時的工作目錄——本機開發解析成 repo 根目錄下的 data/，Docker 因為
WORKDIR 是 /app，解析成 /app/data/，跟 docker-compose.yml 掛的
mcp_fda_data volume 對齊）。
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import aiosqlite

from graphrag.store.base import GraphRAGStore

logger = logging.getLogger(__name__)

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS graphrag_drug_entities (
    entity_id          INTEGER PRIMARY KEY,
    generic_name_norm  TEXT NOT NULL UNIQUE,
    generic_name       TEXT NOT NULL,
    display_name_cn    TEXT,
    brand_names        TEXT,
    link_permit_number TEXT,
    in_local_whitelist INTEGER NOT NULL DEFAULT 0,
    source             TEXT NOT NULL DEFAULT 'fda',
    raw_openfda        TEXT,
    fetched_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_ge_permit ON graphrag_drug_entities (link_permit_number);
CREATE INDEX IF NOT EXISTS idx_ge_wl     ON graphrag_drug_entities (in_local_whitelist);

CREATE TABLE IF NOT EXISTS graphrag_drug_interactions (
    interaction_id   INTEGER PRIMARY KEY,
    drug_1_id        INTEGER NOT NULL REFERENCES graphrag_drug_entities(entity_id) ON DELETE CASCADE,
    drug_2_name      TEXT NOT NULL,
    drug_2_id        INTEGER REFERENCES graphrag_drug_entities(entity_id),
    relation         TEXT NOT NULL,
    severity         TEXT,
    description_id   TEXT NOT NULL,
    evidence_snippet TEXT,
    extracted_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_gi_d1  ON graphrag_drug_interactions (drug_1_id);
CREATE INDEX IF NOT EXISTS idx_gi_d2  ON graphrag_drug_interactions (drug_2_id);
CREATE INDEX IF NOT EXISTS idx_gi_sev ON graphrag_drug_interactions (severity);

CREATE TABLE IF NOT EXISTS graphrag_fetch_log (
    generic_name_norm TEXT PRIMARY KEY,
    last_fetched_at   TEXT,
    status            TEXT NOT NULL DEFAULT 'pending',
    http_code         INTEGER,
    error_message     TEXT,
    interaction_count INTEGER DEFAULT 0,
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_SEVERITY_ORDER = "CASE severity WHEN 'major' THEN 1 WHEN 'moderate' THEN 2 WHEN 'minor' THEN 3 ELSE 4 END"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteGraphRAGStore(GraphRAGStore):
    """SQLite 實作，每個連線使用 WAL journal mode 提升讀寫並行能力。"""

    def __init__(self) -> None:
        self._path = os.getenv("GRAPHRAG_SQLITE_PATH", "./data/graphrag.db")
        self._conn: Optional[aiosqlite.Connection] = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            db_path = Path(self._path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(str(db_path))
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    async def initialize(self) -> None:
        conn = await self._get_conn()
        await conn.executescript(_SQLITE_SCHEMA)
        await conn.commit()
        logger.info(f"SQLite GraphRAG DB 初始化完成: {self._path}")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def check_cache(self, name_norm: str) -> Optional[str]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT status, last_fetched_at FROM graphrag_fetch_log WHERE generic_name_norm = ?",
            (name_norm,),
        ) as cur:
            row = await cur.fetchone()

        if row is None:
            return None

        status = row["status"]
        if status == "not_found":
            return "not_found"

        if status == "ok" and row["last_fetched_at"]:
            try:
                fetched = datetime.fromisoformat(row["last_fetched_at"])
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=timezone.utc)
                ttl_days = int(os.getenv("FDA_CACHE_TTL_DAYS", "30"))
                if datetime.now(timezone.utc) - fetched < timedelta(days=ttl_days):
                    return "skip"
            except ValueError:
                pass

        return None

    async def upsert_fetch_log(
        self,
        name_norm: str,
        status: str,
        http_code: Optional[int] = None,
        error_message: Optional[str] = None,
        interaction_count: int = 0,
    ) -> None:
        conn = await self._get_conn()
        await conn.execute(
            """
            INSERT INTO graphrag_fetch_log
                (generic_name_norm, last_fetched_at, status, http_code, error_message,
                 interaction_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(generic_name_norm) DO UPDATE SET
                last_fetched_at   = excluded.last_fetched_at,
                status            = excluded.status,
                http_code         = excluded.http_code,
                error_message     = excluded.error_message,
                interaction_count = excluded.interaction_count,
                updated_at        = excluded.updated_at
            """,
            (name_norm, _now_iso(), status, http_code, error_message, interaction_count, _now_iso()),
        )
        await conn.commit()

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
        from graphrag.name_resolver import normalize
        norm = normalize(generic_name)
        brand_json = json.dumps(brand_names or [])
        openfda_json = json.dumps(openfda) if openfda else None
        wl_int = 1 if in_whitelist else 0

        conn = await self._get_conn()
        await conn.execute(
            """
            INSERT INTO graphrag_drug_entities
                (generic_name_norm, generic_name, display_name_cn, brand_names,
                 link_permit_number, in_local_whitelist, source, raw_openfda, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(generic_name_norm) DO UPDATE SET
                generic_name       = excluded.generic_name,
                display_name_cn    = COALESCE(excluded.display_name_cn, display_name_cn),
                brand_names        = excluded.brand_names,
                link_permit_number = COALESCE(excluded.link_permit_number, link_permit_number),
                in_local_whitelist = MAX(in_local_whitelist, excluded.in_local_whitelist),
                source = CASE
                    WHEN source = 'local' AND excluded.source = 'fda' THEN 'both'
                    WHEN source = 'fda'   AND excluded.source = 'local' THEN 'both'
                    ELSE excluded.source
                END,
                raw_openfda = COALESCE(excluded.raw_openfda, raw_openfda),
                fetched_at  = excluded.fetched_at
            """,
            (norm, generic_name, display_name_cn, brand_json,
             permit_number, wl_int, source, openfda_json, _now_iso()),
        )
        await conn.commit()

        async with conn.execute(
            "SELECT entity_id FROM graphrag_drug_entities WHERE generic_name_norm = ?",
            (norm,),
        ) as cur:
            row = await cur.fetchone()
        return row["entity_id"]

    async def get_entity_id(self, name_norm: str) -> Optional[int]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT entity_id FROM graphrag_drug_entities WHERE generic_name_norm = ?",
            (name_norm,),
        ) as cur:
            row = await cur.fetchone()
        return row["entity_id"] if row else None

    async def get_entity_ids(self, name_norms: List[str]) -> Dict[str, Optional[int]]:
        if not name_norms:
            return {}
        mapping: Dict[str, Optional[int]] = {n: None for n in name_norms}
        placeholders = ",".join(["?"] * len(name_norms))
        conn = await self._get_conn()
        async with conn.execute(
            f"SELECT entity_id, generic_name_norm FROM graphrag_drug_entities WHERE generic_name_norm IN ({placeholders})",
            name_norms,
        ) as cur:
            async for row in cur:
                mapping[row["generic_name_norm"]] = row["entity_id"]
        return mapping

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
        conn = await self._get_conn()
        await conn.execute(
            """
            INSERT INTO graphrag_drug_interactions
                (drug_1_id, drug_2_name, drug_2_id, relation, severity,
                 description_id, evidence_snippet, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (drug_1_id, drug_2_name, drug_2_id, relation, severity,
             description_id, evidence_snippet[:500], _now_iso()),
        )
        await conn.commit()

    async def graph_query(
        self,
        entity_ids: List[int],
        severity_filter: Optional[str] = None,
    ) -> List[dict]:
        if not entity_ids:
            return []

        placeholders = ",".join(["?"] * len(entity_ids))
        severity_clause = ""
        if severity_filter == "major":
            severity_clause = "AND i.severity = 'major'"
        elif severity_filter == "moderate+":
            severity_clause = "AND i.severity IN ('major', 'moderate')"

        sql = f"""
            SELECT
                e1.generic_name       AS drug_1,
                e1.display_name_cn    AS drug_1_cn,
                i.drug_2_name         AS drug_2,
                e2.display_name_cn    AS drug_2_cn,
                e2.in_local_whitelist AS drug_2_in_whitelist,
                i.relation,
                i.severity,
                i.evidence_snippet,
                i.description_id,
                i.extracted_at
            FROM graphrag_drug_interactions i
            JOIN graphrag_drug_entities e1 ON e1.entity_id = i.drug_1_id
            LEFT JOIN graphrag_drug_entities e2 ON e2.entity_id = i.drug_2_id
            WHERE (i.drug_1_id IN ({placeholders}) OR i.drug_2_id IN ({placeholders}))
            {severity_clause}
            ORDER BY {_SEVERITY_ORDER}, i.extracted_at DESC
            LIMIT 50
        """

        params = entity_ids + entity_ids
        conn = await self._get_conn()
        results = []
        async with conn.execute(sql, params) as cur:
            async for row in cur:
                results.append(dict(row))
        return results
