# 交接:現在到哪、下一步是什麼

**最後更新**:2026-08-07
**主線任務**:`docs/tasks/2026-08-06-sandbox-落地與實測.md`(完整脈絡在那)

> 這份是入口,只講「現在的狀態」與「接下來做什麼」。
> 為什麼這樣決定 → 看主線任務檔;規範本身的決議 → 看 `claude-sandbox/docs/DECISIONS.md`。

---

## 已完成(這次交接前的收尾工作)

1. **容器重建後假刪除消失,確認完畢**——K-3 的 mount 覆蓋修正生效,
   `scripts/` 恢復可寫。細節見 `docs/KNOWN-ISSUES.md` 的 **K-3**
2. **sandbox `fix/drop-scripts-runtime-mount` 分支已 push、PR #9 已合併**
   (GitHub API 查證,merge commit `1381c0c`),容器內 `claude-sandbox` 已同步到這個
   commit
3. **mcp-fda submodule 指標已更新並 commit**(指向 `1381c0c`),連同 K-3 紀錄、
   D7 腳本+測試、任務文件,分四個 commit 提交,開 PR #1 並已合併進 `main`
4. **mcp-fda 自己的 `tools/check_known_issues_links.py` 已刪除**,改用
   submodule 版本(兩份逐行比對過,程式碼一致)。測試檔只留對照真實
   `docs/KNOWN-ISSUES.md` 的整合測試,其餘 14 則邏輯測試刪除(submodule 自己的
   14 則 unittest 已覆蓋)。改動在分支 `chore/dedupe-known-issues-checker` 上,
   已 push、開 PR #2、**已合併進 `main`**(GitHub API 查證,merge commit
   `f62352a`)
5. **HANDOFF.md 同步現況(commit `a57844d`)+ 清掉本機已合併的分支**
   (`chore/add-claude-sandbox`、`chore/dedupe-known-issues-checker`,用
   `git branch -d` 安全刪除,git 自己確認過完全合併才刪成功);遠端同名分支
   還在,留給主機端 `git push origin --delete` 清
6. **稽核既有 skill(`deliver`／`verify`／`traps`)建立時的證據**,結論:
   三個建立 commit(`e8e0001`／`b2bbe99`／`7f37e14`)都真的存在於
   `claude-sandbox` 歷史裡,`SKILL.md` 內容也確實是具體案例而非空泛條列。
   但 `verify` skill 舉的「D7 腳本抓到 2 個真邏輯錯」這個實例,`check_known_issues_links.py`
   的 commit 歷史**只有一個 squash commit**(`5a72f6a`),抓到 2 個真錯的
   「先紅後綠」過程沒有留下獨立 commit 可查——這句話目前只能算任務檔自述,
   不是能反查的一手證據。已補查到對應測試 `test_partial_archive_breaks_atomicity`
   確實存在且通過,教訓確實落地成可執行的迴歸測試,只是「證據鏈的其中一段」不完整。
   **不需要動作**,只是記下這個查證結果,供之後判斷同類 skill 引用的可信度時參考

---

## 目前狀態速覽

| 項目 | 狀態 |
|---|---|
| mcp-fda `main`(本機) | `a57844d`,領先 `origin/main` 1 個 commit(HANDOFF.md 同步,尚未 push) |
| mcp-fda 目前分支 | `main`,工作目錄乾淨;本機已合併分支已清空,遠端兩條同名分支還在等主機端刪 |
| `pytest` | **31 passed**(45 − 14,刪掉重複邏輯測試後的數字,已驗證對得上) |
| `check_known_issues_links.py` | 已改成單一來源:`claude-sandbox/.claude/skills/record/scripts/check_known_issues_links.py` |
| sandbox PR #2–#9 | **全部已合併**(GitHub API 查證過) |
| sandbox `main` | `1381c0c` |

---

## 下一步

### 進行中(2026-08-07):容器內 git/gh 認證,方向已定案,等主機端動作

**定案的方向**:改用 `GH_TOKEN`(fine-grained PAT)走 HTTPS,不裝 ssh。

**已量測、排除掉的方向**:在容器裡裝 `ssh` client——量過是死路,原因兩層都獨立成立:
1. 容器是非 root(`whoami` → `claude`),`apt-get update` 回
   `Permission denied: /var/lib/apt/lists`,裝不了系統套件
2. 就算能裝,`claude-sandbox/scripts/init-firewall.sh` 的白名單只開放
   tcp/443、tcp/80 給允許的網域,**沒開 port 22**,SSH transport 連不出去

**範圍已跟使用者確認**:先只接**這一個容器**,不動 `claude-sandbox` 本體
(不改 `.env.claude.example`、不改 `entrypoint.sh` 自動偵測 `GH_TOKEN`)。
之後這條路驗證可靠了,要不要回饋成 sandbox 標準功能,留給下一次決定。

**分工**(見對話紀錄,`docker-compose.claude.yml` 的 `env_file: .env.claude`
是既有機制,`.env.claude` 已 gitignore):

| 步驟 | 內容 | 誰做 |
|---|---|---|
| 1 | GitHub 建 fine-grained PAT,只授權 `mcp-fda`、`claude-code-sandbox` 兩個 repo,權限只給 Contents + Pull requests 的 read/write | 使用者(GitHub 網站) |
| 2 | `GH_TOKEN=...` 寫進 `claude-sandbox/.env.claude` | 使用者(主機端) |
| 3 | 重建容器讓 `env_file` 生效 | 使用者(主機端) |
| 4 | 容器內把兩個 repo 的 remote 從 SSH 改成 HTTPS、`gh auth setup-git`、用 `gh auth status`+ 一次真的 push 驗證 | 我(下一個能存取到已重建容器的 session) |

**⚠️ 交接斷點,下一個 session 開工前必查**:使用者說「已經開新 session、狀態轉過去了」,
但在**這個**執行環境裡實測(2026-08-07)——`echo $GH_TOKEN` 是空的、`gh auth status`
未登入、容器 `uptime` 顯示 2 天(不是剛重建的新容器)、git remote 仍是
`git@github.com:...`。**代表步驟 1-3 尚未反映在這個環境裡**——不確定是
「新 session 接的是另一個真的重建過的容器」還是「步驟 1-3 其實還沒做完」。
**下一個 session 進來後,先重跑這組檢查**,確認 `GH_TOKEN` 真的有值、
`gh auth status` 是登入狀態,才能往下走第 4 步,不要假設使用者說的「轉移過去了」
等於環境已經就緒(鐵則1、2、9)。

```bash
[ -n "$GH_TOKEN" ] && echo "GH_TOKEN set" || echo "GH_TOKEN NOT set"
gh auth status
uptime
```

### 尚未做的工作

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
   `git -c user.name="..." -c user.email="..." commit`——具體身分不寫死在這份文件裡
   (避免 email 明文進版控),要用的話跟使用者要
3. **`claude-sandbox` 是獨立 repo**,它的 `main` 一樣受禁令 1 保護,要開自己的分支
4. 更多見 `claude-sandbox/.claude/skills/traps/SKILL.md`
