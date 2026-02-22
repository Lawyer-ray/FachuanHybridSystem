"""
属性测试：日志调用不使用 f-string

# Feature: cases-quality-uplift, Property 3: 日志调用不使用 f-string

扫描 backend/apps/cases/ 下所有 Python 文件，
验证无 logger.(info|error|warning|debug|exception)(f["'] 模式。
"""

from __future__ import annotations

import re
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# 项目根目录
BACKEND_ROOT: Path = Path(__file__).parent.parent.parent.parent
CASES_ROOT: Path = BACKEND_ROOT / "apps" / "cases"

# 匹配 f-string 日志调用的正则
FSTRING_LOG_PATTERN: re.Pattern[str] = re.compile(r"""logger\.(info|error|warning|debug|exception)\(f["']""")

# 收集所有 Python 文件（排除 migrations 和 __pycache__）
ALL_PY_FILES: list[Path] = sorted(
    p for p in CASES_ROOT.rglob("*.py") if "migrations" not in p.parts and "__pycache__" not in p.parts
)


def _find_fstring_log_violations(filepath: Path) -> list[tuple[int, str]]:
    """
    扫描文件内容，返回所有匹配 f-string 日志调用的行。

    返回: [(行号, 行内容), ...]
    """
    violations: list[tuple[int, str]] = []
    text: str = filepath.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FSTRING_LOG_PATTERN.search(line):
            violations.append((lineno, line.strip()))
    return violations


# ---------------------------------------------------------------------------
# Property 3: 日志调用不使用 f-string（Hypothesis 属性测试）
# Feature: cases-quality-uplift, Property 3: 日志调用不使用 f-string
# ---------------------------------------------------------------------------


@given(filepath=st.sampled_from(ALL_PY_FILES))
@settings(max_examples=max(100, len(ALL_PY_FILES) * 3))
def test_property_no_fstring_log(filepath: Path) -> None:
    """
    **Validates: Requirements 4.1, 5.3, 9.1, 9.2, 9.3, 9.4**

    对于 backend/apps/cases/ 下任意 Python 文件，
    不应包含 logger.(info|error|warning|debug|exception)(f["'] 模式的调用。
    """
    violations: list[tuple[int, str]] = _find_fstring_log_violations(filepath)

    assert not violations, f"{filepath.relative_to(BACKEND_ROOT)} 包含 f-string 日志调用:\n" + "\n".join(
        f"  第 {lineno} 行: {line}" for lineno, line in violations
    )
