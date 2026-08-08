# 任務索引

按時間讀這裡的計畫檔,是了解「這塊以前為什麼做成這樣」最快的方式 ——
比讀 git log 或程式碼快,因為計畫檔有目標、範圍、假設與變更清單。

**完成後不刪不移動。**

> 📌 **接手中斷的工作,先讀 [HANDOFF.md](HANDOFF.md)** ——
> 那裡有「現在到哪、下一步是什麼」,以及這個環境已知會浪費時間的陷阱。

| 日期 | 任務 | 涉及範圍 | 一句話 |
|---|---|---|---|
| 2026-08-06 | [掛入 claude-sandbox 開發規範並實測](2026-08-06-sandbox-落地與實測.md) | 根 `CLAUDE.md`、`docs/`、`claude-sandbox/` submodule | 拿這個專案當規範的第一個真實案例,把踩到的問題回饋給 sandbox |
| 2026-08-08 | [遷移到 mcp SDK v2 API](2026-08-08-mcp-v2-遷移.md) | `pyproject.toml`、`src/server.py`、`src/http_server.py`、`src/protocol/base_server.py`、`tests/` | `K-4` 的長期解法:把 v1 decorator API 換成 v2 建構子 callback API |
