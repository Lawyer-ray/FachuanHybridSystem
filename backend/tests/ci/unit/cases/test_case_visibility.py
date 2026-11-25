"""案件可见性：指派 / 授权 / 无主 / 管理员，四条来源各自成立。

## 为什么这层要单独测

它是回传件核对 6 个端点的**唯一**权限来源。错一个方向后果不同：

- 收得太紧 → 承办律师打不开自己的案子（功能废掉，且报错会误导成「案件不存在」）；
- 放得太松 → 知道 case_id 就能读别人案子的待裁决清单（真实越权）。

两种错都不会被「功能正常」的用例发现，只能靠这里逐条钉住。
"""

from __future__ import annotations

import pytest

from apps.cases.models import CaseAccessGrant, CaseAssignment
from apps.cases.services.case.case_visibility import accessible_case_ids, can_access_case
from apps.testing.factories import CaseFactory, LawyerFactory


@pytest.mark.django_db
class TestCanAccessCase:
    def test_assigned_lawyer_can_access(self) -> None:
        case = CaseFactory()
        lawyer = LawyerFactory()
        CaseAssignment.objects.create(case=case, lawyer=lawyer)

        assert can_access_case(lawyer, case.pk) is True

    def test_granted_lawyer_can_access(self) -> None:
        case = CaseFactory()
        owner = LawyerFactory()
        CaseAssignment.objects.create(case=case, lawyer=owner)
        granted = LawyerFactory()
        CaseAccessGrant.objects.create(case=case, grantee=granted)

        assert can_access_case(granted, case.pk) is True

    def test_unrelated_lawyer_is_blocked_on_an_assigned_case(self) -> None:
        """有承办律师的案子 = 有人「本来就该看得见」，这时白名单才生效。"""
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=LawyerFactory())
        outsider = LawyerFactory()

        assert can_access_case(outsider, case.pk) is False

    def test_unowned_case_is_open_to_everyone(self) -> None:
        """没指派也没授权 = 没有任何「该看得见的人」；锁死会让刚建好的案子归档 403。"""
        case = CaseFactory()
        outsider = LawyerFactory()

        assert can_access_case(outsider, case.pk) is True

    def test_staff_and_superuser_are_unrestricted(self) -> None:
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=LawyerFactory())
        admin = LawyerFactory(is_staff=True)
        superuser = LawyerFactory(is_superuser=True)

        assert can_access_case(admin, case.pk) is True
        assert can_access_case(superuser, case.pk) is True
        assert accessible_case_ids(admin) is None
        assert accessible_case_ids(superuser) is None

    def test_anonymous_has_nothing(self) -> None:
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=LawyerFactory())

        assert can_access_case(None, case.pk) is False
        assert accessible_case_ids(None) == set()


@pytest.mark.django_db
class TestAccessibleCaseIds:
    def test_union_of_assignments_and_grants(self) -> None:
        lawyer = LawyerFactory()
        assigned = CaseFactory()
        granted = CaseFactory()
        other = CaseFactory()
        CaseAssignment.objects.create(case=assigned, lawyer=lawyer)
        CaseAccessGrant.objects.create(case=granted, grantee=lawyer)
        CaseAssignment.objects.create(case=other, lawyer=LawyerFactory())

        assert accessible_case_ids(lawyer) == {assigned.pk, granted.pk}
