"""HTTP server wrapper for FDA Drug Interaction MCP Server.

Provides REST API access and MCP Streamable HTTP support.
"""

import asyncio
import contextlib
from contextlib import asynccontextmanager
import logging
import os
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI
import uvicorn

from mcp.server import Server

from tools import ToolRegistry, get_all_tools
from api.middleware import setup_middleware

logger = logging.getLogger(__name__)


class MCPHTTPServer:
    """HTTP server wrapper for FDA drug interaction MCP tools with Streamable HTTP support."""

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
        # host= 用來讓 SDK 判斷要不要自動開 DNS-rebinding 保護(只在
        # 127.0.0.1/localhost/::1 時自動開)。不傳的話預設是 127.0.0.1,
        # 會誤判成本機開發、限制 Host header,但實際部署通常綁 0.0.0.0。
        # 讀 HTTP_HOST 就好,跟原本 SSE 一樣不做額外限制,不擴大這次變更範圍
        mcp_asgi_app = self.mcp_server.streamable_http_app(
            streamable_http_path="/",
            host=os.getenv("HTTP_HOST", "0.0.0.0"),
        )

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with contextlib.AsyncExitStack() as stack:
                await stack.enter_async_context(self.mcp_server.session_manager.run())
                logger.info("FDA MCP server started")
                yield
                logger.info("FDA MCP server shutting down")

        self.app = FastAPI(
            title="MCP FDA Drug Interaction API",
            description="REST API & MCP Streamable HTTP for FDA Drug Interaction Checker",
            version="1.0.0",
            docs_url="/docs",
            redoc_url="/redoc",
            lifespan=lifespan
        )

        # Mount MCP Streamable HTTP sub-app
        self.app.mount("/mcp", mcp_asgi_app)

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
                    "mcp": "/mcp",
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

        logger.info(f"Starting MCP FDA HTTP API + Streamable HTTP server at http://{host}:{port}")
        logger.info(f"API docs: http://{host}:{port}/docs")
        logger.info(f"MCP Streamable HTTP endpoint: http://{host}:{port}/mcp")

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
