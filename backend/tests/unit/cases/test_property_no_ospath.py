"""
属性测试：不使用 os.path

# Feature: cases-quality-uplift, Property 4: 不使用 os.path

扫描 backend/apps/cases/ 下所有 Python 文件（排除 migrations），
验证无 os.path 使用。
"""

from __future__ import annotations

import re
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# 项目根目录
BACKEND_ROOT: Path = Path(__file__).parent.parent.parent.parent
CASES_ROOT: Path = BACKEND_ROOT / "apps" / "cases"

# 匹配 os.path 使用的正则模式
OS_PATH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*import\s+os\.path\b"),
    re.compile(r"^\s*import\s+os\b"),
    re.compile(r"^\s*from\s+os(?:\.path)?\s+import\b"),
    re.compile(r"\bos\.path\."),
]

# 收集所有 Python 文件（排除 migrations 和 __pycache__）
ALL_PY_FILES: list[Path] = sorted(
    p
    for p in CASES_ROOT.rglob("*.py")
    if "migrations" not in p.parts and "__pycache__" not in p.parts
)


def _find_ospath_violations(filepath: Path) -> list[tuple[int, str]]:
    """
    扫描文件内容，返回所有匹配 os.path 使用的行。

    返回: [(行号, 行内容), ...]
    """
    violations: list[tuple[int, str]] = []
    text: str = filepath.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in OS_PATH_PATTERNS:
            if pattern.search(line):
                violations.append((lineno, line.strip()))
                break
    return violations


# ---------------------------------------------------------------------------
# Property 4: 不使用 os.path（Hypothesis 属性测试）
# Feature: cases-quality-uplift, Property 4: 不使用 os.path
# ---------------------------------------------------------------------------


@given(filepath=st.sampled_from(ALL_PY_FILES))
@settings(max_examples=max(100, len(ALL_PY_FILES) * 3))
def test_property_no_ospath(filepath: Path) -> None:
    """
    **Validates: Requirements 8.1, 8.2**

    对于 backend/apps/cases/ 下任意 Python 文件（排除 migrations），
    不应包含 import os.path、import os、from os import 或 os.path. 的使用。
    """
    violations: list[tuple[int, str]] = _find_ospath_violations(filepath)

    assert not violations, (
        f"{filepath.relative_to(BACKEND_ROOT)} 包含 os.path 使用:\n"
        + "\n".join(
            f"  第 {lineno} 行: {line}" for lineno, line in violations
        )
    )
