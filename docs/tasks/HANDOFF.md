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
   14 則 unittest 已覆蓋)。改動在分支 `chore/dedupe-known-issues-checker`
   上,**尚未 push**

---

## 目前狀態速覽

| 項目 | 狀態 |
|---|---|
| mcp-fda `main` | 已同步到 `d1d2fa5`(PR #1 合併後),`git submodule status` → `1381c0c heads/main` |
| mcp-fda 目前分支 | `chore/dedupe-known-issues-checker`(不是 main,可以 commit),尚未 push |
| `pytest` | **31 passed**(45 − 14,刪掉重複邏輯測試後的數字,已驗證對得上) |
| `check_known_issues_links.py` | 已改成單一來源:`claude-sandbox/.claude/skills/record/scripts/check_known_issues_links.py` |
| sandbox PR #2–#9 | **全部已合併**(GitHub API 查證過) |
| sandbox `main` | `1381c0c` |

---

## 下一步

### 1. push `chore/dedupe-known-issues-checker` 並開 PR

跟之前一樣,容器裡沒有 ssh client,要在主機端做:

```bash
cd <mcp-fda 專案目錄>
git push -u origin chore/dedupe-known-issues-checker
gh pr create --base main --head chore/dedupe-known-issues-checker \
  --title "refactor: 刪除 mcp-fda 自己的 check_known_issues_links.py,改用 submodule 版本"
```

### 2. 尚未做的工作

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
