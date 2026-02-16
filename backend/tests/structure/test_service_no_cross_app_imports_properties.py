"""
结构护栏测试: Service 层零跨 app 直接导入

Feature: backend-quality-10, Property 7: Service 层零跨 app 直接导入
Validates: Requirements 10.6, 9.3

扫描所有 apps/{module}/services/ 目录下的 Python 文件，检测
`from apps.{other_module}.models import` 和 `from apps.{other_module}.services import`
的跨模块直接导入。apps.core 作为共享模块允许导入。
"""

import os
import re
from pathlib import Path
from typing import NamedTuple

import pytest

# 匹配 from apps.xxx.models import ... 和 from apps.xxx.services import ...
CROSS_APP_FROM_IMPORT_PATTERN: re.Pattern[str] = re.compile(r"^\s*from\s+apps\.(\w+)\.(models|services)\b")

# 匹配 import apps.xxx.models 和 import apps.xxx.services
CROSS_APP_DIRECT_IMPORT_PATTERN: re.Pattern[str] = re.compile(r"^\s*import\s+apps\.(\w+)\.(models|services)\b")

# 共享模块，允许跨模块导入
ALLOWED_MODULES: frozenset[str] = frozenset({"core"})


class Violation(NamedTuple):
    file: str
    line_no: int
    line_content: str
    imported_module: str


def _collect_service_files(apps_path: Path) -> list[Path]:
    """收集所有 Service 层 Python 文件"""
    service_files: list[Path] = []
    for py_file in apps_path.glob("*/services/**/*.py"):
        if py_file.name == "__init__.py":
            continue
        service_files.append(py_file)
    return service_files


def _extract_module_name(file_path: Path, apps_path: Path) -> str:
    """从文件路径提取所属模块名。

    例如 apps/contracts/services/foo.py -> 'contracts'
    """
    rel: Path = file_path.relative_to(apps_path)
    return rel.parts[0]


def _scan_file_for_cross_app_imports(
    file_path: Path,
    backend_path: Path,
    apps_path: Path,
) -> list[Violation]:
    """扫描单个文件中的跨模块直接导入"""
    violations: list[Violation] = []
    own_module: str = _extract_module_name(file_path, apps_path)
    content: str = file_path.read_text(encoding="utf-8")
    lines: list[str] = content.splitlines()

    for line_no, line in enumerate(lines, start=1):
        stripped: str = line.strip()
        # 跳过注释行
        if stripped.startswith("#"):
            continue

        for pattern in (CROSS_APP_FROM_IMPORT_PATTERN, CROSS_APP_DIRECT_IMPORT_PATTERN):
            match: re.Match[str] | None = pattern.search(line)
            if match is None:
                continue
            imported_module: str = match.group(1)
            # 允许导入自身模块
            if imported_module == own_module:
                continue
            # 允许导入共享模块
            if imported_module in ALLOWED_MODULES:
                continue
            violations.append(
                Violation(
                    file=os.path.relpath(str(file_path), str(backend_path)),
                    line_no=line_no,
                    line_content=stripped,
                    imported_module=imported_module,
                )
            )
    return violations


@pytest.mark.property_test
def test_service_layer_no_cross_app_imports() -> None:
    """
    Property 7: Service 层零跨 app 直接导入

    *For any* apps/{module}/services/ 目录下的 Python 文件，该文件不应包含
    `from apps.{other_module}.models import` 或
    `from apps.{other_module}.services import` 的导入语句
    （其中 other_module ≠ module，且 other_module ≠ core）。

    Feature: backend-quality-10, Property 7: Service 层零跨 app 直接导入
    Validates: Requirements 10.6, 9.3
    """
    backend_path: Path = Path(__file__).resolve().parent.parent.parent
    apps_path: Path = backend_path / "apps"

    service_files: list[Path] = _collect_service_files(apps_path)
    assert len(service_files) > 0, "未找到任何 Service 层文件，请检查目录结构"

    all_violations: list[Violation] = []

    for file_path in service_files:
        all_violations.extend(_scan_file_for_cross_app_imports(file_path, backend_path, apps_path))

    assert not all_violations, f"Service 层发现 {len(all_violations)} 处跨模块直接导入违规：\n" + "\n".join(
        f"  - {v.file}:{v.line_no} [导入 apps.{v.imported_module}] {v.line_content}" for v in all_violations
    )
