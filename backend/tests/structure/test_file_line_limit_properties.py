"""
结构护栏测试: 文件行数上限（400行）

Feature: backend-quality-10, Property: 文件行数上限护栏
Validates: Requirements 10.7

扫描 apps/core/interfaces.py 和 apps/core/interfaces/__init__.py，
检测行数是否超过 400 行。文件不存在时跳过。
"""

import os
from pathlib import Path
from typing import NamedTuple

import pytest

# 行数上限
LINE_LIMIT: int = 400

# 需要检测的文件列表（相对于 apps/core/）
TARGET_FILES: tuple[str, ...] = (
    "interfaces.py",
    "interfaces/__init__.py",
)


class Violation(NamedTuple):
    file: str
    line_count: int


def _count_lines(file_path: Path) -> int:
    """统计文件行数"""
    content: str = file_path.read_text(encoding="utf-8")
    return len(content.splitlines())


def _scan_target_files(
    core_path: Path,
    backend_path: Path,
) -> tuple[list[Violation], int]:
    """扫描目标文件，返回违规列表和已扫描文件数"""
    violations: list[Violation] = []
    scanned: int = 0

    for rel_name in TARGET_FILES:
        file_path: Path = core_path / rel_name
        if not file_path.exists():
            continue
        scanned += 1
        line_count: int = _count_lines(file_path)
        if line_count > LINE_LIMIT:
            violations.append(
                Violation(
                    file=os.path.relpath(str(file_path), str(backend_path)),
                    line_count=line_count,
                )
            )
    return violations, scanned


@pytest.mark.property_test
def test_file_line_limit() -> None:
    """
    文件行数上限护栏: interfaces 相关文件不超过 400 行

    扫描 apps/core/interfaces.py 和
    apps/core/interfaces/__init__.py，检测行数是否超过 400 行。
    文件不存在时自动跳过（拆分完成后部分文件会被删除）。

    Feature: backend-quality-10, Property: 文件行数上限护栏
    Validates: Requirements 10.7
    """
    backend_path: Path = Path(__file__).resolve().parent.parent.parent
    core_path: Path = backend_path / "apps" / "core"

    violations, scanned = _scan_target_files(core_path, backend_path)

    assert scanned > 0, "未找到任何目标文件，请检查 apps/core/ 目录结构"

    assert not violations, (
        f"发现 {len(violations)} 个文件超过 {LINE_LIMIT} 行上限：\n"
        + "\n".join(
            f"  - {v.file}: {v.line_count} 行（上限 {LINE_LIMIT} 行）"
            for v in violations
        )
    )
