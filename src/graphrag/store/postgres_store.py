"""PostgreSQL GraphRAG 儲存後端（可選）。

使用 asyncpg 連線池，連線至獨立 PostgreSQL。
啟用條件：GRAPHRAG_DB_TYPE=postgresql

必要環境變數：
    GRAPHRAG_PG_HOST, GRAPHRAG_PG_PORT, GRAPHRAG_PG_NAME,
    GRAPHRAG_PG_USER, GRAPHRAG_PG_PASSWORD
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import asyncpg

from graphrag.store.base import GraphRAGStore

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = """
    CASE i.severity
        WHEN 'major'    THEN 1
        WHEN 'moderate' THEN 2
        WHEN 'minor'    THEN 3
        ELSE 4
    END
"""


def _require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"GRAPHRAG_DB_TYPE=postgresql 時必須設定環境變數 {key}"
        )
    return val


class PostgreSQLGraphRAGStore(GraphRAGStore):
    """asyncpg 實作，使用獨立 PostgreSQL。"""

    def __init__(self) -> None:
        self._pool: Optional[asyncpg.Pool] = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=_require_env("GRAPHRAG_PG_HOST"),
                port=int(os.getenv("GRAPHRAG_PG_PORT", "5432")),
                database=_require_env("GRAPHRAG_PG_NAME"),
                user=_require_env("GRAPHRAG_PG_USER"),
                password=_require_env("GRAPHRAG_PG_PASSWORD"),
                min_size=1,
                max_size=5,
            )
            logger.info("PostgreSQL GraphRAGStore 連線池建立完成")
        return self._pool

    async def initialize(self) -> None:
        schema_file = Path(__file__).parent.parent.parent.parent / "schema" / "graphrag_schema.sql"
        if not schema_file.exists():
            raise FileNotFoundError(f"找不到 GraphRAG schema 檔案: {schema_file}")

        sql = schema_file.read_text(encoding="utf-8")
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(sql)
        logger.info("PostgreSQL GraphRAG 資料表初始化完成")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def check_cache(self, name_norm: str) -> Optional[str]:
        from datetime import timedelta, timezone, datetime
        pool = await self._get_pool()
        row = await pool.fetchrow(
            "SELECT status, last_fetched_at FROM graphrag_fetch_log WHERE generic_name_norm = $1",
            name_norm,
        )
        if row is None:
            return None

        status = row["status"]
        if status == "not_found":
            return "not_found"

        if status == "ok" and row["last_fetched_at"]:
            fetched = row["last_fetched_at"]
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            ttl_days = int(os.getenv("FDA_CACHE_TTL_DAYS", "30"))
            if datetime.now(timezone.utc) - fetched < timedelta(days=ttl_days):
                return "skip"

        return None

    async def upsert_fetch_log(
        self,
        name_norm: str,
        status: str,
        http_code: Optional[int] = None,
        error_message: Optional[str] = None,
        interaction_count: int = 0,
    ) -> None:
        pool = await self._get_pool()
        await pool.execute(
            """
            INSERT INTO graphrag_fetch_log
                (generic_name_norm, last_fetched_at, status, http_code, error_message,
                 interaction_count, updated_at)
            VALUES ($1, NOW(), $2, $3, $4, $5, NOW())
            ON CONFLICT (generic_name_norm) DO UPDATE SET
                last_fetched_at   = EXCLUDED.last_fetched_at,
                status            = EXCLUDED.status,
                http_code         = EXCLUDED.http_code,
                error_message     = EXCLUDED.error_message,
                interaction_count = EXCLUDED.interaction_count,
                updated_at        = NOW()
            """,
            name_norm, status, http_code, error_message, interaction_count,
        )

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
        openfda_json = json.dumps(openfda) if openfda else None

        pool = await self._get_pool()
        row = await pool.fetchrow(
            """
            INSERT INTO graphrag_drug_entities
                (generic_name_norm, generic_name, display_name_cn, brand_names,
                 link_permit_number, in_local_whitelist, source, raw_openfda, fetched_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW())
            ON CONFLICT (generic_name_norm) DO UPDATE SET
                generic_name       = EXCLUDED.generic_name,
                display_name_cn    = COALESCE(EXCLUDED.display_name_cn, graphrag_drug_entities.display_name_cn),
                brand_names        = EXCLUDED.brand_names,
                link_permit_number = COALESCE(EXCLUDED.link_permit_number, graphrag_drug_entities.link_permit_number),
                in_local_whitelist = graphrag_drug_entities.in_local_whitelist OR EXCLUDED.in_local_whitelist,
                source = CASE
                    WHEN graphrag_drug_entities.source = 'local' AND EXCLUDED.source = 'fda' THEN 'both'
                    WHEN graphrag_drug_entities.source = 'fda'   AND EXCLUDED.source = 'local' THEN 'both'
                    ELSE EXCLUDED.source
                END,
                raw_openfda = COALESCE(EXCLUDED.raw_openfda, graphrag_drug_entities.raw_openfda),
                fetched_at  = EXCLUDED.fetched_at
            RETURNING entity_id
            """,
            norm, generic_name, display_name_cn, brand_names or [],
            permit_number, in_whitelist, source, openfda_json,
        )
        return row["entity_id"]

    async def get_entity_id(self, name_norm: str) -> Optional[int]:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            "SELECT entity_id FROM graphrag_drug_entities WHERE generic_name_norm = $1",
            name_norm,
        )
        return row["entity_id"] if row else None

    async def get_entity_ids(self, name_norms: List[str]) -> Dict[str, Optional[int]]:
        if not name_norms:
            return {}
        mapping: Dict[str, Optional[int]] = {n: None for n in name_norms}
        pool = await self._get_pool()
        rows = await pool.fetch(
            "SELECT entity_id, generic_name_norm FROM graphrag_drug_entities WHERE generic_name_norm = ANY($1::text[])",
            name_norms,
        )
        for row in rows:
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
        entity_type: str = "drug",
    ) -> None:
        pool = await self._get_pool()
        await pool.execute(
            """
            INSERT INTO graphrag_drug_interactions
                (drug_1_id, drug_2_name, drug_2_id, relation, severity,
                 entity_type, description_id, evidence_snippet, extracted_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7::uuid, $8, NOW())
            """,
            drug_1_id, drug_2_name, drug_2_id, relation, severity,
            entity_type, description_id, evidence_snippet[:500],
        )

    async def graph_query(
        self,
        entity_ids: List[int],
        severity_filter: Optional[str] = None,
    ) -> List[dict]:
        if not entity_ids:
            return []

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
                i.entity_type,
                i.relation,
                i.severity,
                i.evidence_snippet,
                i.description_id::text,
                i.extracted_at
            FROM graphrag_drug_interactions i
            JOIN graphrag_drug_entities e1 ON e1.entity_id = i.drug_1_id
            LEFT JOIN graphrag_drug_entities e2 ON e2.entity_id = i.drug_2_id
            WHERE (i.drug_1_id = ANY($1::int[]) OR i.drug_2_id = ANY($1::int[]))
            {severity_clause}
            ORDER BY {_SEVERITY_ORDER}, i.extracted_at DESC
            LIMIT 50
        """

        pool = await self._get_pool()
        rows = await pool.fetch(sql, entity_ids)
        return [dict(row) for row in rows]
