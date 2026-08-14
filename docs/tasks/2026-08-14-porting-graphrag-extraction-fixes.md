# 任務：把 mcp-drug 的 GraphRAG 萃取修正移植到 mcp-fda

**建立日期**：2026-08-14
**狀態**：未開始
**交接來源**：mcp-drug 的萃取管線修正（同日完成並驗證）

> 📍 **路徑說明**：本文提到的 `modules/mcp-drug/...` 是**主 repo 工作區**的路徑
> （`/workspace/modules/mcp-drug/`）。若你只 clone 了 mcp-fda 這個 repo 就讀不到，
> 需要在主 repo 的工作區作業。

---

## 背景

`modules/mcp-drug` 的 GraphRAG 萃取管線有三個缺陷，會把 FDA 仿單裡**本來就有的**
保健食品／草藥交互作用資料丟掉。已於 2026-08-14 修好並驗證。

`modules/mcp-fda` 的 `src/graphrag/extractor.py` 與 mcp-drug **修改前完全同源**
（差異只有「美國 FDA」vs「FDA」的字串），三個缺陷一字不差地都存在：

```
extractor.py:21   "drug_2": "交互作用的另一種藥品名"
extractor.py:33   4. 若無明確藥品名，略過（不要生成空白 drug_2）
extractor.py:69   f"FDA drug_interactions 原文:\n{interaction_text[:4000]}"
```

**你的任務是把修正移植過去。**

---

## 必讀

**`modules/mcp-drug/docs/graphrag-extraction-fixes.md`** — 完整技術紀錄：

| 節 | 內容 |
|---|---|
| §2 | 三個缺陷與量化證據 |
| §3 | 修法與取捨（含走過的彎路） |
| §4 | 實測結果 |
| §5 | 已評估但**不做**的優化（規則過濾，別重想一次） |
| **§6** | **移植檢查清單** |
| §7 | 殘留問題 |

參考實作：mcp-drug 分支 `feature/supplement-interaction-extraction`
（commit `f996239`、`16a8a12`、`c23602e`、`498144a`）

---

## 三個缺陷摘要

1. **原文截斷**：`interaction_text[:4000]`。實測 16 個常見藥平均 6,377 字元，
   **63% 被截**；Sertraline 漏 83%。`St. John's Wort` 在 Digoxin 原文第 ~4,400
   字元處，永遠讀不到。
   → 修法：分段（`CHUNK_CHARS=2200` + `CHUNK_OVERLAP=300`），不截斷。

2. **prompt 只講「藥品」**：LLM 讀到「另一種**藥品**名」，看到 `St. John's Wort`
   就判定「不是藥品」而略過；規則 4 更是明確授權它跳過。
   → 修法：範圍改為「另一個物質名稱」，新增 `entity_type`
   （`drug` / `supplement` / `food` / `class`）。

3. **輸出也會截斷**：仿單常寫「以下藥物皆會影響本藥」後接一長串藥名，
   **輸出比輸入長**。
   → 修法：`max_tokens=8192` ＋ 偵測截斷時**遞迴細分該段重跑**（最多兩層，
   低於 600 字元不再細分）＋ `_salvage()` 安全網。

   ⚠️ 走過的彎路：第一次只設 `max_tokens=4096`，結果**更糟**（總筆數 67 → 28）。
   段落大小與輸出上限必須**一起調**。

---

## 四個實作上的坑（都踩過，讀程式碼看不出來）

- ⚠️ **`semaphore` 只能包住 LLM 呼叫本身，不能包住遞迴**
  否則細分產生的子呼叫會等待一個永遠不會被釋放的名額而**死鎖**。
  把呼叫抽成 `call_llm()`，semaphore 只在其中持有。

- ⚠️ **`_salvage()` 必須檢查任何巢狀深度的物件**
  截斷時最外層 wrapper 的 `{` 永遠不閉合，只看 `depth == 0` 會**一筆都救不到**。
  用堆疊記錄每個 `{` 的位置。（第一版就是這樣寫錯的。）

- ⚠️ **`sqlite_store.py` 內嵌了一份自己的 schema**
  實際建表用的是它，不是 `schema/` 目錄那份。**兩邊都要改**。

- ⚠️ **`CREATE TABLE IF NOT EXISTS` 對既有 DB 不會加欄位**
  要寫 `_migrate()`（`PRAGMA table_info` 檢查後 `ALTER TABLE ADD COLUMN`），
  否則既有部署會在 INSERT 時噴 `no such column`。

---

## mcp-fda 的關鍵差異：先確認再動手

**mcp-fda 抽離了內部資料**，沒有 `drug_permits` 白名單。因此：

- [ ] `local_whitelist` 相關邏輯與 `name_resolver` 的行為可能不同 —— **先讀過再改**
- [ ] 確認 store 層是否同樣有 sqlite／postgres 雙實作
- [ ] 這可能是**好事**：沒有反查白名單，就沒有 mcp-drug 那個
      `Biotin（"盈盈"膚麗敏膠囊）`、`Calcium（→ 靜脈注射鈣劑）` 的污染問題
      （見技術紀錄 §7）

---

## 驗收

**標竿：Digoxin**（真實 FDA 原文 6,971 字元）

| | 修改前 | 應達到 |
|---|---|---|
| 萃取筆數 | 圖譜 5 個對象 | **80+ 筆** |
| `St. John's Wort` | ❌ | ✅ 且 `entity_type=supplement` |
| 截斷 | 靜默丟棄整段 | 日誌無「無法救回」 |

跑單元測試，並**記錄哪些是既有失敗** —— 用 `git stash` 掉自己的改動對照一次，
不要把既有問題當成自己造成的（mcp-drug 那邊的 `test_validators.py` 就是這種情況）。

---

## 環境須知

- **sandbox 內沒有 docker** —— rebuild 容器要請使用者在 host 做
- **測試環境要自建 venv**：
  ```bash
  python3 -m venv v && ./v/bin/pip install pytest pytest-asyncio httpx \
    python-dotenv "mcp==2.0.0" asyncpg pandas fastapi slowapi \
    psycopg2-binary tenacity chromadb openai aiosqlite
  ```
- **LLM 設定在 `.env`**，變數名是 `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY`
  （**不是** compose 裡的 `LITELLM_*`，那組是別的用途）。跑萃取前要載入：
  ```bash
  set -a && . <(grep -E "^LLM_(BASE_URL|MODEL|API_KEY|TIMEOUT)=" /workspace/.env) && set +a
  ```
- `api.fda.gov` 需要 sandbox 防火牆放行（白名單只有 Anthropic／GitHub／npm／PyPI）

---

## 邊界

- **不要碰 `modules/mcp-health-products`** —— 另一個 session 正在處理保健諮詢那條線
- **不要碰 `name_resolver` 的比對邏輯** —— 該路線已量化**誤傷率 84%**
  （改成 token 精確比對會打斷 `ACETAMINOPHEN` 等最常見查詢，因為台灣仿單普遍
  記載鹽類與純度形式）。證據見主 repo
  `docs/health-products-consultation-upgrade/interaction-data-sources.md` §7
- **開新分支**，不要在 `main` 上 commit
- **不要自動 push**
- commit 訊息**不加 Claude 署名**
