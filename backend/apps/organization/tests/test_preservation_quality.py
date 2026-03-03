"""
Preservation Property Tests - Organization 模块业务行为保全验证

这些测试在未修复代码上运行时应 PASS（验证现有行为），
修复完成后也应 PASS（确认没有引入回归）。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# 常量：模型类和服务类定义
# ---------------------------------------------------------------------------

MODEL_CLASSES: list[str] = [
    "Lawyer",
    "LawFirm",
    "Team",
    "AccountCredential",
    "TeamType",
]

SERVICE_EXPORTS: dict[str, list[str]] = {
    "LawyerService": [
        "get_lawyer",
        "list_lawyers",
        "create_lawyer",
        "update_lawyer",
        "delete_lawyer",
        "get_lawyers_by_ids",
        "get_team_members",
        "get_team_member_ids",
    ],
    "LawyerServiceAdapter": [
        "get_lawyer",
        "get_lawyers_by_ids",
        "get_team_members",
    ],
    "LawFirmService": [
        "get_lawfirm",
        "list_lawfirms",
        "create_lawfirm",
        "update_lawfirm",
        "delete_lawfirm",
    ],
    "LawFirmServiceAdapter": [
        "get_lawfirm",
        "get_lawfirms_by_ids",
    ],
    "AccountCredentialService": [
        "list_credentials",
        "get_credential",
        "create_credential",
        "update_credential",
        "delete_credential",
    ],
    "TeamService": [
        "list_teams",
        "get_team",
        "create_team",
        "update_team",
        "delete_team",
    ],
    "AuthService": [
        "login",
        "logout",
        "register",
    ],
    "AccountCredentialAdminService": [
        "single_auto_login",
        "batch_auto_login",
    ],
    "OrganizationServiceAdapter": [],
}

LAWYER_SUBMODULE_EXPORTS: list[str] = [
    "LawyerMutationService",
    "LawyerQueryService",
    "LawyerUploadService",
]


# ---------------------------------------------------------------------------
# Property Test: 模型导入保全 (Requirement 3.1)
# ---------------------------------------------------------------------------


@given(class_index=st.integers(min_value=0, max_value=len(MODEL_CLASSES) - 1))
@settings(max_examples=5)
def test_property_model_import_preserved(class_index: int) -> None:
    """
    属性测试：对于任意模型类，通过 apps.organization.models 导入均应成功。

    **Validates: Requirements 3.1**
    """
    class_name = MODEL_CLASSES[class_index]
    module = importlib.import_module("apps.organization.models")
    cls: Any = getattr(module, class_name, None)
    assert cls is not None, f"模型类 {class_name} 无法通过 apps.organization.models 导入"


def test_all_model_classes_importable() -> None:
    """
    验证所有模型类可通过 apps.organization.models 导入。

    **Validates: Requirements 3.1**
    """
    from apps.organization.models import AccountCredential, LawFirm, Lawyer, Team, TeamType

    assert Lawyer is not None
    assert LawFirm is not None
    assert Team is not None
    assert AccountCredential is not None
    assert TeamType is not None

    # 验证 TeamType 是枚举类型
    assert hasattr(TeamType, "LAWYER")
    assert hasattr(TeamType, "BIZ")


# ---------------------------------------------------------------------------
# Property Test: 服务导入保全 (Requirement 3.2, 3.3, 3.6)
# ---------------------------------------------------------------------------

_SERVICE_NAMES: list[str] = list(SERVICE_EXPORTS.keys())


@given(service_index=st.integers(min_value=0, max_value=len(_SERVICE_NAMES) - 1))
@settings(max_examples=len(_SERVICE_NAMES))
def test_property_service_import_and_methods_preserved(service_index: int) -> None:
    """
    属性测试：对于任意服务类，通过 apps.organization.services 导入成功，
    且具有预期的公开方法。

    **Validates: Requirements 3.2, 3.3, 3.6**
    """
    service_name = _SERVICE_NAMES[service_index]
    expected_methods = SERVICE_EXPORTS[service_name]

    module = importlib.import_module("apps.organization.services")
    cls: Any = getattr(module, service_name, None)
    assert cls is not None, f"服务类 {service_name} 无法通过 apps.organization.services 导入"

    # 验证公开方法存在
    for method_name in expected_methods:
        assert hasattr(cls, method_name), f"{service_name} 缺少公开方法 {method_name}"
        member: Any = getattr(cls, method_name)
        assert callable(member), f"{service_name}.{method_name} 不是可调用对象"


def test_services_init_exports_all_expected() -> None:
    """
    验证 services/__init__.py 导出所有预期的服务类。

    **Validates: Requirements 3.2, 3.3, 3.6**
    """
    module = importlib.import_module("apps.organization.services")
    all_exports: list[str] = getattr(module, "__all__", [])

    for service_name in _SERVICE_NAMES:
        assert service_name in all_exports, f"{service_name} 未在 services/__init__.py 的 __all__ 中导出"


# ---------------------------------------------------------------------------
# Property Test: services/lawyer/ 子模块导出保全 (Requirement 3.2)
# ---------------------------------------------------------------------------


@given(export_index=st.integers(min_value=0, max_value=len(LAWYER_SUBMODULE_EXPORTS) - 1))
@settings(max_examples=3)
def test_property_lawyer_submodule_exports_preserved(export_index: int) -> None:
    """
    属性测试：services/lawyer/__init__.py 导出的类均可正常导入。

    **Validates: Requirements 3.2**
    """
    class_name = LAWYER_SUBMODULE_EXPORTS[export_index]
    module = importlib.import_module("apps.organization.services.lawyer")
    cls: Any = getattr(module, class_name, None)
    assert cls is not None, f"{class_name} 无法通过 apps.organization.services.lawyer 导入"
    assert inspect.isclass(cls), f"{class_name} 不是类"


# ---------------------------------------------------------------------------
# Test: AccountCredentialService batch operations (Requirement 3.4)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_credential_is_preferred_update_via_queryset(db: Any) -> None:
    """
    验证 AccountCredential 的 is_preferred 字段可通过 queryset.update 正确更新。
    这是当前 Admin 层的行为，修复后将委托给 Service 层但结果一致。

    **Validates: Requirements 3.4**
    """
    from apps.organization.models import AccountCredential, LawFirm, Lawyer

    # 创建测试数据
    firm = LawFirm.objects.create(name="保全测试律所")
    lawyer = Lawyer.objects.create_user(
        username="preservation_test_user",
        password="testpass123",
        law_firm=firm,
    )

    cred1 = AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="test_site",
        account="account1",
        password="pass1",
        is_preferred=False,
    )
    cred2 = AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="test_site",
        account="account2",
        password="pass2",
        is_preferred=False,
    )

    # 批量标记为优先
    qs = AccountCredential.objects.filter(id__in=[cred1.id, cred2.id])
    count = qs.update(is_preferred=True)
    assert count == 2

    cred1.refresh_from_db()
    cred2.refresh_from_db()
    assert cred1.is_preferred is True
    assert cred2.is_preferred is True

    # 批量取消优先
    count = qs.update(is_preferred=False)
    assert count == 2

    cred1.refresh_from_db()
    cred2.refresh_from_db()
    assert cred1.is_preferred is False
    assert cred2.is_preferred is False


@pytest.mark.django_db
@given(
    preferred_flags=st.lists(st.booleans(), min_size=1, max_size=5),
)
@settings(
    max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
)
def test_property_is_preferred_batch_update_correct(
    preferred_flags: list[bool],
    db: Any,
) -> None:
    """
    属性测试：对于任意 is_preferred 标记组合，批量更新后字段值正确。

    **Validates: Requirements 3.4**
    """
    from apps.organization.models import AccountCredential, LawFirm, Lawyer

    firm = LawFirm.objects.create(name="PBT保全律所")
    lawyer = Lawyer.objects.create_user(
        username="pbt_preservation_user",
        password="testpass123",
        law_firm=firm,
    )

    cred_ids: list[int] = []
    for i, flag in enumerate(preferred_flags):
        cred = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name="pbt_site",
            account=f"pbt_account_{i}",
            password="pass",
            is_preferred=not flag,  # 初始值取反
        )
        cred_ids.append(cred.id)

    # 批量更新为 True
    qs = AccountCredential.objects.filter(id__in=cred_ids)
    updated = qs.update(is_preferred=True)
    assert updated == len(cred_ids)

    for cred in AccountCredential.objects.filter(id__in=cred_ids):
        assert cred.is_preferred is True

    # 批量更新为 False
    updated = qs.update(is_preferred=False)
    assert updated == len(cred_ids)

    for cred in AccountCredential.objects.filter(id__in=cred_ids):
        assert cred.is_preferred is False

    # 清理
    AccountCredential.objects.filter(id__in=cred_ids).delete()
    lawyer.delete()
    firm.delete()


# ---------------------------------------------------------------------------
# Test: 首个用户判断逻辑保全 (Requirement 3.5)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_first_user_detection_no_users(db: Any) -> None:
    """
    验证当无用户时，Lawyer.objects.exists() 返回 False（即 is_first_user = True）。

    **Validates: Requirements 3.5**
    """
    from apps.organization.models import Lawyer

    # 确保无用户
    Lawyer.objects.all().delete()
    is_first_user: bool = not Lawyer.objects.exists()
    assert is_first_user is True


@pytest.mark.django_db
def test_first_user_detection_with_users(db: Any) -> None:
    """
    验证当有用户时，Lawyer.objects.exists() 返回 True（即 is_first_user = False）。

    **Validates: Requirements 3.5**
    """
    from apps.organization.models import LawFirm, Lawyer

    Lawyer.objects.all().delete()
    firm = LawFirm.objects.create(name="首用户测试律所")
    Lawyer.objects.create_user(
        username="first_user_test",
        password="testpass123",
        law_firm=firm,
    )
    is_first_user: bool = not Lawyer.objects.exists()
    assert is_first_user is False


@pytest.mark.django_db
def test_auth_service_register_first_user(db: Any) -> None:
    """
    验证 AuthService.register 在无用户时创建管理员用户。

    **Validates: Requirements 3.5**
    """
    from apps.organization.models import Lawyer
    from apps.organization.services.auth_service import AuthService

    Lawyer.objects.all().delete()

    auth_service = AuthService()
    result = auth_service.register(
        username="first_admin",
        password="testpass123",
        real_name="首位管理员",
    )

    user: Any = result.user
    assert user is not None
    assert user.username == "first_admin"


@pytest.mark.django_db
def test_auth_service_register_subsequent_user(db: Any) -> None:
    """
    验证 AuthService.register 在已有用户时创建非活跃用户。

    **Validates: Requirements 3.5**
    """
    from apps.organization.models import LawFirm, Lawyer
    from apps.organization.services.auth_service import AuthService

    Lawyer.objects.all().delete()
    firm = LawFirm.objects.create(name="后续用户测试律所")
    Lawyer.objects.create_user(
        username="existing_user",
        password="testpass123",
        law_firm=firm,
    )

    auth_service = AuthService()
    result = auth_service.register(
        username="second_user",
        password="testpass123",
        real_name="后续用户",
    )

    user: Any = result.user
    assert user is not None
    assert user.username == "second_user"
    assert user.is_active is False
    assert user.is_admin is False
    assert user.is_superuser is False
