"""三個 MCP 入口檔案(server.py / http_server.py / protocol/base_server.py)的測試。

mcp SDK v2 把 handler 註冊從 decorator(@server.list_tools() 等)改成
建構子傳入 callback(on_list_tools= 等),而且 handler 回傳值要嘛是
BaseModel、要嘛是 dict、要嘛是 None(mcp.server.runner._dump_result),
不能是裸 list。這裡驗證三個入口都真的用得動這組 API——遷移前這三個檔案
完全零測試覆蓋(K-4),這是修這個「無守備」缺口的部分。
"""

import httpx

import server as server_mod
from protocol.base_server import BaseMCPServer
from http_server import MCPHTTPServer


class FakeParams:
    """模擬 mcp.types.CallToolRequestParams 的 name/arguments 形狀。"""

    def __init__(self, name="nonexistent_tool_xyz", arguments=None):
        self.name = name
        self.arguments = arguments or {}


# ─── src/server.py ───────────────────────────────────────────────────────────


async def test_server_list_tools_returns_dict_with_tools_key():
    result = await server_mod.on_list_tools(None, None)
    assert isinstance(result, dict)
    assert "tools" in result
    assert result["tools"] == server_mod.TOOLS_DEFINITIONS


async def test_server_list_prompts_returns_empty_dict_shape():
    assert await server_mod.on_list_prompts(None, None) == {"prompts": []}


async def test_server_list_resources_returns_empty_dict_shape():
    assert await server_mod.on_list_resources(None, None) == {"resources": []}


async def test_server_call_tool_unknown_name_returns_content_dict():
    result = await server_mod.on_call_tool(None, FakeParams())
    assert isinstance(result, dict)
    assert "content" in result
    assert "Unknown tool" in result["content"][0]["text"]


def test_server_construction_accepts_v2_callback_kwargs():
    """v1 的 @server.list_tools() decorator 在 v2 不存在,建構子必須接受
    on_list_tools= 這種 kwargs 才不會在啟動時就炸掉。"""
    server_mod.Server(
        "test",
        on_list_tools=server_mod.on_list_tools,
        on_call_tool=server_mod.on_call_tool,
        on_list_prompts=server_mod.on_list_prompts,
        on_list_resources=server_mod.on_list_resources,
    )


# ─── src/protocol/base_server.py ────────────────────────────────────────────


async def test_base_server_handlers_return_expected_shapes():
    base = BaseMCPServer("test")

    tools_result = await base._on_list_tools(None, None)
    assert "tools" in tools_result

    call_result = await base._on_call_tool(None, FakeParams())
    assert "content" in call_result

    assert await base._on_list_prompts(None, None) == {"prompts": []}
    assert await base._on_list_resources(None, None) == {"resources": []}


# ─── src/http_server.py ─────────────────────────────────────────────────────


async def test_http_server_handlers_return_dict_not_list():
    """遷移前 http_server.py 的 call_tool handler 回傳裸 list,
    v2 的 _dump_result 只接受 BaseModel/dict/None,裸 list 會直接 TypeError。"""
    http = MCPHTTPServer()

    tools_result = await http._on_list_tools(None, None)
    assert isinstance(tools_result, dict)
    assert "tools" in tools_result

    call_result = await http._on_call_tool(None, FakeParams())
    assert isinstance(call_result, dict)
    assert "content" in call_result

    assert await http._on_list_prompts(None, None) == {"prompts": []}
    assert await http._on_list_resources(None, None) == {"resources": []}


def test_http_server_mounts_streamable_http_not_sse():
    """棄用 SSE 改 Streamable HTTP 後,/mcp 要掛上去、/sse 不該再出現。"""
    http = MCPHTTPServer()
    paths = [route.path for route in http.app.routes]
    assert "/mcp" in paths
    assert not any(p.startswith("/sse") for p in paths)
    assert not hasattr(http, "sse_transport")


async def test_http_server_streamable_http_handles_real_initialize_handshake():
    """/mcp 端點要能真的走完一次 MCP initialize 交握,不是只確認沒有 404。"""
    http = MCPHTTPServer()
    transport = httpx.ASGITransport(app=http.app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as client:
        async with http.app.router.lifespan_context(http.app):
            response = await client.post(
                "/mcp",
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                },
            )

    assert response.status_code == 200
    assert '"serverInfo"' in response.text
    assert '"capabilities"' in response.text
