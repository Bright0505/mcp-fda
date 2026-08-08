# 事故紀錄

這個專案踩過的坑。**不是待辦清單** —— 待辦在 issue tracker,這裡記「下一個碰到這塊的人,
不知道這件事會不會出事」。

改任何檔案前先用檔名和功能名各 `grep` 一次:

```bash
grep -n "fda_client" docs/KNOWN-ISSUES.md
grep -n "交互作用" docs/KNOWN-ISSUES.md
```

條目格式、狀態、ID 規則、歸檔規則見 `claude-sandbox/.claude/skills/record/SKILL.md`。

---

### K-1 `requires-python` 下限過期,實際依賴需要 3.10+

- **影響範圍**：`pyproject.toml`(`requires-python`、`[tool.black]` 與 `[tool.ruff]` 的 `target-version`)
- **狀態**：未處理
- **症狀**：`pyproject.toml:12` 宣告 `requires-python = ">=3.8"`,`target-version = py38`
  (第 51、57 行),但已安裝的 `mcp` 2.0.0 實際宣告 `Requires-Python: >=3.10`
  (`importlib.metadata.metadata('mcp').get('Requires-Python')` 量到)。
  在 Python 3.8/3.9 環境下 `pip install` 不會報錯,pip 解析器會靜默回退安裝遠舊於
  2.0.0 的 `mcp` 版本,沒有任何警告
- **根因**：`mcp` SDK 某個版本起把最低 Python 版本提到 3.10+,`pyproject.toml`
  沒有跟著更新(浮動下限 `mcp>=1.13.1`,沒有 lockfile,所以裝到哪個版本取決於安裝環境)
- **判準**：改 `mcp` 版本或做 spec 升級前,先跑 `pip show mcp` 與
  `importlib.metadata.metadata('mcp').get('Requires-Python')` 量測實際下限,
  不要只讀 `pyproject.toml` 推論實際會裝到哪個版本
- **關聯**：（無)
- **日期**：2026-08-06

### K-2 `scripts/` 目錄在沙盒環境裡是唯讀掛載,無法新建/修改檔案

- **影響範圍**：`scripts/`(整個目錄,含 `scripts/entrypoint.sh`、`scripts/init-firewall.sh`)
- **狀態**：**已推翻(2026-08-07)** —— 症狀屬實,但根因判斷錯了,見下方推翻說明。
  原文完整保留(禁令 8)。原本標的狀態是「已知未修(刻意的沙盒防護,不是要修的缺陷)」
- **症狀**：在 `scripts/` 下 `Write`/`touch` 任何檔案都得到
  `EROFS: read-only file system`;`mount` 顯示
  `/run/host_mark/Users on /workspace/scripts type fakeowner (ro,...)`,
  而 `/workspace` 本身與其他子目錄(`docs/`、`tests/`、`src/`)都是 `rw`
- **根因**：只有 `scripts/` 被掛成唯讀,推測是因為裡面放了沙盒啟動用的
  `entrypoint.sh`／`init-firewall.sh`,刻意防止 agent 改動沙盒的啟動/防火牆設定
- **判準**：要新建與 `scripts/` 無關的維護用腳本(例如檢查文件結構的工具),
  改放別的目錄(這次選了新建的 `tools/`),不要嘗試 remount 或用 sudo 繞過——
  這是沙盒的刻意邊界,不是要排除的障礙
- **關聯**：被 K-3 取代
- **日期**：2026-08-06

**推翻說明(2026-08-07)**:上面的**症狀描述完全正確**(`EROFS`、mount 顯示唯讀),
但**根因判斷錯了**,而且錯得有方向性:

- 原本寫「刻意防止 agent 改動沙盒的啟動/防火牆設定」——動機猜對了,
  但實際效果相反。實測發現被鎖住的 `/workspace/scripts` 是**本專案(mcp-fda)
  自己的** `scripts/`,而 sandbox 真正想保護的那份在
  `/workspace/claude-sandbox/scripts/`,**實測可寫、完全沒被保護到**
- 原本的判準「這是沙盒的刻意邊界,不是要排除的障礙」因此也是錯的——
  它是一個 bug,已在 sandbox 修掉(`docs/DECISIONS.md` D10)
- **這則條目本身是「查證不足就下根因」的實例**:當時用了「推測是因為」的措辭
  誠實標示不確定,但仍然把推測寫進了判準。正確做法是當下就去查
  `docker-compose.claude.yml`,那裡一行就能看出真正原因

實際根因與正確判準見 **K-3**。

### K-3 sandbox 的 volume mount 蓋掉本專案的 `scripts/`,git 誤報成「檔案被刪除」

- **影響範圍**：`scripts/`(含 `scripts/init_graphrag_db.py`、`scripts/seed_fda.py`)、
  `claude-sandbox/docker-compose.claude.yml`、任何在容器裡下的 `git status`/`git add`
