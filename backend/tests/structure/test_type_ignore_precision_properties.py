"""
结构护栏测试: type: ignore 精确性

Property 2: type: ignore 精确性
Validates: Requirements 4.3

扫描所有 apps/ 目录下的 Python 文件，检测裸 `# type: ignore`（不带错误码）。
所有保留的 type: ignore 必须包含具体错误代码，如 `# type: ignore[attr-defined]`。

2025-02: 引入 baseline 机制，记录历史遗留的裸 type: ignore 文件，只检测新增违规。
"""

import os
import re
from pathlib import Path
from typing import NamedTuple

import pytest

# 匹配裸 type: ignore（不带错误码）
BARE_TYPE_IGNORE_PATTERN: re.Pattern[str] = re.compile(r"#\s*type:\s*ignore\s*(?!\[)")

# baseline 文件：记录已知的历史遗留违规文件（只记录文件路径）
_BASELINE_FILE = Path(__file__).parent / "baselines" / "bare_type_ignore_baseline.txt"


class Violation(NamedTuple):
    file: str
    line_no: int
    line_content: str


EXCLUDED_DIRS: frozenset[str] = frozenset({"migrations", "venv312", ".git"})


def _load_baseline() -> set[str]:
    """加载 baseline 文件中的已知违规文件路径"""
    if not _BASELINE_FILE.exists():
        return set()
    lines = _BASELINE_FILE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}


def _collect_app_files(apps_path: Path) -> list[Path]:
    py_files: list[Path] = []
    for py_file in apps_path.glob("**/*.py"):
        parts = py_file.parts
        if any(d in parts for d in EXCLUDED_DIRS):
            continue
        if py_file.name == "__init__.py":
            continue
        py_files.append(py_file)
    return py_files


def _scan_file(file_path: Path, backend_path: Path) -> list[Violation]:
    violations: list[Violation] = []
    lines = file_path.read_text(encoding="utf-8").splitlines()
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if BARE_TYPE_IGNORE_PATTERN.search(line):
            violations.append(
                Violation(
                    file=os.path.relpath(str(file_path), str(backend_path)),
                    line_no=line_no,
                    line_content=stripped,
                )
            )
    return violations


@pytest.mark.property_test
def test_type_ignore_must_have_error_code() -> None:
    """
    Property 2: type: ignore 精确性（新增违规检测）

    新增的 `# type: ignore` 注释必须包含具体错误代码，
    如 `# type: ignore[attr-defined]`，不允许裸 `# type: ignore`。
    baseline 文件中记录的历史遗留违规文件暂时豁免。

    Validates: Requirements 4.3
    """
    backend_path: Path = Path(__file__).resolve().parent.parent.parent
    apps_path: Path = backend_path / "apps"

    py_files = _collect_app_files(apps_path)
    assert len(py_files) > 0

    # 加载 baseline（历史遗留违规文件，暂时豁免）
    baseline_files: set[str] = _load_baseline()

    all_violations: list[Violation] = []
    for file_path in py_files:
        rel_path = os.path.relpath(str(file_path), str(backend_path))
        if rel_path in baseline_files:
            continue
        all_violations.extend(_scan_file(file_path, backend_path))

    assert not all_violations, f"发现 {len(all_violations)} 处新增裸 type: ignore（缺少错误码）：\n" + "\n".join(
        f"  - {v.file}:{v.line_no} {v.line_content}" for v in all_violations
    )
