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
        self.server = Server(server_name)
        self._setup_handlers()
        logger.info(f"Initialized {server_name} MCP server")

    def _setup_handlers(self):
        """Setup MCP protocol handlers."""

        @self.server.list_tools()
        async def list_tools():
            return get_all_tools()

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict):
            request = type('CallToolRequest', (), {
                'name': name,
                'arguments': arguments or {}
            })()
            return await handle_tool_call(request, None)

        @self.server.list_prompts()
        async def list_prompts():
            return []

        @self.server.list_resources()
        async def list_resources():
            return []
