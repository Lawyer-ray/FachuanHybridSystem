from __future__ import annotations

from types import SimpleNamespace

from apps.cases.services.case.case_access_policy import CaseAccessPolicy


def test_has_access_allows_staff_user_without_assignment() -> None:
    policy = CaseAccessPolicy()
    user = SimpleNamespace(
        is_authenticated=True,
        is_admin=False,
        is_superuser=False,
        is_staff=True,
    )

    assert policy.has_access(case_id=1, user=user, org_access=None, perm_open_access=False) is True


def test_has_access_allows_superuser_without_assignment() -> None:
    policy = CaseAccessPolicy()
    user = SimpleNamespace(
        is_authenticated=True,
        is_admin=False,
        is_superuser=True,
        is_staff=False,
    )

    assert policy.has_access(case_id=1, user=user, org_access=None, perm_open_access=False) is True
