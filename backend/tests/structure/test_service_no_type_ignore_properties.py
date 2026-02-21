"""
结构护栏测试: Service 层零 type: ignore 注释

Feature: backend-quality-10, Property 3: Service 层零 type: ignore
Validates: Requirements 10.2, 3.1

扫描所有 apps/*/services/ 目录下的 Python 文件，检测 `# type: ignore`
注释（包括带具体错误码的形式如 `# type: ignore[attr-defined]`）。

2025-02: 引入 baseline 机制，记录历史遗留违规，只检测新增违规。
历史违规应逐步清理，但不阻塞当前开发。
"""

import os
import re
from pathlib import Path
from typing import NamedTuple

import pytest

# 匹配 type:ignore 注释的正则表达式模式（含可选的错误码后缀）
TYPE_IGNORE_PATTERN: re.Pattern[str] = re.compile(r"#\s*type:\s*ignore(?:\[[\w\-,\s]+\])?")

# baseline 文件路径：记录已知的历史遗留违规文件（只记录文件路径，不记录行号）
_BASELINE_FILE = Path(__file__).parent / "baselines" / "service_type_ignore_baseline.txt"


class Violation(NamedTuple):
    file: str
    line_no: int
    line_content: str


def _load_baseline() -> set[str]:
    """加载 baseline 文件中的已知违规文件路径"""
    if not _BASELINE_FILE.exists():
        return set()
    lines = _BASELINE_FILE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}


def _collect_service_files(apps_path: Path) -> list[Path]:
    """收集所有 Service 层 Python 文件"""
    service_files: list[Path] = []
    for py_file in apps_path.glob("*/services/**/*.py"):
        if py_file.name == "__init__.py":
            continue
        service_files.append(py_file)
    return service_files


def _scan_file_for_type_ignore(
    file_path: Path,
    backend_path: Path,
) -> list[Violation]:
    """扫描单个文件中的 type: ignore 注释"""
    violations: list[Violation] = []
    content: str = file_path.read_text(encoding="utf-8")
    lines: list[str] = content.splitlines()

    for line_no, line in enumerate(lines, start=1):
        stripped: str = line.strip()
        # 跳过纯注释行（仅检测行内 type: ignore）
        if stripped.startswith("#"):
            continue
        if TYPE_IGNORE_PATTERN.search(line):
            violations.append(
                Violation(
                    file=os.path.relpath(str(file_path), str(backend_path)),
                    line_no=line_no,
                    line_content=stripped,
                )
            )
    return violations


@pytest.mark.property_test
def test_service_layer_no_type_ignore() -> None:
    """
    Property 3: Service 层零 type: ignore（新增违规检测）

    检测 apps/*/services/ 目录下的 Python 文件中新增的 type: ignore 注释。
    baseline 文件中记录的历史遗留违规文件不计入检测范围。

    Feature: backend-quality-10, Property 3: Service 层零 type: ignore
    Validates: Requirements 10.2, 3.1
    """
    backend_path: Path = Path(__file__).resolve().parent.parent.parent
    apps_path: Path = backend_path / "apps"

    service_files: list[Path] = _collect_service_files(apps_path)
    assert len(service_files) > 0, "未找到任何 Service 层文件，请检查目录结构"

    # 加载 baseline（历史遗留违规文件，暂时豁免）
    baseline_files: set[str] = _load_baseline()

    all_violations: list[Violation] = []

    for file_path in service_files:
        rel_path = os.path.relpath(str(file_path), str(backend_path))
        # baseline 中的文件跳过（历史遗留，逐步清理）
        if rel_path in baseline_files:
            continue
        all_violations.extend(_scan_file_for_type_ignore(file_path, backend_path))

    assert not all_violations, f"Service 层发现 {len(all_violations)} 处新增 type: ignore 注释违规：\n" + "\n".join(
        f"  - {v.file}:{v.line_no} {v.line_content}" for v in all_violations
    )
