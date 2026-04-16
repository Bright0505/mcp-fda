"""Configuration management for MCP FDA Drug Interaction Server."""

import os
from typing import Optional
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# 載入 .env 檔案，支援多種路徑策略
_env_loaded = False

# 優先使用環境變數指定的路徑
env_file = os.getenv('ENV_FILE_PATH')
if env_file and Path(env_file).exists():
    load_dotenv(env_file, override=False)
    _env_loaded = True
else:
    # 嘗試多個可能的路徑
    possible_paths = [
        Path.cwd() / '.env',  # 當前工作目錄
        Path(__file__).parent.parent.parent / '.env',  # 專案根目錄
        Path('/app/.env')  # Docker 容器路徑（最後嘗試）
    ]
    for env_path in possible_paths:
        if env_path.exists():
            load_dotenv(str(env_path), override=False)
            _env_loaded = True
            break

if not _env_loaded:
    # Fallback 到預設行為
    load_dotenv()


class HTTPConfig(BaseModel):
    """HTTP server configuration including rate limiting and CORS."""

    rate_limit_default: str = Field(default="100/minute")
    rate_limit_query: str = Field(default="30/minute")
    cors_preflight_max_age: int = Field(default=600)

    @classmethod
    def from_env(cls) -> "HTTPConfig":
        return cls(
            rate_limit_default=os.getenv("RATE_LIMIT_DEFAULT", "100/minute"),
            rate_limit_query=os.getenv("RATE_LIMIT_QUERY", "30/minute"),
            cors_preflight_max_age=int(os.getenv("CORS_PREFLIGHT_MAX_AGE", "600"))
        )


def get_http_config() -> "HTTPConfig":
    """Get HTTPConfig from environment variables."""
    return HTTPConfig.from_env()


class AppConfig(BaseModel):
    """Application configuration."""

    http_config: HTTPConfig
    tool_prefix: str = Field(default="drug")
    server_name: str = Field(default="mcp-fda")

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            http_config=HTTPConfig.from_env(),
            tool_prefix=os.getenv("TOOL_PREFIX", "drug"),
            server_name=os.getenv("MCP_SERVER_NAME", "mcp-fda")
        )