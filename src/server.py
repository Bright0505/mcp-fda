"""MCP server implementation for FDA Drug Interaction Checker."""

import asyncio
import logging
import os
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolRequest

from tools.registry import ToolRegistry
from tools.definitions import DB_TOOLS as TOOLS_DEFINITIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global tool registry
_tool_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create tool registry instance."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


async def handle_call_tool(request: CallToolRequest) -> dict:
    """Handle MCP tool calls via the tool registry."""
    try:
        registry = get_tool_registry()
        result = await registry.handle_tool(request, None)
        if result is not None:
            return result

        return {
            "content": [{"type": "text", "text": f"Unknown tool: {request.name}"}]
        }

    except Exception as e:
        logger.error(f"Tool call error in {request.name}: {e}", exc_info=True)
        return {
            "content": [{"type": "text", "text": f"Internal server error in tool '{request.name}': {e}"}]
        }


async def on_list_tools(ctx, params) -> dict:
    return {"tools": TOOLS_DEFINITIONS}


async def on_call_tool(ctx, params) -> dict:
    request = type('CallToolRequest', (), {
        'name': params.name,
        'arguments': params.arguments or {}
    })()
    return await handle_call_tool(request)


async def on_list_prompts(ctx, params) -> dict:
    return {"prompts": []}


async def on_list_resources(ctx, params) -> dict:
    return {"resources": []}


async def main():
    """Main server entry point."""
    server_name = os.getenv("MCP_SERVER_NAME", "mcp-fda")
    server = Server(
        server_name,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
        on_list_prompts=on_list_prompts,
        on_list_resources=on_list_resources,
    )

    logger.info(f"Starting MCP FDA Server ({server_name})...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
