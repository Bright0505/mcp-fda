#!/usr/bin/env python3
"""結構層檢查 docs/KNOWN-ISSUES.md(與可能存在的 docs/known-issues-archive.md)。

只驗「結構」這一層,範圍與理由見 claude-sandbox/docs/DECISIONS.md D7:

    - 指向的 K-n 是否存在
    - archive anchor 是否有效
    - 關聯群組的原子性有沒有被破壞(一條鏈只搬走一部分)
    - 已歸檔的條目裡有沒有 `已知未修`(永不該歸檔)
    - `守備` 指到的檔案是否存在(不執行測試,只檢查路徑)
    - `影響範圍` 提到的檔案是否還存在(輸出是「需要人判斷」,不是「可歸檔」)

**不檢查**(D7 判定不可驗或需要真實樣本,見腳本輸出末段的免責聲明):
    - 兩則條目是不是真的同一個故障形態(語意層)
    - 該連而沒連的條目(漏連結啟發式)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ENTRY_HEADER_RE = re.compile(r"^###\s+K-(\d+)\s+(.*)$")
FIELD_RE = re.compile(r"^-\s+\*\*`?([^`*]+?)`?\*\*[:：]\s*(.*)$")
ARCHIVE_TABLE_ROW_RE = re.compile(
    r"^\|\s*K-(\d+)\s*\|.*\|.*\|\s*\[[^\]]*\]\(([^)#]+)#([^)]+)\)\s*\|\s*$"
)
KREF_RE = re.compile(r"K-(\d+)")
FILE_TOKEN_RE = re.compile(r"`([^`]+\.[A-Za-z0-9]+(?::[^`]*)?)`")


@dataclass
class Entry:
    id: int
    title: str
    fields: dict = field(default_factory=dict)
    source: str = "main"  # "main" | "archive"


@dataclass
class ArchivedStub:
    id: int
    archive_file: str
    anchor: str


def parse_entries(text: str, source: str) -> list[Entry]:
    lines = text.splitlines()
    entries: list[Entry] = []
    current: Entry | None = None
    current_field: str | None = None
    pending_lines: list[str] = []

    def flush_field():
        if current is not None and current_field is not None:
            current.fields[current_field] = "\n".join(pending_lines).strip()

    for line in lines:
        header_match = ENTRY_HEADER_RE.match(line)
        if header_match:
            flush_field()
            if current is not None:
                entries.append(current)
            current = Entry(id=int(header_match.group(1)), title=header_match.group(2).strip(), source=source)
            current_field = None
            pending_lines = []
            continue

        if current is None:
            continue

        field_match = FIELD_RE.match(line.strip())
        if field_match:
            flush_field()
            current_field = field_match.group(1).strip()
            pending_lines = [field_match.group(2).strip()]
            continue

        if line.strip() == "" and current_field is None:
            continue

        if current_field is not None:
            pending_lines.append(line.strip())

    flush_field()
    if current is not None:
        entries.append(current)

    return entries


def parse_archived_stubs(text: str) -> list[ArchivedStub]:
    stubs = []
    for line in text.splitlines():
        m = ARCHIVE_TABLE_ROW_RE.match(line.strip())
        if m:
            stubs.append(
                ArchivedStub(id=int(m.group(1)), archive_file=m.group(2).strip(), anchor=m.group(3).strip())
            )
    return stubs


def count_headers(text: str) -> int:
    return len(re.findall(r"^###\s+K-\d+\b", text, re.MULTILINE))


def anchor_slug(entry_id: int, title: str) -> str:
    raw = f"k-{entry_id}-{title}"
    slug = re.sub(r"[^\w\- ]", "", raw, flags=re.UNICODE)
    slug = slug.strip().lower().replace(" ", "-")
    return slug


def load_ids(entries: list[Entry], stubs: list[ArchivedStub]) -> set[int]:
    return {e.id for e in entries} | {s.id for s in stubs}


def check_entry_count(main_text: str, main_entries: list[Entry]) -> list[str]:
    header_count = count_headers(main_text)
    if header_count != len(main_entries):
        return [
            f"條目數斷言失敗:`### K-` 標頭有 {header_count} 個,但解析出 {len(main_entries)} 則條目。"
            "解析邏輯可能有 bug,靜默漏掉了條目 —— 這是最危險的失效模式,已中止其餘檢查。"
        ]
    return []


def check_referenced_ids_exist(all_entries: list[Entry], known_ids: set[int]) -> list[str]:
    violations = []
    for e in all_entries:
        ref_text = e.fields.get("關聯", "")
        for m in KREF_RE.finditer(ref_text):
            ref_id = int(m.group(1))
            if ref_id not in known_ids:
                violations.append(f"K-{e.id} 的「關聯」指向 K-{ref_id},但 K-{ref_id} 不存在於主檔或歸檔檔")
    return violations


def check_archive_anchors(stubs: list[ArchivedStub], archive_entries: list[Entry], archive_path: Path) -> list[str]:
    violations = []
    archive_by_id = {e.id: e for e in archive_entries}
    for stub in stubs:
        target_path = archive_path.parent / stub.archive_file
        if not target_path.exists():
            violations.append(f"K-{stub.id} 的歸檔連結指向不存在的檔案 `{stub.archive_file}`")
            continue
        entry = archive_by_id.get(stub.id)
        if entry is None:
            violations.append(f"K-{stub.id} 的歸檔連結指向 `{stub.archive_file}`,但該檔裡沒有 K-{stub.id} 的條目")
            continue
        expected_slug = anchor_slug(entry.id, entry.title)
        if stub.anchor.lower() != expected_slug and not expected_slug.startswith(stub.anchor.lower()):
            violations.append(
                f"K-{stub.id} 的歸檔連結 anchor `#{stub.anchor}` 與 archive 檔裡的標頭 slug `#{expected_slug}` 不一致"
            )
    return violations


def build_link_components(all_entries: list[Entry], known_ids: set[int]) -> list[set[int]]:
    parent = {i: i for i in known_ids}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for e in all_entries:
        ref_text = e.fields.get("關聯", "")
        for m in KREF_RE.finditer(ref_text):
            ref_id = int(m.group(1))
            if ref_id in known_ids:
                union(e.id, ref_id)

    components: dict[int, set[int]] = {}
    for i in known_ids:
        components.setdefault(find(i), set()).add(i)
    return [c for c in components.values() if len(c) > 1]


def check_chain_atomicity(components: list[set[int]], main_ids: set[int], archive_ids: set[int]) -> list[str]:
    violations = []
    for comp in components:
        in_main = comp & main_ids
        in_archive = comp & archive_ids
        if in_main and in_archive:
            violations.append(
                "關聯群組原子性被破壞:"
                f"{{{', '.join('K-' + str(i) for i in sorted(comp))}}} 一部分在主檔"
                f"({', '.join('K-' + str(i) for i in sorted(in_main))}),"
                f"一部分已歸檔({', '.join('K-' + str(i) for i in sorted(in_archive))})"
            )
    return violations


def check_archived_never_unfixed(archive_entries: list[Entry]) -> list[str]:
    violations = []
    for e in archive_entries:
        status = e.fields.get("狀態", "")
        if "已知未修" in status:
            violations.append(f"K-{e.id} 狀態是「已知未修」卻出現在歸檔檔裡 —— 已知未修永不可歸檔")
    return violations


def check_defense_test_paths(all_entries: list[Entry], repo_root: Path) -> list[str]:
    violations = []
    for e in all_entries:
        status = e.fields.get("狀態", "")
        defense = e.fields.get("守備", "")
        if "已修" not in status or "無守備" in status:
            continue
        if not defense:
            violations.append(f"K-{e.id} 狀態是「{status}」但沒有填「守備」")
            continue
        path_part = defense.split("::", 1)[0].strip("` \n")
        if not path_part:
            continue
        candidate = repo_root / path_part
        if not candidate.exists():
            violations.append(f"K-{e.id} 的「守備」指向不存在的檔案 `{path_part}`(只檢查存在,不執行測試)")
    return violations


def check_affected_files(all_entries: list[Entry], repo_root: Path) -> list[str]:
    notices = []
    for e in all_entries:
        scope = e.fields.get("影響範圍", "")
        for m in FILE_TOKEN_RE.finditer(scope):
            token = m.group(1).split(":", 1)[0]
            if "/" not in token and "." not in token:
                continue
            candidate = repo_root / token
            if not candidate.exists():
                notices.append(
                    f"K-{e.id} 的「影響範圍」提到 `{token}`,repo 裡已經找不到這個檔案 —— "
                    "需要人判斷:這個故障形態在新的實作裡還可能發生嗎(不是自動判定可歸檔)"
                )
    return notices


def run_checks(known_issues_path: Path, archive_path: Path, repo_root: Path):
    main_text = known_issues_path.read_text(encoding="utf-8")
    main_entries = parse_entries(main_text, source="main")
    stubs = parse_archived_stubs(main_text)

    archive_entries: list[Entry] = []
    if archive_path.exists():
        archive_text = archive_path.read_text(encoding="utf-8")
        archive_entries = parse_entries(archive_text, source="archive")

    errors: list[str] = check_entry_count(main_text, main_entries)
    if errors:
        return errors, []

    known_ids = load_ids(main_entries + archive_entries, stubs)
    all_entries = main_entries + archive_entries
    # 原子性判斷只看「完整條目現在在哪」:main_entries 是還沒歸檔的,
    # archive_entries 是已歸檔的。stub table 的列只是指標,不代表歸屬,不能混進來算。
    main_ids = {e.id for e in main_entries}
    archive_ids = {e.id for e in archive_entries}

    errors += check_referenced_ids_exist(all_entries, known_ids)
    errors += check_archive_anchors(stubs, archive_entries, archive_path)

    components = build_link_components(all_entries, known_ids)
    errors += check_chain_atomicity(components, main_ids, archive_ids)
    errors += check_archived_never_unfixed(archive_entries)
    errors += check_defense_test_paths(all_entries, repo_root)

    notices = check_affected_files(all_entries, repo_root)

    return errors, notices


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-known-issues-links",
        description="KNOWN-ISSUES.md 結構層檢查(不驗語意、不驗漏連結,見 D7)",
    )
    parser.add_argument("--known-issues", type=Path, default=Path("docs/KNOWN-ISSUES.md"))
    parser.add_argument("--archive", type=Path, default=Path("docs/known-issues-archive.md"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    if not args.known_issues.exists():
        print(f"找不到 {args.known_issues}", file=sys.stderr)
        return 2

    errors, notices = run_checks(args.known_issues, args.archive, args.repo_root)

    for err in errors:
        print(f"[結構錯誤] {err}")
    for notice in notices:
        print(f"[需要人判斷] {notice}")

    if not errors and not notices:
        print("結構層檢查通過,沒有發現問題。")

    print()
    print("本腳本只檢查結構層(K-n 是否存在、archive anchor、關聯群組原子性、"
          "已知未修是否被誤歸檔、守備路徑是否存在、影響範圍檔案是否還在)。")
    print("不檢查:兩則條目是否真的同一形態(語意層)、該連而沒連的條目(漏連結啟發式)——"
          "這兩層 D7 判定不可驗或需要真實樣本累積後再做。")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
