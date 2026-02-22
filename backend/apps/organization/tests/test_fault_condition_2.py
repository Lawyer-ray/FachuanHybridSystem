"""
Bug Condition Exploration Tests (Round 2) - Organization 模块第二轮架构违规检测

这些测试编码的是"期望行为"（修复后的正确状态）。
在未修复代码上运行时，测试会 FAIL，证明 bug 存在。
修复完成后，测试会 PASS，确认 bug 已修复。

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10**
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# 项目根目录（backend/）
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Organization 模块目录
ORG_DIR = BACKEND_DIR / "apps" / "organization"

# C3: 需要检查用户获取方式的 API 文件
USER_RETRIEVAL_API_FILES: list[str] = [
    "api/team_api.py",
    "api/accountcredential_api.py",
]

# C4: 所有 API 文件（检查 type: ignore[arg-type]）
ALL_API_FILES: list[str] = [
    "api/lawyer_api.py",
    "api/lawfirm_api.py",
    "api/team_api.py",
    "api/accountcredential_api.py",
]

# C6: 需要检查权限方法的 Service 文件
PERMISSION_SERVICE_FILES: list[str] = [
    "services/lawfirm_service.py",
    "services/team_service.py",
]

# C5: OrganizationServiceAdapter 中需要实现的方法
ADAPTER_TODO_METHODS: list[str] = [
    "get_law_firm",
    "get_team",
    "get_lawyers_in_organization",
]


# ---------------------------------------------------------------------------
# C1: AccountCredentialOut 的 resolve_created_at / resolve_updated_at
#     不应是 @staticmethod
# ---------------------------------------------------------------------------
def test_c1_resolve_created_at_not_staticmethod() -> None:
    """
    期望行为：AccountCredentialOut.resolve_created_at 不应使用 @staticmethod。
    未修复时 FAIL（方法是 staticmethod），修复后 PASS。

    **Validates: Requirements 1.1**
    """
    from apps.organization.schemas import AccountCredentialOut

    raw = inspect.getattr_static(AccountCredentialOut, "resolve_created_at")
    assert not isinstance(raw, staticmethod), (
        "BUG C1: AccountCredentialOut.resolve_created_at 使用了 @staticmethod，"
        "应改为实例方法通过继承调用 SchemaMixin._resolve_datetime_iso()"
    )


def test_c1_resolve_updated_at_not_staticmethod() -> None:
    """
    期望行为：AccountCredentialOut.resolve_updated_at 不应使用 @staticmethod。
    未修复时 FAIL（方法是 staticmethod），修复后 PASS。

    **Validates: Requirements 1.1**
    """
    from apps.organization.schemas import AccountCredentialOut

    raw = inspect.getattr_static(AccountCredentialOut, "resolve_updated_at")
    assert not isinstance(raw, staticmethod), (
        "BUG C1: AccountCredentialOut.resolve_updated_at 使用了 @staticmethod，"
        "应改为实例方法通过继承调用 SchemaMixin._resolve_datetime_iso()"
    )


@given(method_index=st.integers(min_value=0, max_value=1))
@settings(max_examples=5)
def test_c1_property_no_staticmethod_resolvers(method_index: int) -> None:
    """
    属性测试：AccountCredentialOut 的 resolve_created_at 和 resolve_updated_at
    均不应是 @staticmethod。

    **Validates: Requirements 1.1**
    """
    from apps.organization.schemas import AccountCredentialOut

    methods = ["resolve_created_at", "resolve_updated_at"]
    method_name = methods[method_index]
    raw = inspect.getattr_static(AccountCredentialOut, method_name)
    assert not isinstance(raw, staticmethod), (
        f"BUG C1: AccountCredentialOut.{method_name} 使用了 @staticmethod"
    )


# ---------------------------------------------------------------------------
# C2: LawyerServiceAdapter 不应包含独立的 _to_dto() 内联逻辑，
#     应委托给 LawyerDtoAssembler
# ---------------------------------------------------------------------------
def test_c2_lawyer_adapter_delegates_to_assembler() -> None:
    """
    期望行为：LawyerServiceAdapter._to_dto() 应委托给 LawyerDtoAssembler.to_dto()，
    不应包含独立的内联 DTO 构造逻辑。
    未修复时 FAIL（方法体包含 LawyerDTO(...) 内联构造），修复后 PASS。

    **Validates: Requirements 1.2**
    """
    adapter_file = ORG_DIR / "services" / "lawyer" / "adapter.py"
    source = adapter_file.read_text(encoding="utf-8")

    tree = ast.parse(source)
    method_source: str | None = None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_to_dto":
                # 检查是否在 LawyerServiceAdapter 类中
                method_source = ast.get_source_segment(source, node)
                break

    assert method_source is not None, "未找到 LawyerServiceAdapter._to_dto 方法"

    # 期望方法体委托给 assembler，不应包含内联的字段映射
    has_inline_dto = "LawyerDTO(" in method_source and "lawyer.id" in method_source
    assert not has_inline_dto, (
        "BUG C2: LawyerServiceAdapter._to_dto() 包含独立的内联 DTO 构造逻辑，"
        "与 LawyerDtoAssembler.to_dto() 重复，应委托给 LawyerDtoAssembler"
    )


# ---------------------------------------------------------------------------
# C3: team_api.py 和 accountcredential_api.py 应使用
#     getattr(request, "auth", None) or getattr(request, "user", None)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel_path", USER_RETRIEVAL_API_FILES)
def test_c3_api_uses_auth_or_user(rel_path: str) -> None:
    """
    期望行为：API 文件应使用 getattr(request, "auth", None) or getattr(request, "user", None)
    获取用户，与 lawyer_api.py 和 lawfirm_api.py 保持一致。
    未修复时 FAIL（仅使用 getattr(request, "user", None)），修复后 PASS。

    **Validates: Requirements 1.3**
    """
    target_file = ORG_DIR / rel_path
    source = target_file.read_text(encoding="utf-8")

    # 检查是否包含 auth 属性获取
    has_auth_pattern = 'getattr(request, "auth", None)' in source
    assert has_auth_pattern, (
        f"BUG C3: {rel_path} 未使用 getattr(request, \"auth\", None) 获取用户，"
        "应统一使用 getattr(request, \"auth\", None) or getattr(request, \"user\", None)"
    )


@given(file_index=st.integers(min_value=0, max_value=len(USER_RETRIEVAL_API_FILES) - 1))
@settings(max_examples=5)
def test_c3_property_all_apis_use_auth_or_user(file_index: int) -> None:
    """
    属性测试：所有需要检查的 API 文件均应使用 auth or user 方式获取用户。

    **Validates: Requirements 1.3**
    """
    rel_path = USER_RETRIEVAL_API_FILES[file_index]
    target_file = ORG_DIR / rel_path
    source = target_file.read_text(encoding="utf-8")

    assert 'getattr(request, "auth", None)' in source, (
        f"BUG C3: {rel_path} 未使用 auth 属性获取用户"
    )


# ---------------------------------------------------------------------------
# C4: API 文件中不应存在 # type: ignore[arg-type]
#     （File(None) 的 # type: ignore[misc] 除外）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel_path", ALL_API_FILES)
def test_c4_no_type_ignore_arg_type(rel_path: str) -> None:
    """
    期望行为：API 文件中不应存在 # type: ignore[arg-type]。
    未修复时 FAIL（存在 type: ignore[arg-type]），修复后 PASS。

    **Validates: Requirements 1.4**
    """
    target_file = ORG_DIR / rel_path
    source = target_file.read_text(encoding="utf-8")

    lines_with_ignore: list[str] = []
    for i, line in enumerate(source.splitlines(), 1):
        if "# type: ignore[arg-type]" in line:
            lines_with_ignore.append(f"  L{i}: {line.strip()}")

    assert not lines_with_ignore, (
        f"BUG C4: {rel_path} 中存在 # type: ignore[arg-type]:\n"
        + "\n".join(lines_with_ignore)
        + "\n应通过修改 Service 方法签名（user: Lawyer | None）消除"
    )


@given(file_index=st.integers(min_value=0, max_value=len(ALL_API_FILES) - 1))
@settings(max_examples=5)
def test_c4_property_no_type_ignore_arg_type(file_index: int) -> None:
    """
    属性测试：所有 API 文件均不应包含 # type: ignore[arg-type]。

    **Validates: Requirements 1.4**
    """
    rel_path = ALL_API_FILES[file_index]
    target_file = ORG_DIR / rel_path
    source = target_file.read_text(encoding="utf-8")

    assert "# type: ignore[arg-type]" not in source, (
        f"BUG C4: {rel_path} 中存在 # type: ignore[arg-type]"
    )


# ---------------------------------------------------------------------------
# C5: OrganizationServiceAdapter 的 get_law_firm()、get_team()、
#     get_lawyers_in_organization() 不应包含 TODO 且不应返回 stub 值
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("method_name", ADAPTER_TODO_METHODS)
def test_c5_adapter_no_todo_in_methods(method_name: str) -> None:
    """
    期望行为：OrganizationServiceAdapter 的方法不应包含 TODO 注释。
    未修复时 FAIL（方法体包含 TODO），修复后 PASS。

    **Validates: Requirements 1.5**
    """
    adapter_file = ORG_DIR / "services" / "organization_service_adapter.py"
    source = adapter_file.read_text(encoding="utf-8")

    tree = ast.parse(source)
    method_source: str | None = None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == method_name:
                method_source = ast.get_source_segment(source, node)
                break

    assert method_source is not None, f"未找到 {method_name} 方法"

    assert "TODO" not in method_source, (
        f"BUG C5: OrganizationServiceAdapter.{method_name}() 包含 TODO 注释，"
        "应委托给对应 Service 返回实际数据"
    )


@given(method_index=st.integers(min_value=0, max_value=len(ADAPTER_TODO_METHODS) - 1))
@settings(max_examples=5)
def test_c5_property_adapter_no_todo(method_index: int) -> None:
    """
    属性测试：OrganizationServiceAdapter 的所有待实现方法均不应包含 TODO。

    **Validates: Requirements 1.5**
    """
    method_name = ADAPTER_TODO_METHODS[method_index]
    adapter_file = ORG_DIR / "services" / "organization_service_adapter.py"
    source = adapter_file.read_text(encoding="utf-8")

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == method_name:
                method_source = ast.get_source_segment(source, node)
                assert method_source is not None
                assert "TODO" not in method_source, (
                    f"BUG C5: OrganizationServiceAdapter.{method_name}() 包含 TODO"
                )
                return

    pytest.fail(f"未找到 {method_name} 方法")


# ---------------------------------------------------------------------------
# C6: LawFirmService 和 TeamService 不应包含 _check_*_permission 方法
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel_path", PERMISSION_SERVICE_FILES)
def test_c6_no_check_permission_methods(rel_path: str) -> None:
    """
    期望行为：Service 文件不应包含 _check_*_permission 方法，
    应委托给 OrganizationAccessPolicy。
    未修复时 FAIL（存在 _check_*_permission 方法），修复后 PASS。

    **Validates: Requirements 1.6**
    """
    target_file = ORG_DIR / rel_path
    source = target_file.read_text(encoding="utf-8")

    tree = ast.parse(source)
    permission_methods: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if re.match(r"_check_\w+_permission", node.name):
                permission_methods.append(node.name)

    assert not permission_methods, (
        f"BUG C6: {rel_path} 包含权限检查方法: {permission_methods}，"
        "应委托给 OrganizationAccessPolicy"
    )


@given(file_index=st.integers(min_value=0, max_value=len(PERMISSION_SERVICE_FILES) - 1))
@settings(max_examples=5)
def test_c6_property_no_check_permission(file_index: int) -> None:
    """
    属性测试：LawFirmService 和 TeamService 均不应包含 _check_*_permission 方法。

    **Validates: Requirements 1.6**
    """
    rel_path = PERMISSION_SERVICE_FILES[file_index]
    target_file = ORG_DIR / rel_path
    source = target_file.read_text(encoding="utf-8")

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert not re.match(r"_check_\w+_permission", node.name), (
                f"BUG C6: {rel_path} 包含 {node.name}，应委托给 OrganizationAccessPolicy"
            )


# ---------------------------------------------------------------------------
# C7: single_auto_login 中 error_message 不应使用 # type: ignore
# ---------------------------------------------------------------------------
def test_c7_no_type_ignore_for_error_message() -> None:
    """
    期望行为：single_auto_login 中传递 error_message 时不应使用 # type: ignore，
    应使用 str(_(...)) 将 LazyString 转为 str。
    未修复时 FAIL（存在 # type: ignore），修复后 PASS。

    **Validates: Requirements 1.7**
    """
    service_file = ORG_DIR / "services" / "account_credential_admin_service.py"
    source = service_file.read_text(encoding="utf-8")

    tree = ast.parse(source)
    method_source: str | None = None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "single_auto_login":
                method_source = ast.get_source_segment(source, node)
                break

    assert method_source is not None, "未找到 single_auto_login 方法"

    # 检查 error_message 相关行是否包含 # type: ignore
    lines_with_ignore: list[str] = []
    for i, line in enumerate(method_source.splitlines(), 1):
        if "error_message" in line and "# type: ignore" in line:
            lines_with_ignore.append(f"  L{i}: {line.strip()}")

    assert not lines_with_ignore, (
        "BUG C7: single_auto_login 中 error_message 使用了 # type: ignore:\n"
        + "\n".join(lines_with_ignore)
        + "\n应使用 str(_(...)) 将 LazyString 转为 str"
    )


# ---------------------------------------------------------------------------
# C8: LawyerRegistrationForm.save() 不应包含 is_staff、is_superuser、is_admin
#     设置逻辑
# ---------------------------------------------------------------------------
def test_c8_form_save_no_business_logic() -> None:
    """
    期望行为：LawyerRegistrationForm.save() 不应包含管理员权限设置逻辑
    （is_staff、is_superuser、is_admin），业务逻辑应在 Service 层。
    未修复时 FAIL（包含业务逻辑），修复后 PASS。

    **Validates: Requirements 1.8**
    """
    forms_file = ORG_DIR / "forms.py"
    source = forms_file.read_text(encoding="utf-8")

    tree = ast.parse(source)
    save_source: str | None = None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "save":
                save_source = ast.get_source_segment(source, node)
                break

    assert save_source is not None, "未找到 LawyerRegistrationForm.save() 方法"

    business_attrs = ["is_staff", "is_superuser", "is_admin"]
    found_attrs: list[str] = []
    for attr in business_attrs:
        if attr in save_source:
            found_attrs.append(attr)

    assert not found_attrs, (
        f"BUG C8: LawyerRegistrationForm.save() 包含业务逻辑属性: {found_attrs}，"
        "应将管理员权限设置逻辑委托给 AuthService.register()"
    )


# ---------------------------------------------------------------------------
# C9: lawfirm_service.py 不应导入未使用的 cast
# ---------------------------------------------------------------------------
def test_c9_no_unused_cast_import() -> None:
    """
    期望行为：lawfirm_service.py 不应导入未使用的 cast。
    未修复时 FAIL（导入了 cast 但未使用），修复后 PASS。

    **Validates: Requirements 1.9**
    """
    service_file = ORG_DIR / "services" / "lawfirm_service.py"
    source = service_file.read_text(encoding="utf-8")

    tree = ast.parse(source)

    # 检查是否从 typing 导入了 cast
    imports_cast = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "typing" and node.names:
                for alias in node.names:
                    if alias.name == "cast":
                        imports_cast = True

    if not imports_cast:
        # 没有导入 cast，测试通过
        return

    # 如果导入了 cast，检查是否在非导入语句中使用
    # 排除导入行本身，检查 cast( 是否出现在代码中
    lines = source.splitlines()
    uses_cast = False
    for line in lines:
        stripped = line.strip()
        # 跳过导入行
        if stripped.startswith("from ") or stripped.startswith("import "):
            continue
        if "cast(" in stripped:
            uses_cast = True
            break

    assert uses_cast, (
        "BUG C9: lawfirm_service.py 导入了 cast 但未使用，"
        "应移除未使用的导入"
    )


# ---------------------------------------------------------------------------
# C10: mark_as_preferred 和 unmark_as_preferred 不应使用 _(f"...") 格式
# ---------------------------------------------------------------------------
def test_c10_no_fstring_in_gettext() -> None:
    """
    期望行为：mark_as_preferred 和 unmark_as_preferred 不应使用 _(f"...") 格式，
    应使用 ngettext 或 _("...%(count)d...") % {...} 格式。
    未修复时 FAIL（使用了 _(f"...")），修复后 PASS。

    **Validates: Requirements 1.10**
    """
    admin_file = ORG_DIR / "admin" / "accountcredential_admin.py"
    source = admin_file.read_text(encoding="utf-8")

    methods_to_check = ["mark_as_preferred", "unmark_as_preferred"]

    tree = ast.parse(source)
    for method_name in methods_to_check:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == method_name:
                    method_source = ast.get_source_segment(source, node)
                    assert method_source is not None, f"未找到 {method_name} 方法源码"

                    # 检查是否使用了 _(f"...") 模式
                    has_fstring_gettext = bool(re.search(r'_\(f["\']', method_source))
                    assert not has_fstring_gettext, (
                        f"BUG C10: {method_name} 使用了 _(f\"...\") 格式，"
                        "i18n 工具无法正确提取翻译字符串，"
                        "应使用 ngettext 或 _(\"...%(count)d...\") % {{...}} 格式"
                    )


@given(method_index=st.integers(min_value=0, max_value=1))
@settings(max_examples=5)
def test_c10_property_no_fstring_in_gettext(method_index: int) -> None:
    """
    属性测试：mark_as_preferred 和 unmark_as_preferred 均不应使用 _(f"...") 格式。

    **Validates: Requirements 1.10**
    """
    admin_file = ORG_DIR / "admin" / "accountcredential_admin.py"
    source = admin_file.read_text(encoding="utf-8")

    methods = ["mark_as_preferred", "unmark_as_preferred"]
    method_name = methods[method_index]

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == method_name:
                method_source = ast.get_source_segment(source, node)
                assert method_source is not None
                assert not re.search(r'_\(f["\']', method_source), (
                    f"BUG C10: {method_name} 使用了 _(f\"...\") 格式"
                )
                return

    pytest.fail(f"未找到 {method_name} 方法")
