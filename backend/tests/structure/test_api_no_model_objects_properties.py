"""
结构护栏测试: API 层零 Model.objects 直接调用

Feature: backend-quality-10, Property 2: API 层零 Model.objects 调用
Validates: Requirements 10.1, 2.1

扫描所有 apps/*/api/ 目录下的 Python 文件，检测 .objects.filter(、
.objects.get(、.objects.create(、.objects.all()、.objects.update(、
.objects.delete( 等 ORM 直接调用模式。
"""

import os
import re
from typing import NamedTuple

import pytest
from apps.core.path import Path


class Violation(NamedTuple):
    file: str
    line_no: int
    line_content: str
    pattern: str


# ORM 直接调用模式
MODEL_OBJECTS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (".objects.filter(", re.compile(r"\.objects\.filter\s*\(")),
    (".objects.get(", re.compile(r"\.objects\.get\s*\(")),
    (".objects.get_or_create(", re.compile(r"\.objects\.get_or_create\s*\(")),
    (".objects.create(", re.compile(r"\.objects\.create\s*\(")),
    (".objects.bulk_create(", re.compile(r"\.objects\.bulk_create\s*\(")),
    (".objects.update(", re.compile(r"\.objects\.update\s*\(")),
    (".objects.update_or_create(", re.compile(r"\.objects\.update_or_create\s*\(")),
    (".objects.delete(", re.compile(r"\.objects\.delete\s*\(")),
    (".objects.all()", re.compile(r"\.objects\.all\s*\(\s*\)")),
    (".objects.exclude(", re.compile(r"\.objects\.exclude\s*\(")),
    (".objects.annotate(", re.compile(r"\.objects\.annotate\s*\(")),
    (".objects.aggregate(", re.compile(r"\.objects\.aggregate\s*\(")),
    (".objects.values(", re.compile(r"\.objects\.values\s*\(")),
    (".objects.values_list(", re.compile(r"\.objects\.values_list\s*\(")),
    (".objects.count()", re.compile(r"\.objects\.count\s*\(\s*\)")),
    (".objects.exists()", re.compile(r"\.objects\.exists\s*\(\s*\)")),
    (".objects.first()", re.compile(r"\.objects\.first\s*\(\s*\)")),
    (".objects.last()", re.compile(r"\.objects\.last\s*\(\s*\)")),
    (".objects.order_by(", re.compile(r"\.objects\.order_by\s*\(")),
    (".objects.select_related(", re.compile(r"\.objects\.select_related\s*\(")),
    (".objects.prefetch_related(", re.compile(r"\.objects\.prefetch_related\s*\(")),
    (".objects.only(", re.compile(r"\.objects\.only\s*\(")),
    (".objects.defer(", re.compile(r"\.objects\.defer\s*\(")),
]

# 已知例外：这些文件允许 Model.objects 调用
ALLOWLIST: set[str] = {
    # automation 的 document_delivery 是 Service 层内部的 API 客户端，不是 HTTP API 层
    "apps/automation/services/document_delivery/api/document_delivery_api_service.py",
}


def _collect_api_files(apps_path: Path) -> list[Path]:
    """收集所有 API 层 Python 文件"""
    api_files: list[Path] = []
    for py_file in apps_path.glob("**/api/**/*.py"):
        if py_file.name == "__init__.py":
            continue
        api_files.append(py_file)
    return api_files


def _scan_file_for_violations(
    file_path: Path,
    backend_path: Path,
) -> list[Violation]:
    """扫描单个文件中的 Model.objects 调用"""
    violations: list[Violation] = []
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        # 跳过注释行
        if stripped.startswith("#"):
            continue
        for pattern_name, pattern in MODEL_OBJECTS_PATTERNS:
            if pattern.search(line):
                violations.append(
                    Violation(
                        file=os.path.relpath(str(file_path), str(backend_path)),
                        line_no=line_no,
                        line_content=stripped,
                        pattern=pattern_name,
                    )
                )
    return violations


@pytest.mark.property_test
def test_api_layer_no_model_objects_calls() -> None:
    """
    Property 2: API 层零 Model.objects 调用

    *For any* apps/*/api/ 目录下的 Python 文件，该文件内容不应包含
    .objects.filter(、.objects.get(、.objects.create(、.objects.update(、
    .objects.delete(、.objects.all() 等 ORM 直接调用模式。

    Feature: backend-quality-10, Property 2: API 层零 Model.objects 调用
    Validates: Requirements 10.1, 2.1
    """
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"

    api_files = _collect_api_files(apps_path)
    assert len(api_files) > 0, "未找到任何 API 层文件，请检查目录结构"

    all_violations: list[Violation] = []

    for file_path in api_files:
        rel = os.path.relpath(str(file_path), str(backend_path))
        if rel in ALLOWLIST:
            continue
        all_violations.extend(_scan_file_for_violations(file_path, backend_path))

    assert not all_violations, (
        f"API 层发现 {len(all_violations)} 处 Model.objects 直接调用违规：\n"
        + "\n".join(
            f"  - {v.file}:{v.line_no} [{v.pattern}] {v.line_content}"
            for v in all_violations
        )
    )
