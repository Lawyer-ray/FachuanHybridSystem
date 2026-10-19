"""Evidence Admin 测试 - EvidenceListAdmin, EvidenceItemAdmin, EvidenceGroupAdmin"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from apps.cases.models import Case, CaseAssignment
from apps.contracts.models import Contract
from apps.evidence.admin.evidence_admin import EvidenceListAdmin
from apps.evidence.admin.evidence_item_admin import EvidenceItemAdmin
from apps.evidence.admin.group_admin import EvidenceGroupAdmin
from apps.evidence.models import EvidenceGroup, EvidenceItem, EvidenceList, EvidenceListProxy
from apps.organization.models import Lawyer

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    # 安全审计（2026-10-19）：行级过滤上线后，未挂律所的 is_admin 管理员保持全量可见，
    # 测试请求统一携带 is_admin（与生产 create_superuser 口径一致）
    request.user = User(is_superuser=True, is_staff=True, is_admin=True)
    return request


def _create_case(name: str = "证据测试案件") -> Case:
    contract = Contract.objects.create(name=f"证据测试合同-{name}", case_type="civil")
    return Case.objects.create(name=name, contract=contract)


@pytest.mark.django_db
class TestEvidenceListAdmin:
    """EvidenceListAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = EvidenceListAdmin(EvidenceList, AdminSite())
        assert "title" in admin_obj.list_display
        assert "case_display" in admin_obj.list_display
        assert "list_type" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 包含 case 和 created_by"""
        admin_obj = EvidenceListAdmin(EvidenceList, AdminSite())
        assert "case" in admin_obj.list_select_related
        assert "created_by" in admin_obj.list_select_related

    def test_get_queryset_annotate_item_count(self) -> None:
        """get_queryset 应使用 annotate(Count) 计算 item_count"""
        case = _create_case()
        elist = EvidenceList.objects.create(case=case, title="证据清单1", list_type="previous", order=1)
        EvidenceItem.objects.create(evidence_list=elist, order=1, name="证据1")
        EvidenceItem.objects.create(evidence_list=elist, order=2, name="证据2")

        admin_obj = EvidenceListAdmin(EvidenceList, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 1
        assert results[0].item_count == 2


@pytest.mark.django_db
class TestEvidenceItemAdmin:
    """EvidenceItemAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = EvidenceItemAdmin(EvidenceItem, AdminSite())
        assert "order" in admin_obj.list_display
        assert "name" in admin_obj.list_display
        assert "evidence_type" in admin_obj.list_display

    def test_search_fields(self) -> None:
        """search_fields 包含 name"""
        admin_obj = EvidenceItemAdmin(EvidenceItem, AdminSite())
        assert "name" in admin_obj.search_fields


