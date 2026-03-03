"""
Bug Condition Exploration Tests - Organization 模块架构违规检测

这些测试编码的是"期望行为"（修复后的正确状态）。
在未修复代码上运行时，测试会 FAIL，证明 bug 存在。
修复完成后，测试会 PASS，确认 bug 已修复。

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# 项目根目录（backend/）
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Organization 模块目录
ORG_DIR = BACKEND_DIR / "apps" / "organization"

# C3: 需要检查 from __future__ import annotations 的 22 个文件
EXPECTED_FUTURE_ANNOTATIONS_FILES: list[str] = [
    "schemas.py",
    "dtos.py",
    "middleware.py",
    "services/organization_access_policy.py",
    "services/organization_service_adapter.py",
    "services/dto_assemblers.py",
    "services/account_credential_service.py",
    "services/lawfirm_service.py",
    "services/team_service.py",
    "services/account_credential_admin_service.py",
    "services/org_access_computation_service.py",
    "services/__init__.py",
    "admin/__init__.py",
    "admin/team_admin.py",
    "api/__init__.py",
    "api/lawyer_api.py",
    "api/lawfirm_api.py",
    "api/team_api.py",
    "api/accountcredential_api.py",
    "api/auth_api.py",
    "apps.py",
    "forms.py",
    "views.py",
]


# ---------------------------------------------------------------------------
# C1: organization_access_policy.py 不应使用 ForbiddenError，应使用 PermissionDenied
# ---------------------------------------------------------------------------
def test_c1_no_forbidden_error_in_access_policy() -> None:
    """
    期望行为：organization_access_policy.py 应使用 PermissionDenied，
    不应使用 ForbiddenError。
    未修复时 FAIL（文件中存在 ForbiddenError），修复后 PASS。

    **Validates: Requirements 1.1**
    """
    policy_file = ORG_DIR / "services" / "organization_access_policy.py"
    source = policy_file.read_text(encoding="utf-8")

    assert "ForbiddenError" not in source, (
        "BUG C1: organization_access_policy.py 中使用了 ForbiddenError，"
        "应统一使用 PermissionDenied（来自 apps.core.exceptions）"
    )


def test_c1_uses_permission_denied_import() -> None:
    """
    期望行为：organization_access_policy.py 应导入 PermissionDenied。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.1**
    """
    policy_file = ORG_DIR / "services" / "organization_access_policy.py"
    source = policy_file.read_text(encoding="utf-8")

    assert "PermissionDenied" in source, (
        "BUG C1: organization_access_policy.py 未导入 PermissionDenied，应从 apps.core.exceptions 导入 PermissionDenied"
    )


# ---------------------------------------------------------------------------
# C2: LawyerOut 中 resolve 方法不应是 @staticmethod
# ---------------------------------------------------------------------------
def test_c2_resolve_license_pdf_url_not_staticmethod() -> None:
    """
    期望行为：LawyerOut.resolve_license_pdf_url 不应使用 @staticmethod 装饰器。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.2**
    """
    from apps.organization.schemas import LawyerOut

    method = getattr(LawyerOut, "resolve_license_pdf_url", None)
    assert method is not None, "LawyerOut 缺少 resolve_license_pdf_url 方法"

    assert not isinstance(
        inspect.getattr_static(LawyerOut, "resolve_license_pdf_url"),
        staticmethod,
    ), (
        "BUG C2: LawyerOut.resolve_license_pdf_url 使用了 @staticmethod，"
        "违反四层架构规范（Schema 层不应有 @staticmethod 业务逻辑）"
    )


def test_c2_resolve_law_firm_detail_not_staticmethod() -> None:
    """
    期望行为：LawyerOut.resolve_law_firm_detail 不应使用 @staticmethod 装饰器。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.2**
    """
    from apps.organization.schemas import LawyerOut

    method = getattr(LawyerOut, "resolve_law_firm_detail", None)
    assert method is not None, "LawyerOut 缺少 resolve_law_firm_detail 方法"

    assert not isinstance(
        inspect.getattr_static(LawyerOut, "resolve_law_firm_detail"),
        staticmethod,
    ), (
        "BUG C2: LawyerOut.resolve_law_firm_detail 使用了 @staticmethod，"
        "违反四层架构规范（Schema 层不应有 @staticmethod 业务逻辑）"
    )


# ---------------------------------------------------------------------------
# C3: 所有 23 个文件应包含 from __future__ import annotations
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel_path", EXPECTED_FUTURE_ANNOTATIONS_FILES)
def test_c3_future_annotations_present(rel_path: str) -> None:
    """
    期望行为：organization 模块的每个 Python 文件顶部应包含
    ``from __future__ import annotations``。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.3**
    """
    target_file = ORG_DIR / rel_path
    assert target_file.exists(), f"文件不存在: {rel_path}"

    source = target_file.read_text(encoding="utf-8")

    assert "from __future__ import annotations" in source, (
        f"BUG C3: {rel_path} 缺少 'from __future__ import annotations'，"
        "导致类型注解在运行时被求值，无法通过 mypy --strict 检查"
    )


@given(file_index=st.integers(min_value=0, max_value=len(EXPECTED_FUTURE_ANNOTATIONS_FILES) - 1))
@settings(max_examples=5)
def test_c3_property_all_files_have_future_annotations(file_index: int) -> None:
    """
    属性测试：对于任意选取的 organization 模块文件，
    均应包含 from __future__ import annotations。

    **Validates: Requirements 1.3**
    """
    rel_path = EXPECTED_FUTURE_ANNOTATIONS_FILES[file_index]
    target_file = ORG_DIR / rel_path

    assert target_file.exists(), f"文件不存在: {rel_path}"

    source = target_file.read_text(encoding="utf-8")
    assert "from __future__ import annotations" in source, (
        f"BUG C3: {rel_path} 缺少 'from __future__ import annotations'"
    )


# ---------------------------------------------------------------------------
# C4: LawFirmServiceAdapter 不应包含独立的 _to_dto() 方法
# ---------------------------------------------------------------------------
def test_c4_lawfirm_adapter_no_independent_to_dto() -> None:
    """
    期望行为：LawFirmServiceAdapter 不应包含独立的 _to_dto() 方法，
    应委托给 LawFirmDtoAssembler.to_dto()。
    未修复时 FAIL（方法存在），修复后 PASS。

    **Validates: Requirements 1.4**
    """
    from apps.organization.services.lawfirm_service import LawFirmServiceAdapter

    assert not hasattr(LawFirmServiceAdapter, "_to_dto"), (
        "BUG C4: LawFirmServiceAdapter 包含独立的 _to_dto() 方法，"
        "与 LawFirmDtoAssembler.to_dto() 逻辑重复，"
        "应委托给 LawFirmDtoAssembler"
    )


def test_c4_dto_assemblers_no_cast_type_ignore() -> None:
    """
    期望行为：dto_assemblers.py 不应使用 cast + # type: ignore 绕过类型检查。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.4**
    """
    assembler_file = ORG_DIR / "services" / "dto_assemblers.py"
    source = assembler_file.read_text(encoding="utf-8")

    issues: list[str] = []
    if "cast(" in source:
        issues.append("使用了 cast()")
    if "# type: ignore" in source:
        issues.append("使用了 # type: ignore")

    assert not issues, (
        f"BUG C4: dto_assemblers.py 中存在类型注解问题: {', '.join(issues)}。应使用正确的类型注解替代 cast/type: ignore"
    )


# ---------------------------------------------------------------------------
# C5: middleware.py 的 _compute_org_access 不应直接调用 ServiceLocator
# ---------------------------------------------------------------------------
def test_c5_middleware_no_direct_service_locator() -> None:
    """
    期望行为：OrgAccessMiddleware._compute_org_access 不应直接调用
    ServiceLocator.get_case_service()，应委托给 OrgAccessComputationService。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.5**
    """
    middleware_file = ORG_DIR / "middleware.py"
    source = middleware_file.read_text(encoding="utf-8")

    # 解析 AST 找到 _compute_org_access 方法体
    tree = ast.parse(source)
    method_source: str | None = None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_compute_org_access":
            method_source = ast.get_source_segment(source, node)
            break

    assert method_source is not None, "未找到 _compute_org_access 方法"

    assert "ServiceLocator" not in method_source, (
        "BUG C5: _compute_org_access() 直接调用 ServiceLocator.get_case_service()，"
        "应委托给 OrgAccessComputationService.compute()"
    )


def test_c5_middleware_delegates_to_org_access_service() -> None:
    """
    期望行为：OrgAccessMiddleware._compute_org_access 应委托给
    OrgAccessComputationService 进行计算。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.5**
    """
    middleware_file = ORG_DIR / "middleware.py"
    source = middleware_file.read_text(encoding="utf-8")

    tree = ast.parse(source)
    method_source: str | None = None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_compute_org_access":
            method_source = ast.get_source_segment(source, node)
            break

    assert method_source is not None, "未找到 _compute_org_access 方法"

    # 检查是否委托给 OrgAccessComputationService 或通过 wiring 工厂函数
    delegates = (
        "OrgAccessComputationService" in method_source or "build_org_access_computation_service" in method_source
    )
    assert delegates, (
        "BUG C5: _compute_org_access() 未委托给 OrgAccessComputationService，"
        "而是内联了与 OrgAccessComputationService.compute() 重复的逻辑"
    )
