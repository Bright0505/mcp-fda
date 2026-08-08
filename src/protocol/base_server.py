"""Base MCP server - Transport-agnostic MCP protocol implementation."""

import logging
import os
from mcp.server import Server
from tools import get_all_tools
from tools.handlers import handle_tool_call

logger = logging.getLogger(__name__)


class BaseMCPServer:
    """Base MCP server providing core protocol functionality."""

    def __init__(self, server_name: str = None):
        if server_name is None:
            server_name = os.getenv("MCP_SERVER_NAME", "mcp-fda")
        self.server = Server(
            server_name,
            on_list_tools=self._on_list_tools,
            on_call_tool=self._on_call_tool,
            on_list_prompts=self._on_list_prompts,
            on_list_resources=self._on_list_resources,
        )
        logger.info(f"Initialized {server_name} MCP server")

    async def _on_list_tools(self, ctx, params):
        return {"tools": get_all_tools()}

    async def _on_call_tool(self, ctx, params):
        request = type('CallToolRequest', (), {
            'name': params.name,
            'arguments': params.arguments or {}
        })()
        return await handle_tool_call(request, None)

    async def _on_list_prompts(self, ctx, params):
        return {"prompts": []}

    async def _on_list_resources(self, ctx, params):
        return {"resources": []}
