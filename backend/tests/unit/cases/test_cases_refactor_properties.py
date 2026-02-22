"""
属性测试：Cases App 架构整改正确性验证

# Feature: cases-app-refactor
"""

from __future__ import annotations

import ast
import re
import unicodedata
from pathlib import Path
from typing import Any

import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# 项目根目录
BACKEND_ROOT = Path(__file__).parent.parent.parent.parent
CASES_ROOT = BACKEND_ROOT / "apps" / "cases"


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _has_chinese(s: str) -> bool:
    """判断字符串是否包含中文字符。"""
    return any(unicodedata.category(c) in ("Lo",) and "\u4e00" <= c <= "\u9fff" for c in s)


def _is_gettext_call(node: ast.expr) -> bool:
    """判断 AST 节点是否是 _() 调用，或 _() % {} 这种 BinOp 模式。"""
    # 直接 _(...) 调用
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "_":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "_":
            return True
        return False
    # _("...") % {"key": val} 模式：BinOp(left=Call(_), op=Mod)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return _is_gettext_call(node.left)
    return False


def _collect_raise_exception_args(
    tree: ast.AST,
    exception_names: set[str],
) -> list[tuple[int, str, ast.expr]]:
    """
    收集所有 raise ExceptionType(arg0, ...) 语句中第一个参数。
    返回 [(lineno, exc_name, arg_node), ...]
    """
    results: list[tuple[int, str, ast.expr]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        exc = node.exc
        if exc is None:
            continue
        # raise ExcType(...)
        if isinstance(exc, ast.Call):
            func = exc.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in exception_names and exc.args:
                results.append((node.lineno, name, exc.args[0]))
    return results


def _collect_chinese_string_args_in_exceptions(
    tree: ast.AST,
) -> list[tuple[int, str]]:
    """
    收集异常构造函数参数中裸露的中文字符串（不在 _() 内）。
    返回 [(lineno, string_value), ...]
    """
    violations: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # 跳过 _() 调用本身
        if _is_gettext_call(node):
            continue
        # 检查是否是异常构造调用（func 是 Name 或 Attribute）
        func = node.func
        is_exc_call = isinstance(func, (ast.Name, ast.Attribute))
        if not is_exc_call:
            continue

        for arg in node.args:
            _check_bare_chinese(arg, node, violations)
        for kw in node.keywords:
            _check_bare_chinese(kw.value, node, violations)

    return violations


def _check_bare_chinese(
    node: ast.expr,
    parent_call: ast.Call,
    violations: list[tuple[int, str]],
) -> None:
    """递归检查节点中是否有裸露中文字符串（不在 _() 内）。"""
    if isinstance(node, ast.Constant) and isinstance(node.s, str) and _has_chinese(node.s):
        violations.append((node.lineno, node.s))
    elif isinstance(node, ast.JoinedStr):
        # f-string：检查其中的常量部分
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.s, str) and _has_chinese(value.s):
                violations.append((node.lineno, value.s))
    elif isinstance(node, ast.Call):
        # 如果是 _() 调用，跳过（已包装）
        if _is_gettext_call(node):
            return
        # 否则继续递归
        for arg in node.args:
            _check_bare_chinese(arg, node, violations)


# ---------------------------------------------------------------------------
# Property 1: CaseLogService 异常消息均已 i18n 包装
# Feature: cases-app-refactor, Property 1: CaseLogService 异常消息均已 i18n 包装
# Validates: Requirements 3.2, 3.3, 3.4
# ---------------------------------------------------------------------------


