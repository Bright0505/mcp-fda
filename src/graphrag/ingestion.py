"""Ingestion Pipeline — FDA 懶加載 → LLM 萃取 → GraphRAGStore 入庫。"""

import logging
from typing import Any, List, Optional
from uuid import uuid4

from graphrag.extractor import extract_interactions
from graphrag.fda_client import (
    FDANotFoundError,
    FDAServiceError,
    extract_interaction_text,
    extract_openfda_section,
    fetch_label,
)
from graphrag.name_resolver import get_whitelist_sample, normalize
from graphrag.store.base import GraphRAGStore

logger = logging.getLogger(__name__)


async def ingest_drug(
    generic_name: str,
    store: GraphRAGStore,
    db_manager: Any = None,
    force_refresh: bool = False,
    display_name_cn: Optional[str] = None,
    permit_number: Optional[str] = None,
    in_whitelist: bool = False,
    local_whitelist: Optional[List[str]] = None,
) -> dict:
    """對單一藥品執行完整 ingestion pipeline。

    Args:
        generic_name:    藥品英文學名
        store:           GraphRAGStore 實例（圖譜讀寫）
        db_manager:      保留參數（未使用）
        force_refresh:   忽略快取，強制重新查詢 FDA
        display_name_cn: 中文名稱（可由呼叫端提供）
        permit_number:   許可證字號
        in_whitelist:    是否在本地合法用藥清單中
        local_whitelist: 預先取得的白名單樣本

    Returns:
        dict with keys: status, interaction_count, error
    """
    norm = normalize(generic_name)

    # 1. 快取檢查
    if not force_refresh:
        cached = await store.check_cache(norm)
        if cached == "skip":
            logger.debug(f"快取命中，略過: {generic_name}")
            return {"status": "cached", "interaction_count": 0, "error": None}
        if cached == "not_found":
            return {"status": "not_found", "interaction_count": 0, "error": None}

    # 2. FDA API 呼叫
    try:
        fda_result = await fetch_label(generic_name)
    except FDANotFoundError as e:
        await store.upsert_fetch_log(norm, "not_found", 404, str(e))
        return {"status": "not_found", "interaction_count": 0, "error": str(e)}
    except (FDAServiceError, Exception) as e:
        await store.upsert_fetch_log(norm, "error", None, str(e))
        return {"status": "error", "interaction_count": 0, "error": str(e)}

    # 3. 取出 drug_interactions 原文
    interaction_text = extract_interaction_text(fda_result)
    openfda = extract_openfda_section(fda_result)
    brand_names = openfda.get("brand_name", []) if openfda else []

    # 4. upsert 主實體
    drug_1_id = await store.upsert_entity(
        generic_name=generic_name,
        display_name_cn=display_name_cn,
        permit_number=permit_number,
        in_whitelist=in_whitelist,
        source="both" if in_whitelist else "fda",
        openfda=openfda,
        brand_names=brand_names,
    )

    if not interaction_text:
        await store.upsert_fetch_log(norm, "ok", 200, None, 0)
        return {"status": "ok_no_interactions", "interaction_count": 0, "error": None}

    # 5. LLM 萃取
    whitelist = local_whitelist or await get_whitelist_sample(db_manager)
    interactions = await extract_interactions(generic_name, interaction_text, whitelist)

    # 6. GraphRAGStore 入庫
    count = 0
    for item in interactions:
        drug_2_name = item.get("drug_2", "").strip()
        relation = item.get("relation", "interacts_with")
        severity = item.get("severity", "unknown")
        evidence = item.get("evidence", "")[:2000]

        if not drug_2_name or not evidence:
            continue

        valid_relations = {
            "interacts_with", "contraindicated",
            "increases_effect", "decreases_effect", "monitor_closely"
        }
        valid_severities = {"major", "moderate", "minor", "unknown"}
        relation = relation if relation in valid_relations else "interacts_with"
        severity = severity if severity in valid_severities else "unknown"

        # upsert drug_2 實體
        drug_2_norm = normalize(drug_2_name)
        drug_2_id = await store.get_entity_id(drug_2_norm)
        if drug_2_id is None:
            drug_2_id = await store.upsert_entity(drug_2_name, source="fda")

        desc_id = uuid4()

        await store.insert_interaction(
            drug_1_id=drug_1_id,
            drug_2_name=drug_2_name,
            drug_2_id=drug_2_id,
            relation=relation,
            severity=severity,
            description_id=str(desc_id),
            evidence_snippet=evidence,
        )
        count += 1

    await store.upsert_fetch_log(norm, "ok", 200, None, count)
    logger.info(f"Ingestion 完成: {generic_name} → {count} 筆交互作用")
    return {"status": "ok", "interaction_count": count, "error": None}
