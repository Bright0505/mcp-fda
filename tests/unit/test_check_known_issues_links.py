"""驗證本專案的 docs/KNOWN-ISSUES.md 通過 D7 結構層檢查。

腳本邏輯本身(含 15 則故意壞掉的 fixture,驗證每種紅燈都抓得到)已回饋進
claude-sandbox 本體 `.claude/skills/record/scripts/check_known_issues_links.py`,
不在這裡重複維護——只留這一則對照真實內容的整合測試。
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(
    0, str(REPO_ROOT / "claude-sandbox" / ".claude" / "skills" / "record" / "scripts")
)

import check_known_issues_links as ckil  # noqa: E402


def test_real_repo_known_issues_has_no_structural_errors():
    """真實的 KNOWN-ISSUES.md 不應該有結構錯誤。

    只斷言 errors,**不斷言 notices**——notices 是「需要人判斷」的提示,
    取決於當下環境(例如 K-3 記錄的 volume 遮蔽會讓某些檔案暫時看不到),
    不是不變條件。初版誤把「當時剛好沒有 notice」寫成斷言,在 K-3 出現後
    轉紅;那不是程式錯,是測試過度指定。
    """
    known_issues = REPO_ROOT / "docs" / "KNOWN-ISSUES.md"
    archive = REPO_ROOT / "docs" / "known-issues-archive.md"  # 不存在
    errors, _notices = ckil.run_checks(known_issues, archive, REPO_ROOT)
    assert errors == []
