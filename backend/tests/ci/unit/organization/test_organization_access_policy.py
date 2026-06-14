"""organization/services/access/organization_access_policy.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import ForbiddenError
from apps.organization.services.access.organization_access_policy import OrganizationAccessPolicy


@pytest.fixture
def policy() -> OrganizationAccessPolicy:
    return OrganizationAccessPolicy()


def _user(**kwargs: object) -> SimpleNamespace:
    defaults = {
        "is_authenticated": True,
        "is_superuser": False,
        "is_admin": False,
        "law_firm_id": 1,
        "id": 1,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _lawfirm(**kwargs: object) -> SimpleNamespace:
    defaults = {"id": 1}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _lawyer(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "is_authenticated": True,
        "is_superuser": False,
        "is_admin": False,
        "law_firm_id": 1,
        "id": 1,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── ensure_authenticated ──────────────────────────────────────────────


class TestEnsureAuthenticated:
    def test_none_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_authenticated(None)

    def test_unauthenticated_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_authenticated(SimpleNamespace(is_authenticated=False))

    def test_authenticated_passes(self, policy: OrganizationAccessPolicy) -> None:
        policy.ensure_authenticated(_user())


# ── can_create ─────────────────────────────────────────────────────────


class TestCanCreate:
    def test_none(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_create(None) is False

    def test_unauthenticated(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_create(_user(is_authenticated=False)) is False

    def test_superuser(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_create(_user(is_superuser=True)) is True

    def test_admin(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_create(_user(is_admin=True)) is True

    def test_regular_user(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_create(_user()) is False

    def test_ensure_can_create_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_can_create(_user())


# ── lawyer: can_read_lawyer ────────────────────────────────────────────


class TestCanReadLawyer:
    def test_none_user(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_lawyer(None, _lawyer()) is False

    def test_unauthenticated(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_lawyer(_user(is_authenticated=False), _lawyer()) is False

    def test_superuser(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_lawyer(_user(is_superuser=True), _lawyer()) is True

    def test_same_firm(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_lawyer(_user(law_firm_id=1), _lawyer(law_firm_id=1)) is True

    def test_different_firm(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_lawyer(_user(law_firm_id=1), _lawyer(law_firm_id=2)) is False

    def test_ensure_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_can_read_lawyer(_user(law_firm_id=1), _lawyer(law_firm_id=2))


# ── lawyer: can_update_lawyer ──────────────────────────────────────────


class TestCanUpdateLawyer:
    def test_none_user(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_update_lawyer(None, _lawyer()) is False

    def test_superuser(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_update_lawyer(_user(is_superuser=True), _lawyer()) is True

    def test_self_update(self, policy: OrganizationAccessPolicy) -> None:
        u = _user(id=5)
        assert policy.can_update_lawyer(u, _lawyer(id=5)) is True

    def test_admin_same_firm(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_update_lawyer(_user(is_admin=True, law_firm_id=1), _lawyer(id=99, law_firm_id=1)) is True

    def test_admin_diff_firm(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_update_lawyer(_user(is_admin=True, law_firm_id=1), _lawyer(id=99, law_firm_id=2)) is False

    def test_regular_user(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_update_lawyer(_user(id=1), _lawyer(id=99)) is False

    def test_ensure_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_can_update_lawyer(_user(id=1), _lawyer(id=99))


# ── lawyer: can_delete_lawyer ──────────────────────────────────────────


class TestCanDeleteLawyer:
    def test_none_user(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_delete_lawyer(None, _lawyer()) is False

    def test_superuser(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_delete_lawyer(_user(is_superuser=True), _lawyer()) is True

    def test_admin_same_firm(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_delete_lawyer(_user(is_admin=True, law_firm_id=1), _lawyer(law_firm_id=1)) is True

    def test_admin_diff_firm(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_delete_lawyer(_user(is_admin=True, law_firm_id=1), _lawyer(law_firm_id=2)) is False

    def test_ensure_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_can_delete_lawyer(_user(), _lawyer())


# ── lawfirm: can_read_lawfirm ──────────────────────────────────────────


class TestCanReadLawfirm:
    def test_none_user(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_lawfirm(None, _lawfirm()) is False

    def test_superuser(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_lawfirm(_user(is_superuser=True), _lawfirm()) is True

    def test_same_firm(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_lawfirm(_user(law_firm_id=1), _lawfirm(id=1)) is True

    def test_diff_firm(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_lawfirm(_user(law_firm_id=1), _lawfirm(id=2)) is False

    def test_ensure_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_can_read_lawfirm(_user(law_firm_id=1), _lawfirm(id=2))


# ── lawfirm: can_update_lawfirm ────────────────────────────────────────


class TestCanUpdateLawfirm:
    def test_superuser(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_update_lawfirm(_user(is_superuser=True), _lawfirm()) is True

    def test_admin_same_firm(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_update_lawfirm(_user(is_admin=True, law_firm_id=1), _lawfirm(id=1)) is True

    def test_regular_user(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_update_lawfirm(_user(), _lawfirm(id=1)) is False

    def test_ensure_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_can_update_lawfirm(_user(), _lawfirm())


# ── lawfirm: can_delete_lawfirm ────────────────────────────────────────


class TestCanDeleteLawfirm:
    def test_superuser(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_delete_lawfirm(_user(is_superuser=True), _lawfirm()) is True

    def test_admin(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_delete_lawfirm(_user(is_admin=True), _lawfirm()) is False

    def test_ensure_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_can_delete_lawfirm(_user(), _lawfirm())


# ── team: can_read_team / can_update_team / can_delete_team ────────────


class TestTeamAccess:
    def test_read_team_superuser(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_team(_user(is_superuser=True), SimpleNamespace(law_firm_id=1)) is True

    def test_read_team_same_firm(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_team(_user(law_firm_id=1), SimpleNamespace(law_firm_id=1)) is True

    def test_read_team_diff_firm(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_read_team(_user(law_firm_id=1), SimpleNamespace(law_firm_id=2)) is False

    def test_update_team_admin(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_update_team(_user(is_admin=True, law_firm_id=1), SimpleNamespace(law_firm_id=1)) is True

    def test_update_team_regular(self, policy: OrganizationAccessPolicy) -> None:
        assert policy.can_update_team(_user(), SimpleNamespace(law_firm_id=1)) is False

    def test_delete_team_delegates(self, policy: OrganizationAccessPolicy) -> None:
        team = SimpleNamespace(law_firm_id=1)
        assert policy.can_delete_team(_user(is_admin=True, law_firm_id=1), team) is True

    def test_ensure_read_team_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_can_read_team(_user(law_firm_id=1), SimpleNamespace(law_firm_id=2))

    def test_ensure_update_team_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_can_update_team(_user(), SimpleNamespace(law_firm_id=1))

    def test_ensure_delete_team_raises(self, policy: OrganizationAccessPolicy) -> None:
        with pytest.raises(ForbiddenError):
            policy.ensure_can_delete_team(_user(), SimpleNamespace(law_firm_id=1))
