"""管理员律所收敛测试（cases 域，安全审计）。

is_admin 不再跨律所全放行：可见 = 本所指派覆盖的案件 + 无任何指派的无主案件；
未挂律所的平台级管理员保持全量可见（单律所部署行为不变）。
"""

from __future__ import annotations

import pytest

from apps.cases.models import Case, CaseAssignment
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.organization.models import LawFirm
from apps.testing.factories import CaseFactory, LawyerFactory


def _firm(name: str) -> LawFirm:
    return LawFirm.objects.create(name=name)


@pytest.mark.django_db
class TestAdminFirmScopingCases:
    def test_same_firm_admin_sees_firm_assigned_case(self):
        """同所指派覆盖的案件：本所 admin 可见。"""
        firm = _firm("同所")
        admin = LawyerFactory(is_admin=True, law_firm=firm)
        member = LawyerFactory(law_firm=firm)
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=member)

        policy = CaseAccessPolicy()
        assert policy.has_access(case.id, admin, None) is True
        assert case.id in set(policy.filter_queryset(Case.objects.all(), admin, None).values_list("id", flat=True))

    def test_cross_firm_admin_blocked_on_assigned_case(self):
        """A 所 admin 看不到仅有 B 所指派的案件。"""
        firm_a = _firm("甲所")
        firm_b = _firm("乙所")
        admin_a = LawyerFactory(is_admin=True, law_firm=firm_a)
        lawyer_b = LawyerFactory(law_firm=firm_b)
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=lawyer_b)

        policy = CaseAccessPolicy()
        assert policy.has_access(case.id, admin_a, None) is False
        assert case.id not in set(
            policy.filter_queryset(Case.objects.all(), admin_a, None).values_list("id", flat=True)
        )

    def test_admin_sees_case_without_any_assignment(self):
        """无任何指派的无主案件：admin 兜底可见。"""
        admin = LawyerFactory(is_admin=True, law_firm=_firm("丙所"))
        case = CaseFactory()

        policy = CaseAccessPolicy()
        assert policy.has_access(case.id, admin, None) is True
        assert case.id in set(policy.filter_queryset(Case.objects.all(), admin, None).values_list("id", flat=True))

    def test_firmless_admin_keeps_full_visibility(self):
        """未挂律所的平台级管理员保持全量可见（向后兼容）。"""
        admin = LawyerFactory(is_admin=True)
        lawyer_b = LawyerFactory(law_firm=_firm("丁所"))
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=lawyer_b)

        policy = CaseAccessPolicy()
        assert policy.has_access(case.id, admin, None) is True
        assert case.id in set(policy.filter_queryset(Case.objects.all(), admin, None).values_list("id", flat=True))

    def test_mixed_assignments_visible_when_firm_included(self):
        """案件同时被甲乙两所指派：甲所 admin 可见（存在本所指派即可）。"""
        firm_a = _firm("甲所2")
        admin_a = LawyerFactory(is_admin=True, law_firm=firm_a)
        lawyer_a = LawyerFactory(law_firm=firm_a)
        lawyer_b = LawyerFactory(law_firm=_firm("乙所2"))
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=lawyer_a)
        CaseAssignment.objects.create(case=case, lawyer=lawyer_b)

        assert CaseAccessPolicy().has_access(case.id, admin_a, None) is True

    def test_single_firm_deployment_behavior_unchanged(self):
        """单律所部署：全部案件（有无指派）对 admin 均可见。"""
        firm = _firm("唯一所")
        admin = LawyerFactory(is_admin=True, law_firm=firm)
        member = LawyerFactory(law_firm=firm)
        assigned = CaseFactory()
        CaseAssignment.objects.create(case=assigned, lawyer=member)
        unassigned = CaseFactory()

        visible = set(CaseAccessPolicy().filter_queryset(Case.objects.all(), admin, None).values_list("id", flat=True))
        assert {assigned.id, unassigned.id} <= visible
