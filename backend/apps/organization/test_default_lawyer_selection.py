"""Regression tests for default lawyer selection behavior."""

from __future__ import annotations

from uuid import uuid4

import pytest

from apps.organization.models import LawFirm, Lawyer
from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter


def _create_lawyer(*, law_firm: LawFirm, is_admin: bool = False) -> Lawyer:
    return Lawyer.objects.create_user(
        username=f"lawyer-{uuid4().hex[:12]}",
        password="testpass123",
        law_firm=law_firm,
        is_admin=is_admin,
    )


@pytest.mark.django_db
def test_get_default_lawyer_prefers_admin() -> None:
    law_firm = LawFirm.objects.create(name="law-firm-admin-priority")
    regular = _create_lawyer(law_firm=law_firm, is_admin=False)
    admin = _create_lawyer(law_firm=law_firm, is_admin=True)
    service = OrganizationServiceAdapter()

    default_id = service.get_default_lawyer_id_internal()

    assert default_id == admin.id
    assert default_id != regular.id


@pytest.mark.django_db
def test_get_default_lawyer_falls_back_to_first_lawyer_when_no_admin() -> None:
    law_firm = LawFirm.objects.create(name="law-firm-fallback")
    first = _create_lawyer(law_firm=law_firm, is_admin=False)
    _create_lawyer(law_firm=law_firm, is_admin=False)
    service = OrganizationServiceAdapter()

    default_id = service.get_default_lawyer_id_internal()

    assert default_id == first.id


@pytest.mark.django_db
def test_get_default_lawyer_returns_none_when_no_lawyers() -> None:
    service = OrganizationServiceAdapter()

    default_id = service.get_default_lawyer_id_internal()

    assert default_id is None
