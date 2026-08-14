"""檢索器 — GraphRAGStore 圖譜查詢。"""

import logging
from typing import Dict, List, Optional

from graphrag.name_resolver import normalize
from graphrag.store.base import GraphRAGStore

logger = logging.getLogger(__name__)


async def graph_query(
    entity_ids: List[int],
    store: GraphRAGStore,
    severity_filter: Optional[str] = None,
) -> List[dict]:
    """從 GraphRAGStore 圖譜查詢已知交互作用。"""
    return await store.graph_query(entity_ids, severity_filter)


async def get_entity_ids(
    generic_names: List[str],
    store: GraphRAGStore,
) -> Dict[str, Optional[int]]:
    """查詢藥名對應的 entity_id。"""
    if not generic_names:
        return {}
    norm_names = [normalize(n) for n in generic_names]
    norm_to_orig = dict(zip(norm_names, generic_names))

    id_map = await store.get_entity_ids(norm_names)

    result: Dict[str, Optional[int]] = {n: None for n in generic_names}
    for norm, eid in id_map.items():
        orig = norm_to_orig.get(norm)
        if orig is not None:
            result[orig] = eid
    return result


def format_passthrough_report(
    drug_results: List[dict],
) -> str:
    """直通模式：將 FDA 原文整理為 Markdown，供呼叫端 LLM 解讀。"""
    lines: List[str] = []
    lines.append("> ℹ️ **直通模式**：LLM 未設定，以下為 FDA 原始資料，請依臨床判斷評估交互作用風險。")
    lines.append("")

    for item in drug_results:
        name = item.get("generic_name", "")
        status = item.get("status", "")
        raw = item.get("raw_text")

        lines.append(f"### {name.upper()}")

        if status == "cached":
            lines.append("_(快取)_")
        if status == "not_found":
            lines.append("_FDA 查無此藥品資料。_")
        elif status == "ok_no_interactions":
            lines.append("_FDA 標籤中無 drug interactions 段落。_")
        elif status == "error":
            lines.append(f"_查詢失敗：{item.get('error')}_")
        elif raw:
            lines.append(raw)

        lines.append("")

    lines.append("---")
    lines.append("> ⚕️ **免責聲明**：本資訊為參考用途，實際用藥請諮詢醫師或藥師。")
    return "\n".join(lines)


def format_markdown_report(
    drug_names: List[str],
    resolved: Dict[str, dict],
    graph_results: List[dict],
) -> str:
    """將圖譜查詢結果格式化為 Markdown 報告。"""
    lines: List[str] = []

    # 圖譜結果
    lines.append("### 已知交互作用（FDA 知識圖譜）")
    if graph_results:
        severity_icon = {"major": "🔴", "moderate": "🟠", "minor": "🟡", "unknown": "⚪"}
        # 類別標記：仿單的交互作用段落不只寫藥品，也寫補充劑、草藥與食物。
        # 標出來，讀者才知道哪一條是「與保健食品」而不是「與另一種處方藥」。
        type_icon = {"supplement": "🌿", "food": "🍽", "class": "📚"}
        lines.append("| 藥品 A | 交互作用對象 | 類別 | 關係 | 嚴重度 | 摘要 |")
        lines.append("|--------|--------------|------|------|--------|------|")
        for row in graph_results:
            d1 = row.get("drug_1", "")
            d1cn = row.get("drug_1_cn") or ""
            d2 = row.get("drug_2", "")
            d2cn = row.get("drug_2_cn") or ""
            d1_display = f"{d1}（{d1cn}）" if d1cn else d1
            d2_display = f"{d2}（{d2cn}）" if d2cn else d2
            rel = row.get("relation", "")
            sev = row.get("severity", "unknown")
            icon = severity_icon.get(sev, "⚪")
            snippet = (row.get("evidence_snippet") or "")[:80].replace("|", "\\|")
            etype = (row.get("entity_type") or "drug").lower()
            etype_cell = f"{type_icon.get(etype, '💊')} {etype}"
            lines.append(
                f"| {d1_display} | {d2_display} | {etype_cell} | {rel} "
                f"| {icon} {sev} | {snippet}... |"
            )
    else:
        lines.append("_圖譜中無已知交互作用記錄。（若資料尚未擷取，可使用 drug_ingest_fda 觸發）_")

    lines.append("")
    lines.append("---")
    lines.append("> ⚕️ **免責聲明**：本資訊為參考用途，實際用藥請諮詢醫師或藥師。")

    return "\n".join(lines)
