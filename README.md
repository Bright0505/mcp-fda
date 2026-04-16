# mcp-fda — FDA 藥品交互作用 MCP 伺服器

[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-compatible-blue.svg)](https://modelcontextprotocol.io)

獨立的 FDA 藥品交互作用 MCP 模組。自動擷取 FDA API 資料，透過 **GraphRAG 知識圖譜**（SQLite）提供結構化交互作用查詢，並以 SQLite 作為 FDA 快取層，無需任何外部服務即可運行。

> 此模組不依賴任何內部藥品資料庫，僅需提供英文藥品通用名稱（generic name）即可查詢。

---

## 架構

```
MCP Client / Open WebUI / Claude Desktop
         │
         ▼
    mcp-fda (port 8000)
         │
         ├── drug_check_safety    # 交互作用查詢（懶加載 + 圖譜查詢）
         └── drug_ingest_fda      # 手動觸發 FDA 資料擷取
              │
              ├──► SQLite (/app/data/graphrag.db)
              │      ├── graphrag_drug_entities      # 藥品節點
              │      ├── graphrag_drug_interactions  # 交互作用關係
              │      └── graphrag_fetch_log          # FDA API 快取（TTL=30天）
              │
              └──► LLM（任意 OpenAI-compatible 端點）
                     └──► FDA API (api.fda.gov)
```

---

## 快速開始

### Docker（建議）

```bash
git clone https://github.com/Bright0505/mcp-fda.git
cd mcp-fda

cp .env.example .env
# 編輯 .env，填入 LLM_API_KEY 與 LLM_BASE_URL

docker compose up -d

# 驗證
curl http://localhost:8000/api/v1/health
```

### 本地開發

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env

# SQLite 模式（預設）不需初始化，首次查詢自動建表
python src/main.py --http
```

---

## MCP Client 設定

### Claude Code / Claude Desktop（STDIO）

建立 `.mcp.json`（參考 `.mcp.json.example`，此檔含 API Key 請勿提交）：

```json
{
  "mcpServers": {
    "mcp-fda": {
      "type": "stdio",
      "command": "/path/to/mcp-fda/.venv/bin/python3",
      "args": ["/path/to/mcp-fda/src/main.py"],
      "env": {
        "PYTHONPATH": "/path/to/mcp-fda/src",
        "LLM_BASE_URL": "https://api.openai.com/v1",
        "LLM_API_KEY": "your-api-key",
        "LLM_MODEL": "gpt-4o-mini",
        "GRAPHRAG_DB_TYPE": "sqlite",
        "GRAPHRAG_SQLITE_PATH": "/path/to/mcp-fda/data/graphrag.db",
        "TOOL_PREFIX": "drug",
        "MCP_SERVER_NAME": "mcp-fda"
      }
    }
  }
}
```

### Open WebUI / MCPO（SSE）

```bash
# docker compose 啟動後，MCPO 指向：
http://localhost:8000/sse/
```

---

## 環境變數

完整範例見 [`.env.example`](.env.example)。

| 變數 | 必填 | 預設 | 說明 |
|------|------|------|------|
| `LLM_BASE_URL` | ✅ | `https://api.openai.com/v1` | OpenAI-compatible 端點 |
| `LLM_API_KEY` | ✅ | — | API 金鑰 |
| `LLM_MODEL` | ✅ | `gpt-4o-mini` | 模型名稱 |
| `LLM_TIMEOUT` | | `60` | LLM 逾時（秒） |
| `GRAPHRAG_DB_TYPE` | | `sqlite` | `sqlite` 或 `postgresql` |
| `GRAPHRAG_SQLITE_PATH` | | `/app/data/graphrag.db` | SQLite 資料庫路徑 |
| `FDA_API_BASE` | | `https://api.fda.gov` | FDA API 基底 URL |
| `FDA_CACHE_TTL_DAYS` | | `30` | 快取有效天數 |
| `HTTP_PORT` | | `8000` | HTTP server port |

**LLM 端點範例：**

```bash
# OpenAI
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# Gemini（OpenAI-compatible）
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_MODEL=gemini-2.0-flash

# Ollama（本地）
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3
```

---

## MCP 工具

### `drug_check_safety`

查詢多種藥品的交互作用。首次查詢未快取的藥品時自動擷取 FDA 資料（懶加載）。

| 參數 | 類型 | 預設 | 說明 |
|------|------|------|------|
| `drugs` | `string[]` | **必填** | 英文通用名稱（1–10 種，如 `aspirin`、`warfarin`） |
| `severity_filter` | `string` | `all` | `all`、`major`、`moderate+` |
| `auto_fetch` | `boolean` | `true` | 未快取藥品是否自動呼叫 FDA API |

```bash
# REST API 呼叫範例
curl -X POST http://localhost:8000/api/v1/tool \
  -H "Content-Type: application/json" \
  -d '{"name": "drug_check_safety", "arguments": {"drugs": ["warfarin", "aspirin"]}}'
```

### `drug_ingest_fda`

手動觸發 FDA 資料擷取，適用於批次預載或強制更新。

| 參數 | 類型 | 預設 | 說明 |
|------|------|------|------|
| `generic_names` | `string[]` | **必填** | 英文藥品通用名稱列表 |
| `force_refresh` | `boolean` | `false` | 忽略快取強制重新查詢 |
| `limit` | `integer` | `50` | 最多處理幾種藥品（最大 500） |

---

## 懶加載機制

`drug_check_safety` 呼叫時，若目標藥品尚未快取：

1. 查詢 `graphrag_fetch_log`（TTL=30 天）
2. 呼叫 FDA API：`/drug/label.json?search=openfda.generic_name:"藥名"`
3. LLM 萃取 `drug_interactions` 原文 → 結構化 JSON
4. 寫入 SQLite（`graphrag_drug_entities` + `graphrag_drug_interactions`）
5. 更新 `graphrag_fetch_log`

**降級行為：**

| 情境 | 處理 |
|------|------|
| FDA 404 | 記錄 `not_found`，回傳無資料提示 |
| FDA 429 / 5xx | 指數退避，最多重試 3 次 |
| LLM 萃取失敗 | 記錄 `error`，不寫圖譜 |

---

## 執行測試

```bash
# 安裝開發依賴
pip install -e ".[dev]"

# 執行全部測試
pytest tests/ -v

# 個別測試
pytest tests/unit/test_fda_client.py     # FDA 客戶端（含 mock）
pytest tests/unit/test_name_resolver.py  # 藥名正規化
pytest tests/unit/test_ingestion.py      # Ingestion pipeline
```

---

## PostgreSQL 模式（選用）

SQLite 為預設，若需要多副本部署或持久化需求可切換至 PostgreSQL：

```bash
GRAPHRAG_DB_TYPE=postgresql
GRAPHRAG_PG_HOST=localhost
GRAPHRAG_PG_PORT=5432
GRAPHRAG_PG_NAME=mcp_fda
GRAPHRAG_PG_USER=your_user
GRAPHRAG_PG_PASSWORD=your_password
```

首次啟動需執行建表腳本：

```bash
python scripts/init_graphrag_db.py
```

---

## 開源授權

本專案以 [MIT License](LICENSE) 釋出，歡迎自由使用、修改與散布。

```
MIT License

Copyright (c) 2026 BrightSu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

**版本**：v1.0.0 | **最後更新**：2026-04-16