def test_property1_caselog_service_exceptions_are_i18n_wrapped() -> None:
    """
    **Validates: Requirements 3.2, 3.3, 3.4**

    AST 扫描 CaseLogService，验证所有 raise 语句中
    PermissionDenied/NotFoundError/ValidationException 的第一个参数是 _() 调用。
    """
    service_file = CASES_ROOT / "services" / "caselog_service.py"
    assert service_file.exists(), f"文件不存在: {service_file}"

    tree = ast.parse(service_file.read_text(encoding="utf-8"))
    target_exceptions = {"PermissionDenied", "NotFoundError", "ValidationException"}
    raises = _collect_raise_exception_args(tree, target_exceptions)

    assert raises, "未找到任何目标异常 raise 语句，请检查文件内容"

    violations: list[str] = []
    for lineno, exc_name, arg_node in raises:
        if not _is_gettext_call(arg_node):
            violations.append(
                f"  第 {lineno} 行 {exc_name}: 第一个参数不是 _() 调用，实际类型: {type(arg_node).__name__}"
            )

    assert not violations, "caselog_service.py 中以下异常消息未用 _() 包装:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# Property 2: 日志服务模块无裸露中文字符串
# Feature: cases-app-refactor, Property 2: 日志服务模块无裸露中文字符串
# Validates: Requirements 3.5, 3.6, 3.7, 3.8
# ---------------------------------------------------------------------------


def test_property2_log_services_no_bare_chinese_strings() -> None:
    """
    **Validates: Requirements 3.5, 3.6, 3.7, 3.8**

    AST 扫描 services/log/ 下 4 个文件，验证异常构造函数参数中
    无裸露中文字符串（包含中文字符的 ast.Constant 不在 _() 调用内）。
    """
    log_dir = CASES_ROOT / "services" / "log"
    target_files = [
        "case_log_mutation_service.py",
        "case_log_query_service.py",
        "case_log_attachment_service.py",
        "caselog_service_adapter.py",
    ]

    all_violations: list[str] = []

    for filename in target_files:
        filepath = log_dir / filename
        assert filepath.exists(), f"文件不存在: {filepath}"

        tree = ast.parse(filepath.read_text(encoding="utf-8"))
        violations = _collect_chinese_string_args_in_exceptions(tree)

        for lineno, text in violations:
            all_violations.append(f"  {filename}:{lineno} 裸露中文字符串: {text!r}")

    assert not all_violations, "以下文件存在未用 _() 包装的中文字符串:\n" + "\n".join(all_violations)


# ---------------------------------------------------------------------------
# Property 3: 文件验证常量唯一来源
# Feature: cases-app-refactor, Property 3: 文件验证常量唯一来源
# Validates: Requirements 5.1
# ---------------------------------------------------------------------------


def test_property3_no_duplicate_file_validation_constants() -> None:  # noqa: C901
    """
    **Validates: Requirements 5.1**

    AST 扫描 apps/cases/ 下所有 .py 文件（排除 utils.py），
    验证无 ALLOWED_EXTENSIONS 或 MAX_FILE_SIZE 的赋值定义。
    """
    forbidden_names = {"ALLOWED_EXTENSIONS", "MAX_FILE_SIZE"}
    violations: list[str] = []

    for py_file in sorted(CASES_ROOT.rglob("*.py")):
        if py_file.name == "utils.py":
            continue
        # 排除 __pycache__
        if "__pycache__" in py_file.parts:
            continue

        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        rel = py_file.relative_to(BACKEND_ROOT)

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in forbidden_names:
                        violations.append(f"  {rel}:{node.lineno} 定义了 {target.id}")
                    elif isinstance(target, ast.Attribute) and target.attr in forbidden_names:
                        violations.append(f"  {rel}:{node.lineno} 定义了 {target.attr}")
            elif isinstance(node, ast.AnnAssign):
                target = node.target
                if isinstance(target, ast.Name) and target.id in forbidden_names:
                    violations.append(f"  {rel}:{node.lineno} 定义了 {target.id}")
                elif isinstance(target, ast.Attribute) and target.attr in forbidden_names:
                    violations.append(f"  {rel}:{node.lineno} 定义了 {target.attr}")

    assert not violations, "以下文件重复定义了文件验证常量（应只在 utils.py 中定义）:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# Property 4: 文件验证一致性（hypothesis）
