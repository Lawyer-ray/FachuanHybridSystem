"""Cases Admin 行级访问控制测试（审计五-2 专项）.

覆盖：CaseAdmin 详情/自定义视图的行级校验、CaseLogAdmin 列表行级过滤、
批量添加日志的案件归属校验。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from apps.cases.admin.case_admin import CaseAdmin
from apps.cases.admin.caselog_admin import CaseLogAdmin
from apps.cases.models import Case, CaseAssignment, CaseLog
from apps.contracts.models import Contract
from apps.organization.models import Lawyer

User = get_user_model()


def _grant_case_perm(user: Lawyer, codename: str) -> Lawyer:
    """授予 cases 应用的模型权限并重取用户（刷新权限缓存）。"""
    user.user_permissions.add(Permission.objects.get(content_type__app_label="cases", codename=codename))
    refreshed = User.objects.get(pk=user.pk)
    return refreshed  # type: ignore[no-any-return]


def _make_request(method: str, path: str, user: Any, json_payload: dict[str, Any] | None = None) -> Any:
    factory = RequestFactory()
    if json_payload is not None:
        request = factory.post(path, data=json.dumps(json_payload), content_type="application/json")
    else:
        request = getattr(factory, method.lower())(path)
    request.user = user
    return request


@pytest.mark.django_db
class TestCaseAdminRowLevelAccess:
    """CaseAdmin 详情/自定义视图的行级权限校验"""

    def test_detail_view_denies_staff_without_case_access(self) -> None:
        """受限 staff（有模块级查看权限但未参与案件）访问他人案件详情 → 403"""
        contract = Contract.objects.create(name="行级测试合同", case_type="civil")
        case = Case.objects.create(name="他人案件", contract=contract)
        staff = _grant_case_perm(
            Lawyer.objects.create_user(username="rl_staff", real_name="受限律师", is_staff=True),
            "view_case",
        )

        request = _make_request("GET", f"/admin/cases/case/{case.pk}/detail/", staff)

        with pytest.raises(PermissionDenied):
            CaseAdmin(Case, AdminSite()).detail_view(request, case.pk)

    def test_open_folder_view_denies_staff_without_case_access(self) -> None:
        """受限 staff 打开他人案件文件夹 → PermissionDenied（403）"""
        contract = Contract.objects.create(name="行级测试合同2", case_type="civil")
        case = Case.objects.create(name="他人案件2", contract=contract)
        staff = _grant_case_perm(
            Lawyer.objects.create_user(username="rl_staff2", real_name="受限律师2", is_staff=True),
            "view_case",
        )

        request = _make_request("POST", f"/admin/cases/case/{case.pk}/open-folder/", staff)

        with pytest.raises(PermissionDenied):
            CaseAdmin(Case, AdminSite()).open_folder_view(request, case.pk)

    def test_open_folder_view_allows_assigned_staff(self) -> None:
        """承办律师通过行级校验后，因未绑定文件夹返回 404（而非 403）"""
        contract = Contract.objects.create(name="行级测试合同3", case_type="civil")
        case = Case.objects.create(name="本人案件", contract=contract)
        staff = _grant_case_perm(
            Lawyer.objects.create_user(username="rl_owner", real_name="承办律师", is_staff=True),
            "view_case",
        )
        CaseAssignment.objects.create(case=case, lawyer=staff)

        request = _make_request("POST", f"/admin/cases/case/{case.pk}/open-folder/", staff)

        response = CaseAdmin(Case, AdminSite()).open_folder_view(request, case.pk)
        assert response.status_code == 404
        # 行级校验通过：404 的成因是未绑定文件夹，而非权限拒绝
        assert json.loads(response.content)["error"] == "未绑定文件夹"


@pytest.mark.django_db
class TestCaseLogAdminRowFilter:
    """CaseLogAdmin 列表行级过滤（以 case 关联 join）"""

    def test_get_queryset_filters_by_case_access(self) -> None:
        """非管理员用户只能看到可访问案件下的日志"""
        contract = Contract.objects.create(name="过滤合同", case_type="civil")
        mine = Case.objects.create(name="可见案件", contract=contract)
        other = Case.objects.create(name="不可见案件", contract=contract)
        staff = Lawyer.objects.create_user(username="filter_staff", real_name="过滤律师")
        CaseAssignment.objects.create(case=mine, lawyer=staff)
        CaseLog.objects.create(case=mine, actor=staff, content="本人案件日志")
        CaseLog.objects.create(case=other, actor=staff, content="他人案件日志")

        request = _make_request("GET", "/admin/cases/caselog/", staff)

        qs = CaseLogAdmin(CaseLog, AdminSite()).get_queryset(request)
        assert set(qs.values_list("case_id", flat=True)) == {mine.pk}

    def test_get_queryset_admin_sees_all(self) -> None:
        """is_admin（superuser）用户看到全部日志"""
        contract = Contract.objects.create(name="过滤合同2", case_type="civil")
        case = Case.objects.create(name="案件A", contract=contract)
        actor = Lawyer.objects.create_user(username="filter_admin", real_name="过滤管理员")
        CaseLog.objects.create(case=case, actor=actor, content="日志")

        request = _make_request("GET", "/admin/cases/caselog/", User(is_superuser=True, is_staff=True, is_admin=True))

        qs = CaseLogAdmin(CaseLog, AdminSite()).get_queryset(request)
        assert qs.count() == 1


@pytest.mark.django_db
class TestCaseLogBatchAddRowLevel:
    """批量添加日志的案件归属校验"""

    def _make_staff(self, username: str) -> Lawyer:
        staff = Lawyer.objects.create_user(username=username, real_name=username, is_staff=True)
        return _grant_case_perm(staff, "add_caselog")

    def test_submit_denies_foreign_case(self) -> None:
        """提交包含不可访问案件的 case_ids → 403 且不落库"""
        contract = Contract.objects.create(name="批量合同", case_type="civil")
        mine = Case.objects.create(name="本人案件B", contract=contract)
        other = Case.objects.create(name="他人案件B", contract=contract)
        staff = self._make_staff("batch_staff")
        CaseAssignment.objects.create(case=mine, lawyer=staff)

        request = _make_request(
            "POST",
            "/admin/cases/caselog/batch-add/submit/",
            staff,
            json_payload={"case_ids": [mine.pk, other.pk], "content": "批量日志"},
        )

        response = CaseLogAdmin(CaseLog, AdminSite()).batch_add_submit_view(request)
        assert response.status_code == 403
        assert not CaseLog.objects.filter(case_id=other.pk).exists()

    def test_submit_allows_own_cases(self) -> None:
        """全部案件可访问时正常创建日志"""
        contract = Contract.objects.create(name="批量合同2", case_type="civil")
        mine = Case.objects.create(name="本人案件C", contract=contract)
        staff = self._make_staff("batch_staff2")
        CaseAssignment.objects.create(case=mine, lawyer=staff)

        request = _make_request(
            "POST",
            "/admin/cases/caselog/batch-add/submit/",
            staff,
            json_payload={"case_ids": [mine.pk], "content": "批量日志"},
        )

        response = CaseLogAdmin(CaseLog, AdminSite()).batch_add_submit_view(request)
        assert response.status_code == 200
        assert CaseLog.objects.filter(case_id=mine.pk, content="批量日志").exists()
