"""
属性测试：类型注解完整性

# Feature: cases-quality-uplift, Property 5: 类型注解完整性

AST 解析 backend/apps/cases/ 下所有公开函数和方法（排除 migrations 和 __init__.py），
验证具有返回类型注解且无 Optional[ 字符串。
"""

from __future__ import annotations

import ast
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# 项目根目录
BACKEND_ROOT: Path = Path(__file__).parent.parent.parent.parent
CASES_ROOT: Path = BACKEND_ROOT / "apps" / "cases"

# 收集所有 Python 文件（排除 migrations、__pycache__、__init__.py）
ALL_PY_FILES: list[Path] = sorted(
    p
    for p in CASES_ROOT.rglob("*.py")
    if "migrations" not in p.parts and "__pycache__" not in p.parts and p.name != "__init__.py"
)


def _is_public(name: str) -> bool:
    """判断函数/方法名是否为公开的（非 _ 前缀，排除 dunder）。"""
    if name.startswith("__") and name.endswith("__"):
        return False
    return not name.startswith("_")


def _find_missing_return_annotations(filepath: Path) -> list[tuple[int, str]]:
    """
    AST 解析文件，返回缺少返回类型注解的公开函数/方法。

    返回: [(行号, 函数名), ...]
    """
    violations: list[tuple[int, str]] = []
    source: str = filepath.read_text(encoding="utf-8")
    try:
        tree: ast.Module = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_public(node.name) and node.returns is None:
                violations.append((node.lineno, node.name))
    return violations


def _find_optional_usage(filepath: Path) -> list[tuple[int, str]]:
    """
    扫描文件内容，返回包含 Optional[ 字符串的行。

    返回: [(行号, 行内容), ...]
    """
    violations: list[tuple[int, str]] = []
    source: str = filepath.read_text(encoding="utf-8")
    for lineno, line in enumerate(source.splitlines(), start=1):
        if "Optional[" in line:
            violations.append((lineno, line.strip()))
    return violations


# ---------------------------------------------------------------------------
# Property 5: 类型注解完整性（Hypothesis 属性测试）
# Feature: cases-quality-uplift, Property 5: 类型注解完整性
# ---------------------------------------------------------------------------


@given(filepath=st.sampled_from(ALL_PY_FILES))
@settings(max_examples=max(100, len(ALL_PY_FILES) * 3))
def test_property_public_functions_have_return_annotation(filepath: Path) -> None:
    """
    **Validates: Requirements 6.1**

    对于 backend/apps/cases/ 下任意 Python 文件（排除 migrations 和 __init__.py），
    所有公开函数和方法（非 _ 前缀，排除 dunder）应具有返回类型注解。
    """
    violations: list[tuple[int, str]] = _find_missing_return_annotations(filepath)

    assert not violations, f"{filepath.relative_to(BACKEND_ROOT)} 中以下公开函数缺少返回类型注解:\n" + "\n".join(
        f"  第 {lineno} 行: {name}" for lineno, name in violations
    )


@given(filepath=st.sampled_from(ALL_PY_FILES))
@settings(max_examples=max(100, len(ALL_PY_FILES) * 3))
def test_property_no_optional_bracket(filepath: Path) -> None:
    """
    **Validates: Requirements 6.2**

    对于 backend/apps/cases/ 下任意 Python 文件（排除 migrations 和 __init__.py），
    不应包含 Optional[ 字符串。
    """
    violations: list[tuple[int, str]] = _find_optional_usage(filepath)

    assert not violations, f"{filepath.relative_to(BACKEND_ROOT)} 包含 Optional[ 使用:\n" + "\n".join(
        f"  第 {lineno} 行: {line}" for lineno, line in violations
    )