- **狀態**：已修（無守備）—— 上游 sandbox 已移除該行
  (見 `claude-sandbox/docs/DECISIONS.md` D10),但這是 docker volume 設定,
  沒有測試守得住,所以**它可能回來**(例如有人為了別的理由再加一個重疊的 mount)。
  **本專案要等 submodule 指標更新 + 重建容器才會實際生效**
- **症狀**：容器裡 `git status` 顯示
  `deleted: scripts/init_graphrag_db.py`、`deleted: scripts/seed_fda.py`,
  但這兩個檔案在主機上還在。同時 `/workspace/scripts` 底下出現的是
  `entrypoint.sh`、`init-firewall.sh` 這兩個**不屬於本專案**的檔案
- **根因**：`claude-sandbox/docker-compose.claude.yml` 原本第 12 行
  `- ./scripts:/workspace/scripts:ro` 跟第 11 行 `- ${WORKSPACE_DIR:-.}:/workspace`
  路徑重疊。Docker 依序疊加 volume,後者蓋掉前者,所以本專案的 `scripts/`
  被 sandbox 自己的 `scripts/` 整個遮住。
  證據:`diff /workspace/scripts/entrypoint.sh /workspace/claude-sandbox/scripts/entrypoint.sh`
  → exit 0(位元相同,證明看到的是 sandbox 那份)
- **判準**:
  1. **在容器裡看到 `git status` 報「刪除」你沒動過的檔案時,先查 mount**
     (`mount | grep workspace`),不要直接 commit——那會把環境假象寫成真的破壞
  2. commit 時明確列檔名,**不要用 `git add -A` / `git add .`**,
     避免把這類假刪除掃進去
  3. 這類「宿主專案目錄被 submodule 的 volume 遮蔽」的形態,在任何
     `docker-compose` 有路徑重疊的 mount 時都可能發生,不限 `scripts/`
- **關聯**：取代 K-2(該則的症狀正確但根因判斷錯誤,已標為已推翻)
- **日期**：2026-08-07

> **附註**:在**尚未重建容器**的環境裡跑 `tools/check_known_issues_links.py`,
> 會對本則的「影響範圍」報兩筆「需要人判斷:找不到 `scripts/init_graphrag_db.py`
> / `scripts/seed_fda.py`」——**那不是條目寫錯,正是本則描述的遮蔽現象本身**。
> 容器帶著修正重建之後這兩筆會自動消失。若重建後仍然報,才代表那兩個檔案
> 真的不見了,那時要照判準去查。

### K-5 `test_ingestion.py` 塞進 `sys.modules` 的假模組沒清乾淨,污染同一個 pytest process 裡的其他測試

- **影響範圍**：`tests/unit/test_ingestion.py`(污染源)、任何在同一個
  `pytest` process 裡、在它之後才第一次真的 `import` 到
  `graphrag.store` 的測試(目前已知會中的是 `tests/unit/test_mcp_entrypoints.py`)
- **狀態**：未處理——這次(`2026-08-08-mcp-v2-遷移.md`)撞到但決定不修,
  理由見下方
- **症狀**：`test_mcp_entrypoints.py` 單獨執行(`pytest tests/unit/test_mcp_entrypoints.py`)
  **7 passed**,但跟全專案測試一起跑(`pytest`)會在 collection 階段炸掉:
  `ImportError: cannot import name 'get_store' from 'graphrag.store' (unknown location)`
- **根因**：`test_ingestion.py` 為了避免自己的單元測試碰到真的資料庫/向量
  儲存,執行了 `sys.modules.setdefault("graphrag.store", types.ModuleType("graphrag.store"))`
  塞一個空白假模組進 `sys.modules`(process 全域快取),測試結束後沒有清除。
  pytest 預設按字母序收集,`test_ingestion.py` 先跑,`test_mcp_entrypoints.py`
  (字母序在後)第一次真的走到 `graphrag_handler.py` 的
  `from graphrag.store import get_store` 時,拿到的是那個空白假模組
- **判準**：
  1. 這是既有問題,不是任何一次新改動造成的——只是在這次之前,完全沒有
     測試真的 import 過 `server.py` 這條會走到 `graphrag.store` 的鏈,
     所以這個全域污染從來沒被暴露過
  2. **這次刻意選擇不修**,不是漏掉:討論過「範圍外問題該記錄還是直接改」
     的判準,結論是預設記錄,只有「有邊界的嘗試性修復」證明真的是小範圍
     才直接修——這則還沒做過那個嘗試,先如實記錄,避免在跟這次任務不相關
     的檔案上開一個新的修改範圍
  3. 下一個要處理它的人:先只改 `test_ingestion.py` 的 `sys.modules` 清理
     方式(例如測試結束後還原、或改用 `monkeypatch.setitem` 讓 pytest
     自動復原),跑一次全專案 `pytest`。如果一次就綠燈,直接修掉；如果又
     扯出另一個不相干的失敗,停手退回這裡繼續只記錄
- **關聯**：（無)
- **日期**：2026-08-08
