# 交接:現在到哪、下一步是什麼

**最後更新**:2026-08-07(容器重建前寫的)
**主線任務**:`docs/tasks/2026-08-06-sandbox-落地與實測.md`(完整脈絡在那)

> 這份是入口,只講「現在的狀態」與「接下來做什麼」。
> 為什麼這樣決定 → 看主線任務檔;規範本身的決議 → 看 `claude-sandbox/docs/DECISIONS.md`。

---

## 第一件事:確認容器重建後,假刪除消失了

上一個 session 卡在這裡不能交付。根因是 `claude-sandbox/docker-compose.claude.yml`
原本有一行 `./scripts:/workspace/scripts:ro`,跟前一行的大範圍 mount 路徑重疊,
**把本專案的 `scripts/` 整個遮住**,導致 `git status` 誤報檔案被刪除。
完整說明見 `docs/KNOWN-ISSUES.md` 的 **K-3**。

修正已經在 `claude-sandbox` 的 `fix/drop-scripts-runtime-mount` 分支上(commit `650acef`)。
**這是 volume 設定,不需要 `docker build`,重新建立容器(`down` + `up`)就會生效。**

重建後第一件事,跑:

```bash
git status --short
```

**預期會消失的四行**(它們全都是遮蔽造成的假象):

```
 D scripts/init_graphrag_db.py     ← 假刪除,檔案其實還在
 D scripts/seed_fda.py             ← 假刪除,檔案其實還在
?? scripts/entrypoint.sh           ← 不屬於本專案,是 sandbox 的檔案被掛進來
?? scripts/init-firewall.sh        ← 同上
```

**預期會留下的**(這些是真的、要保留的工作成果):

```
 M claude-sandbox                  ← submodule 指標,見下方
 M docs/KNOWN-ISSUES.md            ← K-2 標已推翻、新增 K-3
 M docs/tasks/2026-08-06-sandbox-落地與實測.md
?? docs/tasks/HANDOFF.md           ← 本檔
?? tests/unit/test_check_known_issues_links.py
?? tools/
```

- **四行都消失** → 修正生效,可以往下走
- **還在** → 不要 commit。先查 `mount | grep workspace` 確認掛載狀態,
  可能是容器沒真的重建、或用到了舊的 compose 檔

---

## 目前狀態速覽

| 項目 | 狀態 |
|---|---|
| mcp-fda 分支 | `chore/add-claude-sandbox`(不是 main,可以 commit) |
| `pytest` | **45 passed**(重建後請重跑一次確認) |
| `tools/check_known_issues_links.py` | exit 0(兩筆「需要人判斷」的提示是 K-3 的遮蔽現象本身,重建後應該會消失) |
| sandbox PR #2–#8 | **全部已合併**(GitHub API 查證過) |
| sandbox `main` | `ee63fb4` |
| sandbox 目前 checkout | `fix/drop-scripts-runtime-mount`(`650acef`)—— **尚未 push** |
| mcp-fda submodule 指標 | 還釘在舊的 `3846eac`,**尚未更新**(刻意留到最後) |

---

## 下一步(照順序)

### 1. 推送並合併最後一個 sandbox 分支

這個環境**沒有 ssh client、`gh` 沒登入**,push 要在主機端做(容器裡的 commit
已經真實存在於主機檔案系統,因為 `/workspace` 是 bind mount):

```bash
cd <mcp-fda 專案目錄>/claude-sandbox
git push -u origin fix/drop-scripts-runtime-mount
gh pr create --base main --head fix/drop-scripts-runtime-mount \
  --title "fix: 移除 docker-compose 的 scripts/ runtime mount"
```

合併後在容器裡可以用 HTTPS 同步(公開 repo 讀取不需要認證):

```bash
cd /workspace/claude-sandbox
git fetch https://github.com/Bright0505/claude-code-sandbox.git main:refs/remotes/origin/main
git checkout main && git merge --ff-only origin/main
```

### 2. 更新 submodule 指標並 commit

**⚠️ commit 時明確列檔名,不要用 `git add -A` / `git add .`**——
如果第一步的驗證沒過,那會把假刪除掃進去(K-3 的判準 2)。

```bash
cd /workspace
git add claude-sandbox docs/KNOWN-ISSUES.md docs/tasks/ tests/unit/test_check_known_issues_links.py tools/
git status --short          # 再確認一次沒有 scripts/ 的假刪除
```

commit 訊息要分開(禁令 6:一個 commit 不混不同性質的改動)——
submodule 指標更新、KNOWN-ISSUES 紀錄、D7 腳本+測試,是三件不同的事。

### 3. 尚未做的工作

| 項目 | 狀態 |
|---|---|
| 主線任務「下一步」表第 5 項:決定 MCP spec 升級的強度與計畫 | **未開始**。量測結果已備妥,見主線任務檔「已量到的事實」第 4、5 條 |
| `code` skill | 未建立(sandbox 觸發表唯一還沒建的;先前判斷這次沒有獨有素材) |
| D1-1 歸檔觸發訊號數值、D1-2 archive 組織方式、D7 漏連結啟發式 | 卡在樣本不足(目前只有 `K-1`~`K-3`),不是現在能解的 |
| `K-1`(`requires-python` 過期) | 未處理。使用者決定留給 MCP 升級任務一起判斷,不單獨修 |

---

## 這個環境的已知陷阱(會浪費時間的)

1. **沒有 `ssh`**,所以 `git push` / `git fetch` 走 SSH 會失敗。
   但**公開 repo 走 HTTPS 讀取完全不需要認證**——不要因為 push 不了就以為讀也不行
2. **不要動 git config**(local 或 global 都不行)。缺身分時用
   `git -c user.name="..." -c user.email="..." commit`,這個 workspace 用的是
   `bright0505 <gt07814@greattree.com.tw>`
3. **`claude-sandbox` 是獨立 repo**,它的 `main` 一樣受禁令 1 保護,要開自己的分支
4. 更多見 `claude-sandbox/.claude/skills/traps/SKILL.md`
