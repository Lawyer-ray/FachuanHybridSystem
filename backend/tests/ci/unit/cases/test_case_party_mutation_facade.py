"""CasePartyMutationFacade 单元测试。

覆盖延迟属性、认证门槛、案件访问校验与委托调用，
以及 update_party 换绑案件时的双重访问校验。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from apps.cases.services.party.case_party_mutation_facade import CasePartyMutationFacade
from apps.core.exceptions import ForbiddenError
from apps.testing.factories import LawyerFactory


class _FakeAccessPolicy:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def ensure_access(self, *, case_id: int, user: object, org_access: dict, perm_open_access: bool) -> None:
        self.calls.append(
            {"case_id": case_id, "user": user, "org_access": org_access, "perm_open_access": perm_open_access}
        )


def _make_facade(*, with_mutation: bool = True) -> tuple[CasePartyMutationFacade, MagicMock, _FakeAccessPolicy]:
    mutation = MagicMock()
    access = _FakeAccessPolicy()
    facade = CasePartyMutationFacade(
        mutation_service=mutation if with_mutation else None,
        access_policy=access,  # type: ignore[arg-type]
    )
    return facade, mutation, access


def _user(authenticated: bool = True) -> MagicMock:
    user = MagicMock()
    user.is_authenticated = authenticated
    return user


class TestLazyProperties:
    def test_mutation_service_required(self) -> None:
        facade, _, _ = _make_facade(with_mutation=False)
        with pytest.raises(RuntimeError, match="requires mutation_service"):
            _ = facade.mutation_service

    def test_query_service_lazy_created_once(self) -> None:
        facade, _, _ = _make_facade()
        first = facade.query_service
        assert first is not None
        assert facade.query_service is first

    def test_access_policy_lazy_created_once(self) -> None:
        facade = CasePartyMutationFacade(mutation_service=MagicMock())
        first = facade.access_policy
        assert first is not None
        assert facade.access_policy is first


class TestCreateParty:
    def test_delegates_after_access_check(self) -> None:
        facade, mutation, access = _make_facade()
        user = _user()
        expected = MagicMock()
        mutation.create_party.return_value = expected

        result = facade.create_party(case_id=5, client_id=7, legal_status="plaintiff", user=user, org_access={"k": 1})

        assert result is expected
        assert access.calls == [{"case_id": 5, "user": user, "org_access": {"k": 1}, "perm_open_access": False}]
        mutation.create_party.assert_called_once_with(case_id=5, client_id=7, legal_status="plaintiff", user=user)

    def test_unauthenticated_user_rejected(self) -> None:
        facade, mutation, _ = _make_facade()
        with pytest.raises(ForbiddenError, match="用户未认证"):
            facade.create_party(case_id=5, client_id=7, user=_user(authenticated=False))
        mutation.create_party.assert_not_called()

    def test_perm_open_access_skips_auth(self) -> None:
        facade, mutation, access = _make_facade()
        facade.create_party(case_id=5, client_id=7, user=None, perm_open_access=True)
        assert access.calls == [{"case_id": 5, "user": None, "org_access": None, "perm_open_access": True}]
        mutation.create_party.assert_called_once()


class TestUpdateParty:
    @staticmethod
    def _make_facade_with_party(case_id: int) -> tuple[CasePartyMutationFacade, MagicMock, _FakeAccessPolicy]:
        facade, mutation, access = _make_facade()
        party = SimpleNamespace(id=3, case_id=case_id)
        facade._query_service = SimpleNamespace(get_party=lambda party_id: party)
        return facade, mutation, access

    def test_same_case_single_access_check(self) -> None:
        facade, mutation, access = self._make_facade_with_party(case_id=8)
        user = _user()
        data = {"legal_status": "defendant"}
        expected = MagicMock()
        mutation.update_party.return_value = expected

        result = facade.update_party(party_id=3, data=data, user=user)

        assert result is expected
        assert len(access.calls) == 1
        assert access.calls[0]["case_id"] == 8
        mutation.update_party.assert_called_once_with(party_id=3, data=data, user=user)

    def test_case_change_triggers_second_access_check(self) -> None:
        facade, mutation, access = self._make_facade_with_party(case_id=8)
        user = _user()

        facade.update_party(party_id=3, data={"case_id": 9}, user=user)

        assert [c["case_id"] for c in access.calls] == [8, 9]

    def test_same_case_id_in_data_no_second_check(self) -> None:
        facade, mutation, access = self._make_facade_with_party(case_id=8)
        facade.update_party(party_id=3, data={"case_id": 8}, user=_user())
        assert len(access.calls) == 1

    def test_unauthenticated_user_rejected(self) -> None:
        facade, mutation, _ = _make_facade()
        with pytest.raises(ForbiddenError, match="用户未认证"):
            facade.update_party(party_id=3, data={}, user=_user(authenticated=False))
        mutation.update_party.assert_not_called()

    def test_perm_open_access_skips_auth(self) -> None:
        facade, mutation, access = self._make_facade_with_party(case_id=8)
        facade.update_party(party_id=3, data={}, user=None, perm_open_access=True)
        assert access.calls[0]["perm_open_access"] is True


class TestDeleteParty:
    def test_delegates_after_access_check(self) -> None:
        facade, mutation, access = _make_facade()
        facade._query_service = SimpleNamespace(get_party=lambda party_id: SimpleNamespace(id=4, case_id=6))
        user = _user()
        mutation.delete_party.return_value = {"success": True}

        result = facade.delete_party(party_id=4, user=user)

        assert result == {"success": True}
        assert access.calls[0]["case_id"] == 6
        mutation.delete_party.assert_called_once_with(party_id=4, user=user)

    def test_unauthenticated_user_rejected(self) -> None:
        facade, mutation, _ = _make_facade()
        with pytest.raises(ForbiddenError, match="用户未认证"):
            facade.delete_party(party_id=4, user=_user(authenticated=False))
        mutation.delete_party.assert_not_called()


class TestCreatePartyInternal:
    def test_delegates_without_user(self) -> None:
        facade, mutation, _ = _make_facade()
        mutation.create_party_internal.return_value = True
        assert facade.create_party_internal(case_id=1, client_id=2, legal_status="plaintiff") is True
        mutation.create_party_internal.assert_called_once_with(case_id=1, client_id=2, legal_status="plaintiff")


@pytest.mark.django_db
class TestDefaultQueryService:
    def test_default_query_service_is_real_service(self) -> None:
        from apps.cases.services.party.case_party_query_service import CasePartyQueryService

        facade = CasePartyMutationFacade(mutation_service=MagicMock())
        assert isinstance(facade.query_service, CasePartyQueryService)


@pytest.mark.django_db
class TestAccessDeniedByRealPolicy:
    def test_create_party_blocked_for_stranger(self) -> None:
        """真实访问策略下，未指派案件的用户创建当事人被拒。"""
        from apps.testing.factories import CaseFactory

        case = CaseFactory()
        stranger = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")
        facade = CasePartyMutationFacade(mutation_service=MagicMock())

        with pytest.raises(ForbiddenError, match="无权限访问此案件"):
            facade.create_party(case_id=case.id, client_id=1, user=stranger)


class TestEnsureAuthenticatedWithAnonymous:
    def test_anonymous_user_rejected(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        facade, mutation, _ = _make_facade()
        with pytest.raises(ForbiddenError):
            facade.create_party(case_id=1, client_id=1, user=AnonymousUser())
        mutation.create_party.assert_not_called()
