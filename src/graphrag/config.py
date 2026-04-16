"""GraphRAG 設定：從環境變數讀取 FDA / LLM / Store 連線參數。"""

import os


class GraphRAGConfig:
    # FDA API
    FDA_API_BASE: str = os.getenv("FDA_API_BASE", "https://api.fda.gov")
    FDA_CACHE_TTL_DAYS: int = int(os.getenv("FDA_CACHE_TTL_DAYS", "30"))
    FDA_TIMEOUT: int = int(os.getenv("FDA_TIMEOUT", "15"))
    FDA_MAX_RETRIES: int = int(os.getenv("FDA_MAX_RETRIES", "3"))

    # LLM Extraction（OpenAI-compatible，可對接任何相容端點）
    # 支援：OpenAI、Gemini、LiteLLM、或其他 OpenAI-compatible proxy
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))

    # GraphRAG Store 後端
    # 'sqlite'（預設，嵌入式）或 'postgresql'（獨立 PG，非 Data Lake）
    GRAPHRAG_DB_TYPE: str = os.getenv("GRAPHRAG_DB_TYPE", "sqlite").lower()

    # SQLite 模式
    GRAPHRAG_SQLITE_PATH: str = os.getenv("GRAPHRAG_SQLITE_PATH", "/app/data/graphrag.db")

    # PostgreSQL 模式（GRAPHRAG_DB_TYPE=postgresql 時必填）
    GRAPHRAG_PG_HOST: str = os.getenv("GRAPHRAG_PG_HOST", "")
    GRAPHRAG_PG_PORT: int = int(os.getenv("GRAPHRAG_PG_PORT", "5432"))
    GRAPHRAG_PG_NAME: str = os.getenv("GRAPHRAG_PG_NAME", "")
    GRAPHRAG_PG_USER: str = os.getenv("GRAPHRAG_PG_USER", "")
    GRAPHRAG_PG_PASSWORD: str = os.getenv("GRAPHRAG_PG_PASSWORD", "")

    @classmethod
    def is_llm_configured(cls) -> bool:
        """回傳 True 表示 LLM 已設定，可執行提取模式；False 則降為直通模式。"""
        return bool(cls.LLM_API_KEY.strip())
