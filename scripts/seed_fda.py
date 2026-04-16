#!/usr/bin/env python3
"""批次從 drug_permits 撈藥品，觸發 FDA Ingestion Pipeline。

執行方式：
    python scripts/seed_fda.py [--limit 10] [--concurrency 3] [--force-refresh]

在容器內：
    docker compose exec mcp-drug-http python scripts/seed_fda.py --limit 50
"""

import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

# 讓 src/ 模組可被 import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("seed_fda")


async def main(limit: int, concurrency: int, force_refresh: bool):
    from database.async_manager import HybridDatabaseManager
    from graphrag.ingestion import ingest_drug
    from graphrag.name_resolver import get_whitelist_sample

    logger.info("初始化資料庫連線...")
    db_manager = HybridDatabaseManager.create_with_preload()

    # 撈取有效藥品清單
    sql = f"""
        SELECT name_en, name_cn, permit_number
        FROM drug_permits
        WHERE cancel_status = ''
          AND name_en IS NOT NULL AND trim(name_en) <> ''
        ORDER BY name_en
        LIMIT {limit}
    """
    result = await db_manager.execute_query_async(sql)
    rows = result.get("results", []) if result.get("success") else []
    logger.info(f"找到 {len(rows)} 種有效藥品（limit={limit}）")

    # 取得白名單樣本（提供給 LLM）
    whitelist = await get_whitelist_sample(db_manager, limit=200)

    # 並行執行 ingestion（semaphore 控制並行數）
    sem = asyncio.Semaphore(concurrency)
    stats = {"ok": 0, "cached": 0, "not_found": 0, "error": 0, "interactions": 0}

    async def process(row: dict):
        name_en = row.get("name_en", "")
        if not name_en:
            return
        async with sem:
            res = await ingest_drug(
                generic_name=name_en,
                db_manager=db_manager,
                force_refresh=force_refresh,
                display_name_cn=row.get("name_cn"),
                permit_number=row.get("permit_number"),
                in_whitelist=True,
                local_whitelist=whitelist,
            )
            status = res.get("status", "error")
            count = res.get("interaction_count", 0)
            stats["interactions"] += count

            if status in ("ok", "ok_no_interactions"):
                stats["ok"] += 1
                logger.info(f"  ✅ {name_en}: {count} 筆交互作用")
            elif status == "cached":
                stats["cached"] += 1
                logger.debug(f"  💾 {name_en}: 快取命中")
            elif status == "not_found":
                stats["not_found"] += 1
                logger.info(f"  🔍 {name_en}: FDA 查無資料")
            else:
                stats["error"] += 1
                logger.warning(f"  ❌ {name_en}: {res.get('error')}")

    tasks = [process(row) for row in rows]
    await asyncio.gather(*tasks)

    print("\n" + "="*50)
    print("Seed FDA 完成統計")
    print("="*50)
    print(f"  ✅ 成功: {stats['ok']}")
    print(f"  💾 快取: {stats['cached']}")
    print(f"  🔍 查無: {stats['not_found']}")
    print(f"  ❌ 錯誤: {stats['error']}")
    print(f"  📊 新增交互作用: {stats['interactions']}")
    print("="*50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FDA Drug Interaction Seed Script")
    parser.add_argument("--limit", type=int, default=50, help="處理藥品數量上限（預設 50）")
    parser.add_argument("--concurrency", type=int, default=3, help="並行查詢數（預設 3）")
    parser.add_argument("--force-refresh", action="store_true", help="忽略快取強制重新查詢")
    args = parser.parse_args()

    asyncio.run(main(args.limit, args.concurrency, args.force_refresh))
