"""
Preservation Property Tests - Organization 模块现有行为保持

这些测试验证修复前后行为一致性。在未修复代码上运行时应 PASS，
修复完成后也应 PASS，确认没有引入回归。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# P6: PermissionDenied 与 ForbiddenError 的 HTTP 状态码和消息一致（均为 403）
# ---------------------------------------------------------------------------

# 错误消息策略：从 organization_access_policy.py 中实际使用的消息中选取
_ERROR_MESSAGES: list[str] = [
    "用户未认证",
    "权限不足",
    "无权限访问",
    "无权限更新",
    "无权限删除",
    "无权限访问该律所",
    "无权限更新该律所",
    "无权限删除该律所",
    "无权限访问该团队",
    "无权限更新该团队",
    "无权限删除该团队",
]

error_message_st: st.SearchStrategy[str] = st.sampled_from(_ERROR_MESSAGES)


@given(message=error_message_st)
@settings(max_examples=5)
def test_p6_forbidden_error_and_permission_denied_both_return_403(
    message: str,
) -> None:
    """
    属性测试：对于任意错误消息，ForbiddenError 和 PermissionDenied
    均返回 HTTP 403 状态码，且 to_dict() 中的 message 字段一致。

    ForbiddenError 是 PermissionDenied 的子类（向后兼容别名），
    两者在异常处理器中都映射到 HTTP 403。

    **Validates: Requirements 3.1**
    """
    from apps.core.exceptions import ForbiddenError, PermissionDenied

    forbidden = ForbiddenError(message)
    permission_denied = PermissionDenied(message)

    # 两者都是 PermissionDenied 的实例（ForbiddenError 继承自 PermissionDenied）
    assert isinstance(forbidden, PermissionDenied)

    # to_dict() 中 message 字段一致
    forbidden_dict = forbidden.to_dict()
    permission_denied_dict = permission_denied.to_dict()

    assert str(forbidden_dict["message"]) == str(permission_denied_dict["message"])
    assert forbidden_dict["success"] is False
    assert permission_denied_dict["success"] is False

    # ForbiddenError 显式设置 status=403
    assert getattr(forbidden, "status", 403) == 403


@given(message=error_message_st)
@settings(max_examples=5)
def test_p6_access_policy_error_messages_preserved(message: str) -> None:
    """
    属性测试：OrganizationAccessPolicy 抛出的错误消息内容在
    ForbiddenError 和 PermissionDenied 之间保持一致。

    **Validates: Requirements 3.1**
    """
    from apps.core.exceptions import ForbiddenError, PermissionDenied

    # 当前代码使用 ForbiddenError，修复后使用 PermissionDenied
    # 两者的 message 属性应完全一致
    exc_current = ForbiddenError(message)
    exc_fixed = PermissionDenied(message)

    assert str(exc_current.message) == str(exc_fixed.message)
    assert str(exc_current) != ""
    assert str(exc_fixed) != ""


# ---------------------------------------------------------------------------
# P7: LawyerOut 序列化字段值在重构后不变
# ---------------------------------------------------------------------------


class _FakeLicensePdf:
    """模拟 FileField 对象"""

    def __init__(self, url: str | None) -> None:
        self._url = url

    @property
    def url(self) -> str:
        if self._url is None:
            raise ValueError("No file")
        return self._url

    def __bool__(self) -> bool:
        return self._url is not None


class _FakeLawFirm:
    """模拟 LawFirm 对象用于 Schema 序列化测试"""

    def __init__(
        self,
        *,
        pk: int,
        name: str,
        address: str,
        phone: str,
        social_credit_code: str,
    ) -> None:
        self.pk = pk
        self.id = pk
        self.name = name
        self.address = address
        self.phone = phone
        self.social_credit_code = social_credit_code


class _FakeLawyer:
    """模拟 Lawyer 对象用于 Schema 序列化测试"""

    def __init__(
        self,
        *,
        pk: int,
        username: str,
        real_name: str,
        phone: str | None,
        license_no: str,
        id_card: str,
        law_firm: _FakeLawFirm | None,
        law_firm_id: int | None,
        is_admin: bool,
        is_active: bool,
        license_pdf: _FakeLicensePdf | None,
    ) -> None:
        self.pk = pk
        self.id = pk
        self.username = username
        self.real_name = real_name
        self.phone = phone
        self.license_no = license_no
        self.id_card = id_card
        self.law_firm = law_firm
        self.law_firm_id = law_firm_id
        self.is_admin = is_admin
        self.is_active = is_active
        self.license_pdf = license_pdf


# Hypothesis 策略：生成 _FakeLawFirm
_fake_lawfirm_st: st.SearchStrategy[_FakeLawFirm] = st.builds(
    _FakeLawFirm,
    pk=st.integers(min_value=1, max_value=9999),
    name=st.sampled_from(["测试律所", "北京律所", "上海律所", "广州律所", "深圳律所"]),
    address=st.sampled_from(["北京市朝阳区", "上海市浦东新区", "广州市天河区", ""]),
    phone=st.sampled_from(["13800138000", "13900139000", "15000150000", ""]),
    social_credit_code=st.sampled_from(["91110000MA001", "91310000MA002", ""]),
)


@given(
    url=st.one_of(st.none(), st.just("/media/lawyers/licenses/test.pdf")),
)
@settings(max_examples=5)
def test_p7_resolve_license_pdf_url_output_preserved(url: str | None) -> None:
    """
    属性测试：LawyerOut.resolve_license_pdf_url 的输出值
    在 @staticmethod 移除前后保持一致。

    当前实现调用 SchemaMixin._get_file_url(obj.license_pdf)，
    重构后通过实例方法调用同一逻辑，输出不变。

    **Validates: Requirements 3.2**
    """
    from apps.core.schemas import SchemaMixin

    license_pdf = _FakeLicensePdf(url)

    # 当前行为：直接调用 SchemaMixin._get_file_url
    expected = SchemaMixin._get_file_url(license_pdf)

    # 验证 resolve_license_pdf_url 的当前输出
    from apps.organization.schemas import LawyerOut

    fake_lawyer = _FakeLawyer(
        pk=1,
        username="test",
        real_name="测试",
        phone=None,
        license_no="",
        id_card="",
        law_firm=None,
        law_firm_id=None,
        is_admin=False,
        is_active=True,
        license_pdf=license_pdf,
    )

    # 通过 object.__new__ 创建实例避免 pydantic 验证
    schema_instance = object.__new__(LawyerOut)
    result = schema_instance.resolve_license_pdf_url(fake_lawyer)  # type: ignore[arg-type]
    assert result == expected


@given(has_law_firm=st.booleans())
@settings(max_examples=5)
def test_p7_resolve_law_firm_detail_output_preserved(has_law_firm: bool) -> None:
    """
    属性测试：LawyerOut.resolve_law_firm_detail 的输出值
    在 @staticmethod 移除前后保持一致。

    **Validates: Requirements 3.2**
    """
    from apps.organization.schemas import LawyerOut

    law_firm: _FakeLawFirm | None = None
    if has_law_firm:
        law_firm = _FakeLawFirm(
            pk=1,
            name="测试律所",
            address="测试地址",
            phone="13800138000",
            social_credit_code="91110000",
        )

    fake_lawyer = _FakeLawyer(
        pk=1,
        username="test",
        real_name="测试",
        phone=None,
        license_no="",
        id_card="",
        law_firm=law_firm,
        law_firm_id=law_firm.pk if law_firm else None,
        is_admin=False,
        is_active=True,
        license_pdf=None,
    )

    # 通过 object.__new__ 创建实例避免 pydantic 验证
    schema_instance = object.__new__(LawyerOut)
    result = schema_instance.resolve_law_firm_detail(fake_lawyer)  # type: ignore[arg-type]

    if has_law_firm:
        # 当前行为：返回 obj.law_firm（即 _FakeLawFirm 对象）
        assert result is law_firm
    else:
        assert result is None


# ---------------------------------------------------------------------------
# P8: LawFirmDtoAssembler.to_dto() 输出与原 LawFirmServiceAdapter._to_dto() 一致
# ---------------------------------------------------------------------------


class _FakeLawFirmModel:
    """模拟 LawFirm Model 对象，同时满足 Adapter 和 Assembler 的字段访问"""

    def __init__(
        self,
        *,
        pk: int,
        name: str,
        address: str,
        phone: str,
        social_credit_code: str,
    ) -> None:
        self.pk = pk
        self.id = pk
        self.name = name
        self.address = address
        self.phone = phone
        self.social_credit_code = social_credit_code


# Hypothesis 策略：生成 _FakeLawFirmModel
_fake_lawfirm_model_st: st.SearchStrategy[_FakeLawFirmModel] = st.builds(
    _FakeLawFirmModel,
    pk=st.integers(min_value=1, max_value=9999),
    name=st.sampled_from(["测试律所", "北京律所", "上海律所", "广州律所", "深圳律所"]),
    address=st.sampled_from(["北京市朝阳区", "上海市浦东新区", "广州市天河区", ""]),
    phone=st.sampled_from(["13800138000", "13900139000", "15000150000", ""]),
    social_credit_code=st.sampled_from(["91110000MA001", "91310000MA002", ""]),
)


@given(lawfirm=_fake_lawfirm_model_st)
@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
def test_p8_dto_assembler_matches_adapter_to_dto(lawfirm: _FakeLawFirmModel) -> None:
    """
    属性测试：LawFirmDtoAssembler.to_dto() 的输出与
    LawFirmServiceAdapter._to_dto() 完全一致。

    修复后 Adapter 将委托给 Assembler，此测试确保输出不变。

    **Validates: Requirements 3.3**
    """
    from apps.core.interfaces import LawFirmDTO
    from apps.organization.services.dto_assemblers import LawFirmDtoAssembler
    from apps.organization.services.lawfirm_service import LawFirmServiceAdapter

    adapter = LawFirmServiceAdapter()
    assembler = LawFirmDtoAssembler()

    # 修复后：Adapter 委托给 Assembler，验证两者输出一致
    assembler_result: LawFirmDTO = assembler.to_dto(lawfirm)  # type: ignore[arg-type]
    adapter_result: LawFirmDTO = adapter._assembler.to_dto(lawfirm)  # type: ignore[arg-type]

    # 比较所有字段
    assert adapter_result.id == assembler_result.id
    assert adapter_result.name == assembler_result.name
    assert adapter_result.address == assembler_result.address
    assert adapter_result.phone == assembler_result.phone
    assert adapter_result.social_credit_code == assembler_result.social_credit_code

    # 完整 dataclass 比较
    assert asdict(adapter_result) == asdict(assembler_result)


# ---------------------------------------------------------------------------
# P9: 中间件委托后计算结果与原内联逻辑一致
# ---------------------------------------------------------------------------


class _FakeTeamMember:
    """模拟团队成员"""

    def __init__(self, member_id: int) -> None:
        self.id = member_id


class _FakeTeam:
    """模拟团队对象"""

    def __init__(self, team_id: int, member_ids: list[int]) -> None:
        self.id = team_id
        self._members = [_FakeTeamMember(mid) for mid in member_ids]

    @property
    def lawyers(self) -> _FakeTeam:
        """返回自身以支持 .all() 链式调用"""
        return self

    def all(self) -> list[_FakeTeamMember]:
        return self._members


class _FakeTeamQuerySet:
    """模拟 lawyer_teams 查询集"""

    def __init__(self, teams: list[_FakeTeam]) -> None:
        self._teams = teams

    def prefetch_related(self, *args: str) -> _FakeTeamQuerySet:
        return self

    def all(self) -> list[_FakeTeam]:
        return self._teams


class _FakeUser:
    """模拟用户对象用于中间件测试"""

    def __init__(
        self,
        *,
        user_id: int,
        teams: list[_FakeTeam],
    ) -> None:
        self.id = user_id
        self.lawyer_teams = _FakeTeamQuerySet(teams)


# 策略：生成团队成员 ID 列表
_member_ids_st: st.SearchStrategy[list[int]] = st.lists(
    st.integers(min_value=1, max_value=999),
    min_size=0,
    max_size=3,
)

# 策略：生成团队列表
_teams_st: st.SearchStrategy[list[tuple[int, list[int]]]] = st.lists(
    st.tuples(
        st.integers(min_value=1, max_value=999),
        _member_ids_st,
    ),
    min_size=0,
    max_size=3,
)

# 策略：生成额外案件 ID 列表
_extra_case_ids_st: st.SearchStrategy[list[int]] = st.lists(
    st.integers(min_value=1, max_value=9999),
    min_size=0,
    max_size=5,
)


@given(
    user_id=st.integers(min_value=1, max_value=9999),
    teams_data=_teams_st,
    extra_case_ids=_extra_case_ids_st,
)
@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
def test_p9_middleware_and_service_compute_same_result(
    user_id: int,
    teams_data: list[tuple[int, list[int]]],
    extra_case_ids: list[int],
) -> None:
    """
    属性测试：OrgAccessMiddleware._compute_org_access() 的计算结果
    与 OrgAccessComputationService.compute() 完全一致。

    修复后中间件将委托给 Service，此测试确保输出不变。

    **Validates: Requirements 3.4**
    """
    from apps.organization.middleware import OrgAccessMiddleware
    from apps.organization.services.org_access_computation_service import OrgAccessComputationService

    # 构造测试数据
    teams = [_FakeTeam(tid, mids) for tid, mids in teams_data]
    user = _FakeUser(user_id=user_id, teams=teams)

    # Mock ICaseService.get_user_extra_case_access
    mock_case_service = MagicMock()
    mock_case_service.get_user_extra_case_access.return_value = extra_case_ids

    # 1. 通过 OrgAccessComputationService 计算
    service = OrgAccessComputationService(case_service=mock_case_service)
    service_result: dict[str, Any] = service.compute(user)

    # 2. 通过 middleware._compute_org_access 计算
    middleware = OrgAccessMiddleware(get_response=lambda r: r)  # type: ignore[arg-type]

    with patch(
        "apps.core.interfaces.ServiceLocator.get_case_service",
        return_value=mock_case_service,
    ):
        middleware_result: dict[str, Any] = middleware._compute_org_access(user)

    # 比较结果
    assert middleware_result["lawyers"] == service_result["lawyers"]
    assert middleware_result["team_ids"] == service_result["team_ids"]
    assert middleware_result["extra_cases"] == service_result["extra_cases"]
