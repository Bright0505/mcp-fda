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
| mcp-fda `main`(本機/遠端) | `10b1f54`,本機已用 `git push` 推上 `origin/main`,GitHub API 查證過真的落地(這次 HANDOFF.md 更新完會再領先 1 個 commit) |
| mcp-fda 目前分支 | `main`,工作目錄乾淨;remote 已切成 HTTPS;`chore/add-claude-sandbox`、`chore/dedupe-known-issues-checker` 兩條分支經 GitHub API 查證已不存在於遠端(不是這次刪的,推測是合併時 GitHub 自動清掉,未證實) |
| `pytest` | **31 passed**(45 − 14,刪掉重複邏輯測試後的數字,已驗證對得上) |
| `check_known_issues_links.py` | 已改成單一來源:`claude-sandbox/.claude/skills/record/scripts/check_known_issues_links.py` |
| sandbox PR #2–#9 | **全部已合併**(GitHub API 查證過) |
| sandbox `main` | `1381c0c` |

---

## 下一步

### 已完成(2026-08-07):容器內 git/gh 認證,GH_TOKEN 接線通了

**結論**:HTTPS + fine-grained PAT 這條路**通**,讀、寫(push)都用真實動作驗證過,
GitHub API 交叉查證過結果不是只信 CLI 訊息。

**開工前環境檢查**(這次沒有卡住,直接往下做):

```
$ [ -n "$GH_TOKEN" ] && echo "GH_TOKEN set" || echo "GH_TOKEN NOT set"
GH_TOKEN set
$ gh auth status
github.com
  ✓ Logged in to github.com account Bright0505 (GH_TOKEN)
  - Active account: true
  - Git operations protocol: https
$ uptime
 07:35:02 up 2 days,  2:25, ...
```

`uptime` 仍顯示 2 天(不是剛重建的新容器),但 `GH_TOKEN` 已經生效——
代表這次不是靠「重建容器」讓 `env_file` 生效,實際機制是什麼**無法從現有證據判定**
(不編造原因,鐵則5)。只記錄現象:這次環境已就緒,可以照原計畫往下走。

**做了什麼**:

1. `git remote set-url origin https://github.com/Bright0505/mcp-fda.git`、
   `git -C claude-sandbox remote set-url origin https://github.com/Bright0505/claude-code-sandbox.git`、
   `gh auth setup-git`——三個指令都無輸出無錯誤,`git remote -v` 復查兩個 repo
   都已經是 `https://...` 形式
2. 讀測試:`git ls-remote origin` 兩個 repo 各跑一次,都成功回傳 `refs/heads/main`
   等 ref 清單(mcp-fda 在 `f62352a`,claude-sandbox 在 `1381c0c`,跟 HANDOFF.md
   之前記的狀態速覽一致)
3. 寫測試(真實待辦,不是空推):`git push origin main`(mcp-fda,本機領先
   3 個 commit `a57844d`/`9fc076a`/`10b1f54`)→ 成功,輸出
   `f62352a..10b1f54  main -> main`
4. 刪分支測試:`git push origin --delete chore/add-claude-sandbox
   chore/dedupe-known-issues-checker` → **失敗**,`error: unable to delete
   ...: remote ref does not exist`——查了一下,前一步 `ls-remote` 的輸出裡
   本來就沒看到這兩條分支,代表它們在這次操作之前就已經不在遠端了(合理推測
   是 PR #1/#2 合併時 GitHub 自動刪除分支,但這只是推測,沒有直接證據,
   不寫成結論)。**delete 權限這次沒有真正測到**,因為沒有活著的目標可刪
5. GitHub API 交叉驗證(不只信 git/gh CLI 的成功訊息):
   - `GET /repos/Bright0505/mcp-fda/commits?sha=main` → 回傳的第一筆
     `sha` 就是 `10b1f5420ccd63b9a58c1f8aa8fa628b2a30a9e1`,commit message
     跟本機一致,**確認 push 真的落地在遠端**
   - `GET /repos/Bright0505/mcp-fda/branches` → 只列出 `main` 一條,
     **確認 `chore/add-claude-sandbox`、`chore/dedupe-known-issues-checker`
     確實不存在**於遠端(不論是不是這次刪的)

**沒做什麼**:
- 沒有驗證到「刪分支」的寫入權限本身——目標分支本來就已經不存在,這次操作
  只證明了 CLI 對「刪不存在的 ref」的錯誤回報行為,不能當作 delete 權限已驗證。
  之後如果要真的驗 delete 權限,需要另外造一條測試分支
- 只對 mcp-fda 做了 push(寫入)測試,claude-sandbox 這邊只做了 `ls-remote`
  讀測試,沒有做寫入測試(沒有真實待辦需要推,不無中生有造一個)
- 沒有回答「這次 GH_TOKEN 為什麼生效、容器到底有沒有重建」——現象記錄了,
  原因無法從現有證據判定,留給使用者或下一個 session 有新證據時再補

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
