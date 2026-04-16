"""STDIO transport MCP server."""

import logging
from mcp.server.stdio import stdio_server
from protocol.base_server import BaseMCPServer

logger = logging.getLogger(__name__)


class StdioMCPServer(BaseMCPServer):
    """MCP server using STDIO transport."""

    def __init__(self):
        super().__init__()

    async def run(self):
        """Run the STDIO MCP server."""
        logger.info("Starting STDIO MCP server")
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


async def run_stdio_server():
    """Run STDIO MCP server."""
    server = StdioMCPServer()
    await server.run()
