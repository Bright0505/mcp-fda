#!/usr/bin/env python3
"""初始化 GraphRAG 資料庫 Schema。

依 GRAPHRAG_DB_TYPE 環境變數選擇後端：
  - sqlite（預設）：建立本地 SQLite DB，使用 schema/graphrag_schema_sqlite.sql
  - postgresql：連線獨立 PostgreSQL，使用 schema/graphrag_schema.sql

執行方式：
    python scripts/init_graphrag_db.py

或在容器內：
    docker compose exec mcp-drug-http python scripts/init_graphrag_db.py
"""

import asyncio
import os
import sys
from pathlib import Path

# 讓 src/ 下的模組可被 import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

SCHEMA_DIR = Path(__file__).parent.parent / "schema"


async def init_sqlite() -> None:
    import aiosqlite

    db_path = os.getenv("GRAPHRAG_SQLITE_PATH", "/app/data/graphrag.db")
    schema_file = SCHEMA_DIR / "graphrag_schema_sqlite.sql"

    if not schema_file.exists():
        print(f"Schema 檔案不存在: {schema_file}")
        sys.exit(1)

    sql = schema_file.read_text(encoding="utf-8")
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    print(f"建立 SQLite DB: {db_path}")
    async with aiosqlite.connect(str(path)) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.executescript(sql)
        await conn.commit()

        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'graphrag_%' ORDER BY name"
        ) as cur:
            tables = [row[0] async for row in cur]

    print(f"建立完成，共 {len(tables)} 張 GraphRAG 資料表：")
    for t in tables:
        print(f"   - {t}")


def init_postgresql() -> None:
    import psycopg2

    schema_file = SCHEMA_DIR / "graphrag_schema.sql"
    if not schema_file.exists():
        print(f"Schema 檔案不存在: {schema_file}")
        sys.exit(1)

    sql = schema_file.read_text(encoding="utf-8")

    host = os.getenv("GRAPHRAG_PG_HOST")
    port = int(os.getenv("GRAPHRAG_PG_PORT", "5432"))
    dbname = os.getenv("GRAPHRAG_PG_NAME")
    user = os.getenv("GRAPHRAG_PG_USER")
    password = os.getenv("GRAPHRAG_PG_PASSWORD")

    missing = [k for k, v in {
        "GRAPHRAG_PG_HOST": host,
        "GRAPHRAG_PG_NAME": dbname,
        "GRAPHRAG_PG_USER": user,
        "GRAPHRAG_PG_PASSWORD": password,
    }.items() if not v]

    if missing:
        print(f"缺少必要環境變數：{', '.join(missing)}")
        sys.exit(1)

    print(f"連線 PostgreSQL {host}:{port}/{dbname}...")
    conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)
    conn.autocommit = True
    cur = conn.cursor()

    print("建立 GraphRAG 資料表...")
    cur.execute(sql)

    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name LIKE 'graphrag_%'
        ORDER BY table_name
    """)
    tables = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()

    print(f"建立完成，共 {len(tables)} 張 GraphRAG 資料表：")
    for t in tables:
        print(f"   - {t}")


def main() -> None:
    db_type = os.getenv("GRAPHRAG_DB_TYPE", "sqlite").lower()

    if db_type == "postgresql":
        init_postgresql()
    else:
        asyncio.run(init_sqlite())


if __name__ == "__main__":
    main()
