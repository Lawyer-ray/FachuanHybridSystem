"""Test that business layer code does not directly import django_q.

All task submission should go through ``apps.core.tasking`` abstraction.
Only infrastructure code (``core/tasking/`` itself and management commands)
is allowed to import from django_q directly.

See: P3-1 Complete task scheduling abstraction
"""

from __future__ import annotations

import re
from pathlib import Path

_APPS_ROOT = Path(__file__).resolve().parents[3] / "apps"

# Patterns that are ALLOWED to import from django_q
_ALLOWED_PREFIXES: list[str] = [
    # The tasking abstraction layer itself
    str(_APPS_ROOT / "core" / "tasking"),
    # NOTE: management commands are handled separately below via parts check
]

# Specific files that are allowed to import from django_q
# These are known infrastructure-level files.
# 注意：条目必须是相对 apps/ 的路径（与 rel_path 比较；历史上存绝对路径
# 导致从未生效过——2026-09-29 修正）。
_ALLOWED_FILES: set[str] = {
    # automation「停止并删除」需对 Django-Q 做队列级手术（Schedule 批量删除、
    # Redis/OrmQ 队列条目按签名 payload 匹配清理、SignedPackage 反解析）——
    # core.tasking 尚无对应抽象，待抽象后迁移
    "automation/services/sms/court_sms_abort_service.py",
}


def _find_django_q_imports() -> list[tuple[str, int, str]]:
    """Find all ``from django_q`` or ``import django_q`` in apps/.

    Returns list of (relative_path, line_number, line_content).
    """
    violations: list[tuple[str, int, str]] = []
    import_pattern = re.compile(r"(?:from\s+django_q|import\s+django_q)")

    for py_file in _APPS_ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        rel_path = str(py_file.relative_to(_APPS_ROOT))

        # Skip allowed locations
        if any(str(py_file).startswith(prefix) for prefix in _ALLOWED_PREFIXES):
            continue
        if rel_path in _ALLOWED_FILES:
            continue

        # Skip management commands
        parts = py_file.parts
        if "management" in parts and "commands" in parts:
            continue

        text = py_file.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if import_pattern.search(line):
                violations.append((rel_path, line_no, line.strip()))

    return violations


def test_business_layer_has_no_django_q_imports() -> None:
    """Business layer code must not directly import django_q.

    Only ``apps/core/tasking/`` and management commands may import django_q.
    All other code should use ``apps.core.tasking`` abstractions.
    """
    violations = _find_django_q_imports()

    if violations:
        lines = [f"  {path}:{lineno}: {content}" for path, lineno, content in violations]
        msg = (
            "Business layer code must not directly import django_q.\n"
            "Use ``from apps.core.tasking import submit_task`` instead.\n"
            f"Found {len(violations)} violation(s):\n" + "\n".join(lines)
        )
        raise AssertionError(msg)
