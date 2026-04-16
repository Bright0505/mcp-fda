"""Tool handlers package."""

from tools.handlers.graphrag_handler import GraphRAGHandler

__all__ = [
    'GraphRAGHandler',
    'handle_tool_call',
    'handle_call_tool',
]


# Lazy import to avoid circular dependency with registry
_registry = None


def _get_registry():
    global _registry
    if _registry is None:
        from tools.registry import ToolRegistry
        _registry = ToolRegistry()
    return _registry


async def handle_tool_call(request, db_manager=None) -> dict:
    """Unified tool handler entry point via ToolRegistry."""
    registry = _get_registry()
    result = await registry.handle_tool(request, db_manager)
    if result is not None:
        return result
    return {
        "content": [{"type": "text", "text": f"Unknown tool: {request.name}"}]
    }


handle_call_tool = handle_tool_call
