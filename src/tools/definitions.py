"""MCP tool definitions for FDA Drug Interaction Checker."""

import os
from typing import List
from mcp.types import Tool


def get_tool_prefix() -> str:
    """Get tool name prefix from environment or default."""
    return os.getenv("TOOL_PREFIX", "drug")


def make_tool_name(suffix: str) -> str:
    """Generate a tool name with the configured prefix."""
    return f"{get_tool_prefix()}_{suffix}"


# Tool suffix constants
TOOL_CHECK_SAFETY = "check_safety"
TOOL_INGEST_FDA = "ingest_fda"


def get_all_tools() -> List[Tool]:
    """Generate FDA tool definitions with the configured prefix."""
    prefix = get_tool_prefix()

    return [
        Tool(
            name=f"{prefix}_{TOOL_CHECK_SAFETY}",
            description=(
                "檢查多種藥品的交互作用與安全警告，透過 FDA 知識圖譜（SQLite）進行結構化查詢。\n\n"
                "輸入 1–10 種藥品的英文通用名稱（generic name），系統會：\n"
                "1. 自動查詢 FDA API 補充未快取的交互作用資料\n"
                "2. 以 Markdown 表格輸出交互作用嚴重程度與說明\n\n"
                "⚠ 僅支援英文通用名稱（如 aspirin、warfarin），不支援中文藥名。\n\n"
                "用於用藥安全諮詢、多藥合用評估、藥品風險查詢。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "drugs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "英文通用名稱列表（1–10 種，例如 aspirin、warfarin）",
                        "minItems": 1,
                        "maxItems": 10
                    },
                    "severity_filter": {
                        "type": "string",
                        "enum": ["all", "major", "moderate+"],
                        "default": "all",
                        "description": "嚴重程度過濾：all=全部、major=僅嚴重、moderate+=中度以上"
                    },
                    "auto_fetch": {
                        "type": "boolean",
                        "default": True,
                        "description": "若藥品尚未快取，是否自動呼叫 FDA API（預設 true）"
                    }
                },
                "required": ["drugs"]
            }
        ),
        Tool(
            name=f"{prefix}_{TOOL_INGEST_FDA}",
            description=(
                "手動觸發 FDA 藥品交互作用資料擷取，更新知識圖譜與向量資料庫。\n\n"
                "適用情境：\n"
                "- 初始化或預載特定藥品的 FDA 資料\n"
                "- 強制重新整理特定藥品的資料（force_refresh=true）\n"
                "- 排程定期更新（可搭配 limit 分批執行）\n\n"
                "⚠ 必須提供英文通用名稱列表（generic_names）。\n"
                "⚠ 管理工具：每次呼叫會觸發 FDA API 請求，請勿頻繁調用。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "generic_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要擷取的英文藥品通用名稱列表（必填，如 [\"aspirin\", \"warfarin\"]）"
                    },
                    "force_refresh": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否忽略快取強制重新查詢 FDA（預設 false）"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 500,
                        "description": "最多處理幾種藥品（預設 50，最大 500）"
                    }
                },
                "required": ["generic_names"]
            }
        )
    ]


DB_TOOLS = get_all_tools()
