"""
属性测试：根目录重导出文件纯净性

# Feature: cases-quality-uplift, Property 1: 根目录重导出文件纯净性
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# 项目根目录
BACKEND_ROOT = Path(__file__).parent.parent.parent.parent
CASES_ROOT = BACKEND_ROOT / "apps" / "cases"

# 根目录重导出文件列表
REEXPORT_FILES: list[Path] = [
    CASES_ROOT / "models.py",
    CASES_ROOT / "schemas.py",
    CASES_ROOT / "validators.py",
]

# AST 节点中允许出现在纯重导出文件顶层的类型
ALLOWED_TOP_LEVEL_TYPES: tuple[type[ast.stmt], ...] = (
    ast.Import,
    ast.ImportFrom,
    ast.Assign,  # __all__ 赋值
    ast.Expr,  # 文档字符串
    ast.If,  # TYPE_CHECKING 守卫等
    ast.AnnAssign,  # 带注解的赋值
)


def _parse_file(filepath: Path) -> ast.Module:
    """解析 Python 文件并返回 AST 模块节点。"""
    source: str = filepath.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(filepath))


def _get_forbidden_nodes(tree: ast.Module) -> list[tuple[int, str, str]]:
    """
    检查 AST 顶层节点，返回所有不允许的节点列表。

    返回: [(行号, 节点类型名, 节点名称), ...]
    """
    violations: list[tuple[int, str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            violations.append((node.lineno, "ClassDef", node.name))
        elif isinstance(node, ast.FunctionDef):
            violations.append((node.lineno, "FunctionDef", node.name))
        elif isinstance(node, ast.AsyncFunctionDef):
            violations.append((node.lineno, "AsyncFunctionDef", node.name))
        elif not isinstance(node, ALLOWED_TOP_LEVEL_TYPES):
            violations.append(
                (
                    getattr(node, "lineno", 0),
                    type(node).__name__,
                    "",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Property 1: 根目录重导出文件纯净性（实际文件验证）
# Feature: cases-quality-uplift, Property 1: 根目录重导出文件纯净性
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filepath", REEXPORT_FILES, ids=lambda p: p.name)
def test_reexport_file_has_no_class_or_function_definitions(filepath: Path) -> None:
    """
    **Validates: Requirements 1.1, 1.2, 1.3**

    解析根目录重导出文件的 AST，验证顶层不包含 ClassDef 或 FunctionDef 节点。
    仅允许 Import、ImportFrom、Assign（__all__）、Expr（docstring）等节点。
    """
    assert filepath.exists(), f"文件不存在: {filepath}"

    tree: ast.Module = _parse_file(filepath)
    violations: list[tuple[int, str, str]] = _get_forbidden_nodes(tree)

    assert not violations, f"{filepath.name} 包含不允许的顶层定义:\n" + "\n".join(
        f"  第 {lineno} 行: {node_type} {name}" for lineno, node_type, name in violations
    )


# ---------------------------------------------------------------------------
# Hypothesis 属性测试：验证 AST 检测逻辑对随机 Python 代码的正确性
# Feature: cases-quality-uplift, Property 1: 根目录重导出文件纯净性
# ---------------------------------------------------------------------------

# 策略：生成纯重导出文件内容（应通过检测）
_pure_reexport_strategy: st.SearchStrategy[str] = st.builds(
    lambda imports, has_all, docstring: (
        ('"""Pure re-export file."""\n' if docstring else "")
        + "\n".join(imports)
        + ("\n__all__ = " + repr(["Sym" + str(i) for i in range(len(imports))]) if has_all else "")
    ),
    imports=st.lists(
        st.one_of(
            st.builds(
                lambda mod, name: f"from {mod} import {name}",
                mod=st.sampled_from(["os", "sys", "pathlib", "typing", "ast", "re"]),
                name=st.sampled_from(["Path", "Any", "List", "Dict", "Optional", "Union"]),
            ),
            st.builds(
                lambda mod: f"import {mod}",
                mod=st.sampled_from(["os", "sys", "pathlib", "typing", "ast", "re"]),
            ),
        ),
        min_size=0,
        max_size=5,
    ),
    has_all=st.booleans(),
    docstring=st.booleans(),
)

# 策略：生成包含 class 定义的文件内容（应被检测到）
_class_def_strategy: st.SearchStrategy[str] = st.builds(
    lambda name: f"class {name}:\n    pass\n",
    name=st.from_regex(r"[A-Z][a-zA-Z]{1,15}", fullmatch=True),
)

# 策略：生成包含函数定义的文件内容（应被检测到）
_func_def_strategy: st.SearchStrategy[str] = st.builds(
    lambda name: f"def {name}() -> None:\n    pass\n",
    name=st.from_regex(r"[a-z][a-z_]{1,15}", fullmatch=True),
)


@given(source=_pure_reexport_strategy)
@settings(max_examples=100)
def test_property_pure_reexport_passes_check(source: str) -> None:
    """
    **Validates: Requirements 1.1, 1.2, 1.3**

    对于任意纯重导出文件内容（仅含 import 和 __all__ 赋值），
    AST 检测逻辑应返回零违规。
    """
    tree: ast.Module = ast.parse(source)
    violations: list[tuple[int, str, str]] = _get_forbidden_nodes(tree)
    assert not violations, f"纯重导出内容被误报为包含定义:\n  源码: {source!r}\n  违规: {violations}"


@given(class_source=_class_def_strategy)
@settings(max_examples=100)
def test_property_class_def_detected(class_source: str) -> None:
    """
    **Validates: Requirements 1.1, 1.2, 1.3**

    对于任意包含 class 定义的文件内容，
    AST 检测逻辑应返回至少一个 ClassDef 违规。
    """
    tree: ast.Module = ast.parse(class_source)
    violations: list[tuple[int, str, str]] = _get_forbidden_nodes(tree)
    class_violations: list[tuple[int, str, str]] = [v for v in violations if v[1] == "ClassDef"]
    assert class_violations, f"未检测到 class 定义:\n  源码: {class_source!r}"


@given(func_source=_func_def_strategy)
@settings(max_examples=100)
def test_property_func_def_detected(func_source: str) -> None:
    """
    **Validates: Requirements 1.1, 1.2, 1.3**

    对于任意包含函数定义的文件内容，
    AST 检测逻辑应返回至少一个 FunctionDef 违规。
    """
    tree: ast.Module = ast.parse(func_source)
    violations: list[tuple[int, str, str]] = _get_forbidden_nodes(tree)
    func_violations: list[tuple[int, str, str]] = [v for v in violations if v[1] == "FunctionDef"]
    assert func_violations, f"未检测到函数定义:\n  源码: {func_source!r}"
