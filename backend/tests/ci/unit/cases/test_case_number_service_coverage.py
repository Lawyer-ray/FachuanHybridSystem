"""CaseNumberService 单元测试（覆盖 list/get/delete 与规范化入口）。

权限矩阵：
- perm_open_access=True 跳过访问策略；
- superuser 全量；
- 普通用户按指派案件过滤；
- 未认证用户被拒。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from apps.cases.models import CaseAssignment, CaseNumber
from apps.cases.services.number.case_number_service import CaseNumberService
from apps.core.exceptions import ForbiddenError, NotFoundError
from apps.testing.factories import CaseFactory, LawyerFactory


def _make_number(case, number: str = "（2026）京01民初1号") -> CaseNumber:
    return CaseNumber.objects.create(case=case, number=number)


class TestLazyProperties:
    def test_case_service_lazy_init(self) -> None:
        service = CaseNumberService()
        assert service.case_service is not None
        assert service.case_service is service.case_service

    def test_access_policy_lazy_init(self) -> None:
        service = CaseNumberService()
        assert service.access_policy is not None
        assert service.access_policy is service.access_policy


@pytest.mark.django_db
class TestListNumbers:
    def test_open_access_returns_all(self) -> None:
        case_a = CaseFactory()
        case_b = CaseFactory()
        _make_number(case_a)
        _make_number(case_b, "（2026）京01民初2号")

        result = CaseNumberService().list_numbers(perm_open_access=True)

        assert set(result.values_list("case_id", flat=True)) == {case_a.id, case_b.id}

    def test_case_id_filter_with_access(self) -> None:
        case = CaseFactory()
        other = CaseFactory()
        _make_number(case)
        _make_number(other, "（2026）京01民初9号")

        result = CaseNumberService().list_numbers(case_id=case.id, perm_open_access=True)

        assert list(result.values_list("case_id", flat=True)) == [case.id]

    def test_superuser_sees_all_without_case_id(self) -> None:
        case = CaseFactory()
        _make_number(case)
        admin = LawyerFactory(is_superuser=True, username=f"lawyer-{uuid4().hex[:8]}")

        result = CaseNumberService().list_numbers(user=admin)

        assert list(result.values_list("case_id", flat=True)) == [case.id]

    def test_normal_user_sees_only_assigned(self) -> None:
        assigned_case = CaseFactory()
        hidden_case = CaseFactory()
        lawyer = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")
        CaseAssignment.objects.create(case=assigned_case, lawyer=lawyer)
        _make_number(assigned_case)
        _make_number(hidden_case, "（2026）京01民初8号")

        result = CaseNumberService().list_numbers(user=lawyer)

        assert list(result.values_list("case_id", flat=True)) == [assigned_case.id]

    def test_normal_user_sees_nothing_without_assignment(self) -> None:
        case = CaseFactory()
        _make_number(case)
        stranger = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")

        result = CaseNumberService().list_numbers(user=stranger)

        assert list(result) == []

    def test_anonymous_user_rejected(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        with pytest.raises(ForbiddenError, match="用户未认证"):
            CaseNumberService().list_numbers(user=AnonymousUser())

    def test_case_id_access_denied_for_stranger(self) -> None:
        case = CaseFactory()
        stranger = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")

        with pytest.raises(ForbiddenError, match="无权限访问此案件"):
            CaseNumberService().list_numbers(case_id=case.id, user=stranger)


@pytest.mark.django_db
class TestGetNumber:
    def test_returns_number_with_open_access(self) -> None:
        case = CaseFactory()
        number = _make_number(case, "（2026）粤06民终100号")

        result = CaseNumberService().get_number(number.id, perm_open_access=True)

        assert result.id == number.id
        assert result.number == "（2026）粤06民终100号"
        assert result.case_id == case.id

    def test_not_found_raises(self) -> None:
        with pytest.raises(NotFoundError) as exc_info:
            CaseNumberService().get_number(99999, perm_open_access=True)
        assert exc_info.value.code == "CASE_NUMBER_NOT_FOUND"

    def test_access_denied_for_stranger(self) -> None:
        case = CaseFactory()
        number = _make_number(case)
        stranger = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")

        with pytest.raises(ForbiddenError, match="无权限访问此案件"):
            CaseNumberService().get_number(number.id, user=stranger)


@pytest.mark.django_db
class TestDeleteNumber:
    def test_deletes_successfully(self) -> None:
        case = CaseFactory()
        number = _make_number(case)

        result = CaseNumberService().delete_number(number.id, perm_open_access=True)

        assert result == {"success": True}
        assert not CaseNumber.objects.filter(id=number.id).exists()

    def test_not_found_raises(self) -> None:
        with pytest.raises(NotFoundError) as exc_info:
            CaseNumberService().delete_number(99999, perm_open_access=True)
        assert exc_info.value.code == "CASE_NUMBER_NOT_FOUND"

    def test_access_denied_for_stranger(self) -> None:
        case = CaseFactory()
        number = _make_number(case)
        stranger = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")

        with pytest.raises(ForbiddenError, match="无权限访问此案件"):
            CaseNumberService().delete_number(number.id, user=stranger)


class TestNormalizationHelpers:
    def test_format_case_number_normalizes(self) -> None:
        result = CaseNumberService().format_case_number("(2026)京01民初123号")
        assert "(" not in result and ")" not in result
        assert result.startswith("（2026）")
        assert result.endswith("号")

    def test_normalize_case_number_delegates_to_format(self) -> None:
        service = CaseNumberService()
        assert service.normalize_case_number("(2026)京01民初123号") == service.format_case_number("(2026)京01民初123号")

    def test_format_keeps_text_without_hao(self) -> None:
        assert CaseNumberService().format_case_number("abc 123") == "abc123"
