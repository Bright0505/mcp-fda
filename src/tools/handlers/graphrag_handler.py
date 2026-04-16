"""GraphRAG Handler — drug_check_safety + drug_ingest_fda 工具實作。"""

import logging
from typing import Any, Dict, List

from mcp.types import CallToolRequest

from graphrag.ingestion import ingest_drug
from graphrag.name_resolver import _is_ascii_name, normalize, resolve_drug_names
from graphrag.retriever import (
    format_markdown_report,
    get_entity_ids,
    graph_query,
)
from graphrag.store import get_store
from tools.base import ToolHandler
from tools.definitions import make_tool_name

logger = logging.getLogger(__name__)

TOOL_CHECK_SAFETY = "check_safety"
TOOL_INGEST_FDA = "ingest_fda"


class GraphRAGHandler(ToolHandler):
    """處理 drug_check_safety 與 drug_ingest_fda 工具調用。"""

    @property
    def tool_names(self) -> List[str]:
        return [
            make_tool_name(TOOL_CHECK_SAFETY),
            make_tool_name(TOOL_INGEST_FDA),
        ]

    async def handle(self, request: CallToolRequest, db_manager: Any) -> Dict[str, Any]:
        tool = request.name
        args = request.arguments or {}

        if tool == make_tool_name(TOOL_CHECK_SAFETY):
            return await self._check_safety(args)
        if tool == make_tool_name(TOOL_INGEST_FDA):
            return await self._ingest_fda(args)

        return self._error_response(f"未知工具: {tool}")

    async def _check_safety(self, args: dict) -> Dict[str, Any]:
        """drug_check_safety 實作。"""
        drug_names: List[str] = args.get("drugs", [])
        severity_filter: str = args.get("severity_filter", "all")
        auto_fetch: bool = args.get("auto_fetch", True)

        if not drug_names:
            return self._error_response("請至少指定 1 種藥品名稱")
        if len(drug_names) > 10:
            return self._error_response("最多支援 10 種藥品，請分批查詢")

        store = await get_store()

        # 1. 藥名對齊
        resolved = await resolve_drug_names(drug_names)

        # 2. 收集唯一英文成分（去重）
        unique_ingredients: List[str] = []
        seen_ings: set = set()
        for name in drug_names:
            ings = resolved[name].get("ingredients") or []
            if not ings:
                if _is_ascii_name(name):
                    ings = [name]
                else:
                    logger.warning(f"'{name}' 非英文名稱，略過")
            for ing in ings:
                key = ing.upper()
                if key not in seen_ings:
                    seen_ings.add(key)
                    unique_ingredients.append(ing)

        # 3. 懶加載 ingestion
        if auto_fetch:
            for ing in unique_ingredients:
                await ingest_drug(
                    generic_name=ing,
                    store=store,
                    db_manager=None,
                )

        # 4. 圖譜查詢
        entity_id_map = await get_entity_ids(unique_ingredients, store)
        entity_ids = [eid for eid in entity_id_map.values() if eid is not None]
        graph_results = await graph_query(entity_ids, store, severity_filter)

        # 5. 格式化報告
        report = format_markdown_report(
            drug_names=drug_names,
            resolved=resolved,
            graph_results=graph_results,
        )
        return self._success_response(report)

    async def _ingest_fda(self, args: dict) -> Dict[str, Any]:
        """drug_ingest_fda 實作。"""
        generic_names: List[str] = args.get("generic_names", [])
        force_refresh: bool = args.get("force_refresh", False)
        limit: int = min(args.get("limit", 50), 500)

        store = await get_store()

        if not generic_names:
            return self._error_response(
                "請提供 generic_names 列表（英文通用名稱）"
            )

        skipped = [n for n in generic_names if not _is_ascii_name(n)]
        if skipped:
            logger.warning(f"非英文名稱，已略過: {skipped}")
        rows = [n for n in generic_names[:limit] if _is_ascii_name(n)]

        if not rows:
            return self._error_response("無可處理的藥品名稱")

        stats = {"ok": 0, "not_found": 0, "cached": 0, "error": 0, "total_interactions": 0}
        errors = []

        for name_en in rows:
            res = await ingest_drug(
                generic_name=name_en,
                store=store,
                db_manager=None,
                force_refresh=force_refresh,
            )
            status = res.get("status", "error")
            if status in ("ok", "ok_no_interactions"):
                stats["ok"] += 1
                stats["total_interactions"] += res.get("interaction_count", 0)
            elif status == "cached":
                stats["cached"] += 1
            elif status == "not_found":
                stats["not_found"] += 1
            else:
                stats["error"] += 1
                if res.get("error"):
                    errors.append(f"{name_en}: {res['error']}")

        report = (
            f"### FDA Ingestion 完成\n\n"
            f"| 狀態 | 數量 |\n"
            f"|------|------|\n"
            f"| ✅ 成功 | {stats['ok']} |\n"
            f"| 💾 快取命中 | {stats['cached']} |\n"
            f"| 🔍 FDA 查無 | {stats['not_found']} |\n"
            f"| ❌ 錯誤 | {stats['error']} |\n"
            f"| 📊 新增交互作用 | {stats['total_interactions']} |\n"
        )
        if errors:
            report += f"\n**錯誤明細**（前 5 筆）：\n"
            for e in errors[:5]:
                report += f"- {e}\n"

        return self._success_response(report)