# Feature: cases-app-refactor, Property 4: 文件验证一致性
# Validates: Requirements 5.3
# ---------------------------------------------------------------------------

# 合法扩展名列表（用于生成测试数据）
_VALID_EXTS = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".jpg", ".jpeg", ".png"]
_INVALID_EXTS = [".exe", ".sh", ".py", ".txt", ".zip", ".mp4", ".csv", ".html", ""]

_filename_strategy = st.one_of(
    # 合法扩展名
    st.builds(
        lambda stem, ext: stem + ext,
        stem=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
            min_size=1,
            max_size=20,
        ),
        ext=st.sampled_from(_VALID_EXTS),
    ),
    # 非法扩展名
    st.builds(
        lambda stem, ext: stem + ext,
        stem=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
            min_size=1,
            max_size=20,
        ),
        ext=st.sampled_from(_INVALID_EXTS),
    ),
    # 无扩展名
    st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
        min_size=1,
        max_size=20,
    ),
)

_size_strategy = st.one_of(
    st.integers(min_value=0, max_value=50 * 1024 * 1024),  # 合法大小
    st.integers(min_value=50 * 1024 * 1024 + 1, max_value=200 * 1024 * 1024),  # 超大
    st.just(0),
    st.none(),
)


class _FakeFile:
    """模拟 UploadedFile，供 _validate_attachment 使用。"""

    def __init__(self, name: str, size: int | None) -> None:
        self.name = name
        self.size = size


@given(filename=_filename_strategy, size=_size_strategy)
@settings(max_examples=100)
def test_property4_file_validation_consistency(filename: str, size: int | None) -> None:
    """
    **Validates: Requirements 5.3**

    使用 hypothesis 生成随机 filename 和 size，
    对比 utils.validate_case_log_attachment 和 CaseLogService._validate_attachment 结果一致。
    """
    from apps.cases.utils import validate_case_log_attachment
    from apps.cases.services.caselog_service import CaseLogService
    from apps.core.exceptions import ValidationException

    # utils 函数结果
    utils_ok, utils_err = validate_case_log_attachment(filename, size)

    # CaseLogService._validate_attachment 结果
    svc = CaseLogService.__new__(CaseLogService)
    fake_file = _FakeFile(name=filename, size=size)
    try:
        svc._validate_attachment(fake_file)  # type: ignore[attr-defined]
        svc_ok = True
    except ValidationException:
        svc_ok = False

    assert utils_ok == svc_ok, (
        f"验证结果不一致: filename={filename!r}, size={size}\n"
        f"  utils.validate_case_log_attachment -> ok={utils_ok}\n"
        f"  CaseLogService._validate_attachment -> ok={svc_ok}"
    )


# ---------------------------------------------------------------------------
# Property 5: nested_admin 条件导入唯一定义
# Feature: cases-app-refactor, Property 5: nested_admin 条件导入唯一定义
# Validates: Requirements 7.6
# ---------------------------------------------------------------------------


def test_property5_no_direct_nested_admin_import_outside_base() -> None:
    """
    **Validates: Requirements 7.6**

    AST 扫描 apps/cases/admin/ 下所有 .py 文件（排除 base.py），
    验证源码中无 `import nested_admin`（直接 import，非 from）。
    """
    admin_dir = CASES_ROOT / "admin"
    violations: list[str] = []

    for py_file in sorted(admin_dir.rglob("*.py")):
        if py_file.name == "base.py":
            continue
        if "__pycache__" in py_file.parts:
            continue

        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        rel = py_file.relative_to(BACKEND_ROOT)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "nested_admin" or alias.name.startswith("nested_admin."):
                        violations.append(f"  {rel}:{node.lineno} import nested_admin")

    assert not violations, "以下文件直接 import nested_admin（应只在 admin/base.py 中定义）:\n" + "\n".join(violations)
