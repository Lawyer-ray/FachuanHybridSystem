"""
结构护栏测试: TODO 格式规范

Property 5: TODO 格式规范
Validates: Requirements 7.3

扫描所有 apps/ 目录下的 Python 文件，检测 FIXME/HACK 标记。
FIXME/HACK 不允许出现（应修复后删除，或转为带 issue 编号的 TODO）。
TODO 允许出现，但推荐格式为 `TODO(issue-NNN): 描述`。
"""

import re
from pathlib import Path
from typing import NamedTuple

import pytest

# 检测 FIXME/HACK 标记（行内注释，不在字符串中）
FORBIDDEN_MARKER_PATTERN: re.Pattern[str] = re.compile(r"#.*(FIXME|HACK)\b", re.IGNORECASE)

EXCLUDED_DIRS: frozenset[str] = frozenset({"migrations", "venv312", ".git"})


class Violation(NamedTuple):
    file: str
    line_no: int
    marker: str
    line_content: str


def _collect_app_files(apps_path: Path) -> list[Path]:
    py_files: list[Path] = []
    for py_file in apps_path.glob("**/*.py"):
        parts = py_file.parts
        if any(d in parts for d in EXCLUDED_DIRS):
            continue
        py_files.append(py_file)
    return py_files


def _scan_file(file_path: Path, backend_path: Path) -> list[Violation]:
    violations: list[Violation] = []
    lines = file_path.read_text(encoding="utf-8").splitlines()
    for line_no, line in enumerate(lines, start=1):
        m = FORBIDDEN_MARKER_PATTERN.search(line)
        if not m:
            continue
        violations.append(
            Violation(
                file=str(file_path.relative_to(backend_path)),
                line_no=line_no,
                marker=m.group(1).upper(),
                line_content=line.strip(),
            )
        )
    return violations


@pytest.mark.property_test
def test_no_fixme_or_hack_markers() -> None:
    """
    Property 5: TODO 格式规范

    FIXME/HACK 标记不允许出现在代码注释中。
    应修复问题后删除，或转为 TODO(issue-NNN): 描述 格式跟踪。

    Validates: Requirements 7.3
    """
    backend_path: Path = Path(__file__).resolve().parent.parent.parent
    apps_path: Path = backend_path / "apps"

    py_files = _collect_app_files(apps_path)
    assert len(py_files) > 0

    all_violations: list[Violation] = []
    for file_path in py_files:
        all_violations.extend(_scan_file(file_path, backend_path))

    assert (
        not all_violations
    ), f"发现 {len(all_violations)} 处 FIXME/HACK 标记（应修复或转为 TODO(issue-NNN)）：\n" + "\n".join(
        f"  - {v.file}:{v.line_no} [{v.marker}] {v.line_content}" for v in all_violations
    )
