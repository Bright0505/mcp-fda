"""tools/check_known_issues_links.py 的結構層檢查測試。

每一種紅燈都用故意壞掉的 fixture 觸發一次,確認腳本真的抓得到
(鐵則 4:沒紅過的測試不算測試)。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import check_known_issues_links as ckil  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# ─── 對照真實 repo ───


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


# ─── 條目數斷言(直接測函式,不繞經真實解析器,因為這是防禦解析器本身的 bug)───


def test_entry_count_assertion_catches_parser_undercount():
    text = "### K-1 標題一\n- **狀態**：未處理\n\n### K-2 標題二\n- **狀態**：未處理\n"
    fake_entries = [ckil.Entry(id=1, title="標題一", fields={"狀態": "未處理"})]  # 故意少一則
    errors = ckil.check_entry_count(text, fake_entries)
    assert len(errors) == 1
    assert "條目數斷言失敗" in errors[0]


def test_entry_count_assertion_passes_when_counts_match():
    text = "### K-1 標題一\n- **狀態**：未處理\n"
    entries = ckil.parse_entries(text, source="main")
    errors = ckil.check_entry_count(text, entries)
    assert errors == []


# ─── 指向不存在的 K-n ───


def test_dangling_reference_detected(tmp_path):
    known_issues = write(
        tmp_path / "KNOWN-ISSUES.md",
        "### K-1 有壞掉的關聯\n"
        "- **影響範圍**：`foo.py`\n"
        "- **狀態**：未處理\n"
        "- **關聯**：與 K-99 同形態\n",
    )
    archive = tmp_path / "known-issues-archive.md"
    errors, _ = ckil.run_checks(known_issues, archive, tmp_path)
    assert any("K-99" in e and "不存在" in e for e in errors)


# ─── archive 連結指向不存在的檔案 ───


def test_archive_anchor_missing_file_detected(tmp_path):
    known_issues = write(
        tmp_path / "KNOWN-ISSUES.md",
        "## 已歸檔\n\n"
        "| ID | 一句話 | 影響範圍 | 明細 |\n"
        "|---|---|---|---|\n"
        "| K-1 | 測試用 | `foo.py` | [archive](known-issues-archive.md#k-1) |\n",
    )
    archive = tmp_path / "known-issues-archive.md"  # 故意不建立
    errors, _ = ckil.run_checks(known_issues, archive, tmp_path)
    assert any("K-1" in e and "不存在的檔案" in e for e in errors)


def test_archive_anchor_valid_no_violation(tmp_path):
    known_issues = write(
        tmp_path / "KNOWN-ISSUES.md",
        "## 已歸檔\n\n"
        "| ID | 一句話 | 影響範圍 | 明細 |\n"
        "|---|---|---|---|\n"
        "| K-1 | 測試用故障 | `foo.py` | [archive](known-issues-archive.md#k-1-測試用故障) |\n",
    )
    archive = write(
        tmp_path / "known-issues-archive.md",
        "### K-1 測試用故障\n- **狀態**：已修（無守備）\n",
    )
    errors, _ = ckil.run_checks(known_issues, archive, tmp_path)
    assert errors == []


# ─── 關聯群組原子性:一半在主檔、一半已歸檔 ───


def test_partial_archive_breaks_atomicity(tmp_path):
    known_issues = write(
        tmp_path / "KNOWN-ISSUES.md",
        "### K-1 還在主檔\n"
        "- **影響範圍**：`foo.py`\n"
        "- **狀態**：未處理\n"
        "- **關聯**：與 K-2 同形態\n",
    )
    archive = write(
        tmp_path / "known-issues-archive.md",
        "### K-2 已經被搬走\n- **狀態**：已修\n",
    )
    errors, _ = ckil.run_checks(known_issues, archive, tmp_path)
    assert any("原子性被破壞" in e for e in errors)


def test_fully_archived_chain_no_atomicity_violation(tmp_path):
    known_issues = write(
        tmp_path / "KNOWN-ISSUES.md",
        "## 已歸檔\n\n"
        "| ID | 一句話 | 影響範圍 | 明細 |\n"
        "|---|---|---|---|\n"
        "| K-1 | 一 | `foo.py` | [archive](known-issues-archive.md#k-1-一) |\n"
        "| K-2 | 二 | `bar.py` | [archive](known-issues-archive.md#k-2-二) |\n",
    )
    archive = write(
        tmp_path / "known-issues-archive.md",
        "### K-1 一\n- **狀態**：已修（無守備）\n- **關聯**：與 K-2 同形態\n\n"
        "### K-2 二\n- **狀態**：已修（無守備）\n",
    )
    errors, _ = ckil.run_checks(known_issues, archive, tmp_path)
    assert not any("原子性被破壞" in e for e in errors)


# ─── 已知未修被誤歸檔 ───


def test_archived_known_unfixed_detected(tmp_path):
    known_issues = write(
        tmp_path / "KNOWN-ISSUES.md",
        "## 已歸檔\n\n"
        "| ID | 一句話 | 影響範圍 | 明細 |\n"
        "|---|---|---|---|\n"
        "| K-1 | 刻意不修的問題 | `foo.py` | [archive](known-issues-archive.md#k-1-刻意不修的問題) |\n",
    )
    archive = write(
        tmp_path / "known-issues-archive.md",
        "### K-1 刻意不修的問題\n- **狀態**：已知未修\n",
    )
    errors, _ = ckil.run_checks(known_issues, archive, tmp_path)
    assert any("已知未修" in e and "K-1" in e for e in errors)


# ─── 守備路徑檢查(只查存在,不執行) ───


def test_defense_path_missing_detected(tmp_path):
    known_issues = write(
        tmp_path / "KNOWN-ISSUES.md",
        "### K-1 守備指向不存在的測試\n"
        "- **影響範圍**：`foo.py`\n"
        "- **狀態**：已修\n"
        "- **守備**：`tests/unit/test_nonexistent_file.py::test_x`\n",
    )
    archive = tmp_path / "known-issues-archive.md"
    errors, _ = ckil.run_checks(known_issues, archive, tmp_path)
    assert any("守備" in e and "test_nonexistent_file.py" in e for e in errors)


def test_defense_path_existing_no_violation(tmp_path):
    defense_file = tmp_path / "tests" / "unit" / "test_real.py"
    defense_file.parent.mkdir(parents=True)
    defense_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    known_issues = write(
        tmp_path / "KNOWN-ISSUES.md",
        "### K-1 守備指向存在的測試\n"
        "- **影響範圍**：`foo.py`\n"
        "- **狀態**：已修\n"
        "- **守備**：`tests/unit/test_real.py::test_x`\n",
    )
    archive = tmp_path / "known-issues-archive.md"
    errors, _ = ckil.run_checks(known_issues, archive, tmp_path)
    assert errors == []


def test_defense_required_but_empty_detected(tmp_path):
    known_issues = write(
        tmp_path / "KNOWN-ISSUES.md",
        "### K-1 已修卻沒填守備\n"
        "- **影響範圍**：`foo.py`\n"
        "- **狀態**：已修\n",
    )
    archive = tmp_path / "known-issues-archive.md"
    errors, _ = ckil.run_checks(known_issues, archive, tmp_path)
    assert any("沒有填「守備」" in e for e in errors)


# ─── 影響範圍檔案已不存在:只能是「需要人判斷」的 notice,不是 error ───


def test_affected_file_missing_is_notice_not_error(tmp_path):
    known_issues = write(
        tmp_path / "KNOWN-ISSUES.md",
        "### K-1 影響範圍的檔案已經不在了\n"
        "- **影響範圍**：`this_file_does_not_exist.py`\n"
        "- **狀態**：未處理\n",
    )
    archive = tmp_path / "known-issues-archive.md"
    errors, notices = ckil.run_checks(known_issues, archive, tmp_path)
    assert errors == []
    assert any("需要人判斷" in n and "this_file_does_not_exist.py" in n for n in notices)


# ─── CLI 輸出:命名與「沒檢查什麼」的免責聲明 ───


def test_cli_output_has_disclaimer_and_correct_naming(tmp_path, capsys):
    known_issues = write(tmp_path / "KNOWN-ISSUES.md", "### K-1 正常\n- **狀態**：未處理\n")
    archive = tmp_path / "known-issues-archive.md"
    exit_code = ckil.main(
        ["--known-issues", str(known_issues), "--archive", str(archive), "--repo-root", str(tmp_path)]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "驗證關聯性" not in out
    assert "不檢查" in out
    assert "語意層" in out
    assert "漏連結" in out


def test_cli_exit_code_nonzero_on_structural_error(tmp_path, capsys):
    known_issues = write(
        tmp_path / "KNOWN-ISSUES.md",
        "### K-1 壞掉的關聯\n- **狀態**：未處理\n- **關聯**：與 K-99 同形態\n",
    )
    archive = tmp_path / "known-issues-archive.md"
    exit_code = ckil.main(
        ["--known-issues", str(known_issues), "--archive", str(archive), "--repo-root", str(tmp_path)]
    )
    assert exit_code == 1
