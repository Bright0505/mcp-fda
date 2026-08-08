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

### K-4 `mcp` 相依沒有版本上限,今天全新安裝直接壞掉

- **影響範圍**：`pyproject.toml`(`dependencies` 的 `mcp` 這行)、
  `src/server.py`、`src/http_server.py`、`src/protocol/base_server.py`
  (三個入口檔案都用同一種 handler 註冊寫法)
- **狀態**：已修（無守備）—— 已加上版本上限,症狀確認消失,但沒有任何
  測試守住這個入口層(見下方判準第 2 點),所以**上限被鬆綁或移除的話,
  這個問題會原樣復發而不會被 CI 抓到**
- **症狀**：`pyproject.toml` 原本宣告 `mcp>=1.13.1`,沒有上限。實測:乾淨
  環境 `pip install -e ".[dev]"` 裝出來的是 `mcp==2.0.0`,接著
  `from mcp.server import Server; Server("x").list_tools()` 直接
  `AttributeError: 'Server' object has no attribute 'list_tools'`。
  `src/server.py`、`src/http_server.py`、`src/protocol/base_server.py`
  三個對外入口都用 `@server.list_tools()` 這種 decorator 註冊 handler,
  全部會在啟動時炸掉
- **根因**：`mcp` SDK 從 1.x 到 2.0.0(2026-07-28 發布)是官方明文的
  breaking change 大版號跳動——低階 `Server` 整個重寫,decorator 式
  handler 註冊改成建構子傳 `on_list_tools=` 等 callback。`pyproject.toml`
  沒有上限,加上沒有 lockfile,所以「今天裝出來是什麼版本」完全取決於
  安裝當下 PyPI 上有什麼,不是取決於這個 repo 的任何一次 commit
- **判準**：
  1. 浮動下限(`>=x.y.z` 沒有上限)在相依套件發生 breaking major bump 時,
     會讓「同一份 `pyproject.toml`」在不同時間點裝出行為完全不同的東西——
     改動或稽核相依版本前,先實際裝一次、量測解出來的版本,不要只讀
     `pyproject.toml` 推論
  2. `pytest` 31 passed 跟這個 bug 完全共存過——現有測試套件對
     `server.py`/`http_server.py`/`protocol/base_server.py` 這三個入口
     檔案零覆蓋,綠燈不代表這一層沒事
  3. 這只是**暫時擋血**(釘 `mcp>=1.13.1,<2`),不是遷移到 v2 API。
     真的遷移是規模更大的獨立任務,見 `docs/tasks/`(待建檔)
- **關聯**：（無)
- **日期**：2026-08-08