@pytest.mark.django_db
class TestEvidenceGroupAdmin:
    """EvidenceGroupAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = EvidenceGroupAdmin(EvidenceGroup, AdminSite())
        assert "name" in admin_obj.list_display
        assert "case" in admin_obj.list_display
        assert "item_count" in admin_obj.list_display

    def test_get_queryset_annotate_item_count(self) -> None:
        """get_queryset 应使用 annotate(Count) 计算 item_count"""
        case = _create_case("分组测试案件")
        elist = EvidenceList.objects.create(case=case, title="分组证据清单", list_type="previous", order=1)
        item1 = EvidenceItem.objects.create(evidence_list=elist, order=1, name="分组证据1")
        item2 = EvidenceItem.objects.create(evidence_list=elist, order=2, name="分组证据2")
        group = EvidenceGroup.objects.create(case=case, name="证据分组1", sort_order=1)
        group.items.add(item1, item2)

        admin_obj = EvidenceGroupAdmin(EvidenceGroup, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 1
        assert results[0].item_count == 2

    def test_item_count_display_uses_annotation(self) -> None:
        """item_count display 方法应使用 annotate 的值"""
        case = _create_case("显示测试案件")
        elist = EvidenceList.objects.create(case=case, title="显示证据清单", list_type="previous", order=1)
        item = EvidenceItem.objects.create(evidence_list=elist, order=1, name="显示证据")
        group = EvidenceGroup.objects.create(case=case, name="显示分组", sort_order=1)
        group.items.add(item)

        admin_obj = EvidenceGroupAdmin(EvidenceGroup, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        obj = qs.first()
        assert admin_obj.item_count(obj) == 1


@pytest.mark.django_db
class TestEvidenceAdminRowLevelAccess:
    """安全审计（2026-10-19）回归：evidence 三个 Admin 的行级案件过滤 + 自定义视图 403。"""

    def _setup_two_cases(self) -> tuple[Case, Case]:
        contract = Contract.objects.create(name="行级证据合同", case_type="civil")
        mine = Case.objects.create(name="本人证据案件", contract=contract)
        other = Case.objects.create(name="他人证据案件", contract=contract)
        return mine, other

    def _make_staff_request(self, staff: Lawyer, method: str = "GET", path: str = "/admin/") -> Any:
        factory = RequestFactory()
        request = getattr(factory, method.lower())(path)
        request.user = staff
        return request

    def _make_assigned_staff(self, mine: Case) -> Lawyer:
        staff = Lawyer.objects.create_user(username="ev_row_staff", real_name="受限律师", is_staff=True)
        CaseAssignment.objects.create(case=mine, lawyer=staff)
        return staff

    def test_evidence_list_queryset_filters_by_case_access(self) -> None:
        """非管理员 staff 只能看到本所指派/授权案件下的证据清单"""
        mine, other = self._setup_two_cases()
        staff = self._make_assigned_staff(mine)
        EvidenceList.objects.create(case=mine, title="本人清单", list_type="previous", order=1)
        EvidenceList.objects.create(case=other, title="他人清单", list_type="previous", order=1)

        qs = EvidenceListAdmin(EvidenceListProxy, AdminSite()).get_queryset(self._make_staff_request(staff))
        assert set(qs.values_list("case_id", flat=True)) == {mine.pk}

    def test_evidence_item_queryset_filters_by_case_access(self) -> None:
        """非管理员 staff 只能看到可访问案件下的证据明细（evidence_list→case 关联）"""
        mine, other = self._setup_two_cases()
        staff = self._make_assigned_staff(mine)
        mine_list = EvidenceList.objects.create(case=mine, title="本人清单I", list_type="previous", order=1)
        other_list = EvidenceList.objects.create(case=other, title="他人清单I", list_type="previous", order=1)
        EvidenceItem.objects.create(evidence_list=mine_list, order=1, name="本人明细")
        EvidenceItem.objects.create(evidence_list=other_list, order=1, name="他人明细")

        qs = EvidenceItemAdmin(EvidenceItem, AdminSite()).get_queryset(self._make_staff_request(staff))
        assert set(qs.values_list("evidence_list__case_id", flat=True)) == {mine.pk}

    def test_evidence_group_queryset_filters_by_case_access(self) -> None:
        """非管理员 staff 只能看到可访问案件下的证据分组"""
        mine, other = self._setup_two_cases()
        staff = self._make_assigned_staff(mine)
        EvidenceGroup.objects.create(case=mine, name="本人分组", sort_order=1)
        EvidenceGroup.objects.create(case=other, name="他人分组", sort_order=1)

        qs = EvidenceGroupAdmin(EvidenceGroup, AdminSite()).get_queryset(self._make_staff_request(staff))
        assert set(qs.values_list("case_id", flat=True)) == {mine.pk}

    def test_export_list_view_denies_staff_without_case_access(self) -> None:
        """受限 staff 直接打他人案件的导出清单视图 → PermissionDenied（403）"""
        _mine, other = self._setup_two_cases()
        staff = self._make_assigned_staff(_mine)
        elist = EvidenceList.objects.create(case=other, title="他人清单E", list_type="previous", order=1)

        with pytest.raises(PermissionDenied):
            EvidenceListAdmin(EvidenceListProxy, AdminSite()).export_list_view(
                self._make_staff_request(staff), elist.pk
            )

    def test_download_pdf_view_denies_staff_without_case_access(self) -> None:
        """受限 staff 直接打他人案件的下载 PDF 视图 → PermissionDenied（403）"""
        _mine, other = self._setup_two_cases()
        staff = self._make_assigned_staff(_mine)
        elist = EvidenceList.objects.create(case=other, title="他人清单D", list_type="previous", order=1)

        with pytest.raises(PermissionDenied):
            EvidenceListAdmin(EvidenceListProxy, AdminSite()).download_pdf_view(
                self._make_staff_request(staff), elist.pk
            )

    def test_reorder_view_denies_staff_without_case_access(self) -> None:
        """受限 staff 直接打他人案件的重排视图 → PermissionDenied（403）"""
        _mine, other = self._setup_two_cases()
        staff = self._make_assigned_staff(_mine)
        elist = EvidenceList.objects.create(case=other, title="他人清单R", list_type="previous", order=1)

        with pytest.raises(PermissionDenied):
            EvidenceListAdmin(EvidenceListProxy, AdminSite()).reorder_view(
                self._make_staff_request(staff, method="POST", path="/admin/evidence/reorder/"), elist.pk
            )

    def test_next_list_type_and_hearing_mode_denies_staff_without_case_access(self) -> None:
        """受限 staff 直接打他人案件的 next-list-type / hearing-mode 视图 → PermissionDenied（403）"""
        _mine, other = self._setup_two_cases()
        staff = self._make_assigned_staff(_mine)
        admin_obj = EvidenceListAdmin(EvidenceListProxy, AdminSite())

        with pytest.raises(PermissionDenied):
            admin_obj.next_list_type_view(self._make_staff_request(staff), other.pk)
        with pytest.raises(PermissionDenied):
            admin_obj.hearing_mode_view(self._make_staff_request(staff), other.pk)

    def test_hearing_mode_allows_assigned_staff(self) -> None:
        """承办律师可访问本人案件的开庭模式（正控：过校验后正常渲染）"""
        mine, _other = self._setup_two_cases()
        staff = self._make_assigned_staff(mine)

        response = EvidenceListAdmin(EvidenceListProxy, AdminSite()).hearing_mode_view(
            self._make_staff_request(staff), mine.pk
        )
        assert response.context_data["case_id"] == mine.pk
