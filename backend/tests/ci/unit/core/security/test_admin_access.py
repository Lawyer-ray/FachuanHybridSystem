"""core.security.admin_access 泛型函数单测（解耦 2026-10-19）。

覆盖新增的三个泛型：admin_accessible_queryset / apply_related_admin_access_filter /
ensure_admin_object_access——管理员全量、普通用户行级、无权时业务 PermissionDenied
转换为 django PermissionDenied（admin 渲染 403）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.test import RequestFactory

from apps.cases.models import Case, CaseAssignment, CaseLog
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.contracts.models import Contract
from apps.core.exceptions import PermissionDenied as BizPermissionDenied
from apps.core.security.admin_access import (
    admin_accessible_queryset,
    apply_related_admin_access_filter,
    ensure_admin_object_access,
    is_admin_user,
)

User = get_user_model()


def _request(user: Any, *, perm_open_access: bool = False) -> Any:
    request: Any = RequestFactory().get("/admin/")
    request.user = user
    request.perm_open_access = perm_open_access
    return request


class TestIsAdminUserReExport:
    """解耦（2026-10-19）：message_hub / reminders 的本地同体实现已删除，统一走 core。"""

    def test_is_admin_user_flags(self) -> None:
        assert is_admin_user(None) is False
        assert is_admin_user(SimpleNamespace(is_staff=True)) is False
        assert is_admin_user(SimpleNamespace(is_admin=True)) is True
        assert is_admin_user(SimpleNamespace(is_superuser=True)) is True


class TestAdminAccessibleQueryset:
    """admin_accessible_queryset：管理员全量 / 普通用户行级 / perm_open_access 全量。"""

    @pytest.mark.django_db
    def test_admin_sees_all(self) -> None:
        contract = Contract.objects.create(name="泛型合同A", case_type="civil")
        case_a = Case.objects.create(name="案件A", contract=contract)
        case_b = Case.objects.create(name="案件B", contract=contract)
        admin = User(is_superuser=True, is_staff=True, is_admin=True)

        qs = admin_accessible_queryset(_request(admin), Case, CaseAccessPolicy())

        assert set(qs.values_list("pk", flat=True)) == {case_a.pk, case_b.pk}

    @pytest.mark.django_db
    def test_assigned_staff_sees_only_assigned(self) -> None:
        contract = Contract.objects.create(name="泛型合同B", case_type="civil")
        mine = Case.objects.create(name="本人案件", contract=contract)
        Case.objects.create(name="他人案件", contract=contract)
        staff = User.objects.create_user(username="gen_staff", real_name="泛型律师", is_staff=True)
        CaseAssignment.objects.create(case=mine, lawyer=staff)

        qs = admin_accessible_queryset(_request(staff), Case, CaseAccessPolicy())

        assert set(qs.values_list("pk", flat=True)) == {mine.pk}

    @pytest.mark.django_db
    def test_unassigned_staff_sees_none(self) -> None:
        Contract.objects.create(name="泛型合同C", case_type="civil")
        staff = User.objects.create_user(username="gen_staff_none", real_name="无权律师", is_staff=True)

        qs = admin_accessible_queryset(_request(staff), Case, CaseAccessPolicy())

        assert qs.count() == 0

    @pytest.mark.django_db
    def test_perm_open_access_sees_all(self) -> None:
        contract = Contract.objects.create(name="泛型合同D", case_type="civil")
        Case.objects.create(name="开放案件", contract=contract)
        staff = User.objects.create_user(username="gen_staff_open", real_name="开放律师", is_staff=True)

        qs = admin_accessible_queryset(_request(staff, perm_open_access=True), Case, CaseAccessPolicy())

        assert qs.count() == 1


class TestApplyRelatedAdminAccessFilter:
    """apply_related_admin_access_filter：按外键关联父对象行级过滤。"""

    @pytest.mark.django_db
    def test_filters_logs_by_case_access(self) -> None:
        contract = Contract.objects.create(name="泛型合同E", case_type="civil")
        mine = Case.objects.create(name="可见案件", contract=contract)
        other = Case.objects.create(name="不可见案件", contract=contract)
        staff = User.objects.create_user(username="rel_staff", real_name="关联律师", is_staff=True)
        CaseAssignment.objects.create(case=mine, lawyer=staff)
        CaseLog.objects.create(case=mine, actor=staff, content="本人案件日志")
        CaseLog.objects.create(case=other, actor=staff, content="他人案件日志")

        qs = apply_related_admin_access_filter(
            _request(staff), CaseLog.objects.all(), fk="case_id", model=Case, policy=CaseAccessPolicy()
        )

        assert set(qs.values_list("case_id", flat=True)) == {mine.pk}

    @pytest.mark.django_db
    def test_admin_sees_all_related(self) -> None:
        contract = Contract.objects.create(name="泛型合同F", case_type="civil")
        case = Case.objects.create(name="管理员案件", contract=contract)
        actor = User.objects.create_user(username="rel_actor", real_name="记录人")
        CaseLog.objects.create(case=case, actor=actor, content="日志")
        admin = User(is_superuser=True, is_staff=True, is_admin=True)

        qs = apply_related_admin_access_filter(
            _request(admin), CaseLog.objects.all(), fk="case_id", model=Case, policy=CaseAccessPolicy()
        )

        assert qs.count() == 1


class _RecordingPolicy:
    """记录 ensure_access_ctx 入参的假策略（无 DB 依赖）。"""

    def __init__(self, *, raise_denied: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.raise_denied = raise_denied

    def ensure_access_ctx(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.raise_denied:
            raise BizPermissionDenied(message="无权限访问此案件", code="PERMISSION_DENIED")


class TestEnsureAdminObjectAccess:
    """ensure_admin_object_access：入参透传 + 业务异常 → django PermissionDenied（403）。"""

    def test_passes_id_ctx_and_obj_to_policy(self) -> None:
        policy = _RecordingPolicy()
        user = SimpleNamespace(id=1, is_authenticated=True, is_admin=False)
        request = _request(user)
        case = SimpleNamespace(pk=5)

        ensure_admin_object_access(
            request,
            policy,
            object_id=5,
            message="无权限访问此案件",
            id_kwarg="case_id",
            obj=case,
            obj_kwarg="case",
        )

        assert len(policy.calls) == 1
        call = policy.calls[0]
        assert call["case_id"] == 5
        assert call["case"] is case
        ctx = call["ctx"]
        assert ctx.user is user
        assert ctx.perm_open_access is False

    def test_obj_kwarg_none_passes_none_like_direct_call(self) -> None:
        policy = _RecordingPolicy()

        ensure_admin_object_access(
            _request(SimpleNamespace(id=2, is_authenticated=True)),
            policy,
            object_id=7,
            message="无权限访问该合同",
            id_kwarg="contract_id",
            obj=None,
            obj_kwarg="contract",
        )

        assert policy.calls[0]["contract"] is None

    def test_converts_biz_permission_denied_to_django_403(self) -> None:
        policy = _RecordingPolicy(raise_denied=True)

        with pytest.raises(DjangoPermissionDenied) as excinfo:
            ensure_admin_object_access(
                _request(SimpleNamespace(id=3, is_authenticated=True)),
                policy,
                object_id=9,
                message="无权限访问此案件",
                id_kwarg="case_id",
            )

        assert "无权限访问此案件" in str(excinfo.value)

    @pytest.mark.django_db
    def test_real_policy_admin_passes_and_staff_denied(self) -> None:
        """接真实 CaseAccessPolicy：管理员放行、无权普通用户 403、被指派用户放行。"""
        contract = Contract.objects.create(name="泛型合同G", case_type="civil")
        case = Case.objects.create(name="真实策略案件", contract=contract)
        admin = User(is_superuser=True, is_staff=True, is_admin=True)
        outsider = User.objects.create_user(username="gen_outsider", real_name="无权律师", is_staff=True)
        assignee = User.objects.create_user(username="gen_assignee", real_name="承办律师", is_staff=True)
        CaseAssignment.objects.create(case=case, lawyer=assignee)

        ensure_admin_object_access(
            _request(admin), CaseAccessPolicy(), object_id=case.pk, message="无权限访问此案件", id_kwarg="case_id"
        )
        ensure_admin_object_access(
            _request(assignee),
            CaseAccessPolicy(),
            object_id=case.pk,
            message="无权限访问此案件",
            id_kwarg="case_id",
            obj=case,
            obj_kwarg="case",
        )
        with pytest.raises(DjangoPermissionDenied):
            ensure_admin_object_access(
                _request(outsider),
                CaseAccessPolicy(),
                object_id=case.pk,
                message="无权限访问此案件",
                id_kwarg="case_id",
            )
