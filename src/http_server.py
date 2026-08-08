"""HTTP server wrapper for FDA Drug Interaction MCP Server.

Provides REST API access and MCP SSE (Server-Sent Events) support.
"""

import asyncio
from contextlib import asynccontextmanager
import logging
import os
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI
import uvicorn

from mcp.server import Server
from mcp.server.sse import SseServerTransport

from tools import ToolRegistry, get_all_tools
from api.middleware import setup_middleware

logger = logging.getLogger(__name__)


class MCPHTTPServer:
    """HTTP server wrapper for FDA drug interaction MCP tools with SSE support."""

    def __init__(self):
        self.tool_registry = ToolRegistry()

        self.server_name = os.getenv("MCP_SERVER_NAME", "mcp-fda")
        self.mcp_server = Server(
            self.server_name,
            on_list_tools=self._on_list_tools,
            on_call_tool=self._on_call_tool,
            on_list_prompts=self._on_list_prompts,
            on_list_resources=self._on_list_resources,
        )
        self.sse_transport = SseServerTransport("/messages")

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            logger.info("FDA MCP server started")
            yield
            logger.info("FDA MCP server shutting down")

        self.app = FastAPI(
            title="MCP FDA Drug Interaction API",
            description="REST API & SSE for FDA Drug Interaction Checker via MCP",
            version="1.0.0",
            docs_url="/docs",
            redoc_url="/redoc",
            lifespan=lifespan
        )

        # Mount MCP SSE ASGI sub-app
        async def mcp_sse_asgi_app(scope, receive, send):
            path = scope.get("path", "/")
            method = scope.get("method", "GET")

            if path == "/sse/" and method == "GET":
                async with self.sse_transport.connect_sse(scope, receive, send) as streams:
                    await self.mcp_server.run(
                        streams[0],
                        streams[1],
                        self.mcp_server.create_initialization_options()
                    )
            elif path.startswith("/sse/messages") and method == "POST":
                await self.sse_transport.handle_post_message(scope, receive, send)
            else:
                await send({
                    'type': 'http.response.start',
                    'status': 404,
                    'headers': [[b'content-type', b'text/plain']],
                })
                await send({
                    'type': 'http.response.body',
                    'body': b'Not Found',
                })

        self.app.mount("/sse", mcp_sse_asgi_app)

        # Apply middleware (CORS, GZip, rate limiting)
        from core.config import AppConfig
        app_config = AppConfig.from_env()
        setup_middleware(self.app, app_config)

        self._register_routes()

    async def _on_list_tools(self, ctx, params):
        return {"tools": get_all_tools()}

    async def _on_call_tool(self, ctx, params):
        try:
            request = type('CallToolRequest', (), {
                'name': params.name,
                'arguments': params.arguments or {}
            })()
            result = await self.tool_registry.handle_tool(request, None)
            if isinstance(result, dict) and "content" in result:
                return result
            content = result if isinstance(result, list) else [result]
            return {"content": content}
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}

    async def _on_list_prompts(self, ctx, params):
        return {"prompts": []}

    async def _on_list_resources(self, ctx, params):
        return {"resources": []}

    def _register_routes(self):
        """Register API routes."""

        @self.app.get("/")
        async def root():
            return {
                "name": "MCP FDA Drug Interaction Server",
                "version": "1.0.0",
                "endpoints": {
                    "health": "/api/v1/health",
                    "tools": "/api/v1/tools",
                    "mcp_sse": "/sse/",
                    "docs": "/docs"
                }
            }

        @self.app.get("/api/v1/health")
        async def health_check():
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "version": "1.0.0"
            }

        @self.app.get("/api/v1/tools")
        async def list_api_tools():
            tools = get_all_tools()
            return self._success_response([
                {"name": t.name, "description": t.description}
                for t in tools
            ])

        @self.app.post("/api/v1/tool")
        async def call_tool(body: dict):
            name = body.get("name")
            arguments = body.get("arguments", {})
            if not name:
                return {"success": False, "error": "missing 'name' field"}
            try:
                request = type('CallToolRequest', (), {
                    'name': name,
                    'arguments': arguments
                })()
                result = await self.tool_registry.handle_tool(request, None)
                return self._success_response(result)
            except Exception as e:
                logger.error(f"Tool call error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

    def _success_response(self, data: Any) -> Dict[str, Any]:
        return {
            "success": True,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }


def run_http_server(host: str = "0.0.0.0", port: int = 8000):
    """Run HTTP server."""
    async def start_server():
        server = MCPHTTPServer()

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        logger.info(f"Starting MCP FDA HTTP API + SSE server at http://{host}:{port}")
        logger.info(f"API docs: http://{host}:{port}/docs")
        logger.info(f"MCP SSE endpoint: http://{host}:{port}/sse")

        config_uvicorn = uvicorn.Config(
            server.app,
            host=host,
            port=port,
            log_level="info",
            workers=int(os.environ.get("MCP_WORKERS", "1")),
        )
        server_uvicorn = uvicorn.Server(config_uvicorn)
        await server_uvicorn.serve()

    asyncio.run(start_server())


if __name__ == "__main__":
    host = os.getenv("HTTP_HOST", "0.0.0.0")
    port = int(os.getenv("HTTP_PORT", "8000"))
    run_http_server(host, port)
