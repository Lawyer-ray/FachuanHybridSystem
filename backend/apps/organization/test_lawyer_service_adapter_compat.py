from __future__ import annotations

import pytest

from apps.organization.models import LawFirm, Lawyer
from apps.organization.services.lawyer.adapter import LawyerServiceAdapter


@pytest.mark.django_db
def test_lawyer_service_adapter_public_and_internal_admin_lookup_are_compatible() -> None:
    law_firm = LawFirm.objects.create(name="测试律所")
    Lawyer.objects.create_user(
        username="normal-user",
        password="secret",
        real_name="普通律师",
        law_firm=law_firm,
        is_admin=False,
    )
    admin_user = Lawyer.objects.create_user(
        username="admin-user",
        password="secret",
        real_name="管理员律师",
        law_firm=law_firm,
        is_admin=True,
    )

    adapter = LawyerServiceAdapter()

    admin_dto = adapter.get_admin_lawyer()
    admin_dto_internal = adapter.get_admin_lawyer_internal()

    assert admin_dto is not None
    assert admin_dto_internal is not None
    assert admin_dto.id == admin_user.id
    assert admin_dto_internal.id == admin_user.id


@pytest.mark.django_db
def test_lawyer_service_adapter_public_and_internal_name_listing_are_compatible() -> None:
    law_firm = LawFirm.objects.create(name="测试律所")
    Lawyer.objects.create_user(
        username="user-a",
        password="secret",
        real_name="张三",
        law_firm=law_firm,
    )
    Lawyer.objects.create_user(
        username="user-b",
        password="secret",
        real_name="李四",
        law_firm=law_firm,
    )

    adapter = LawyerServiceAdapter()

    assert set(adapter.get_all_lawyer_names()) == {"张三", "李四"}
    assert set(adapter.get_all_lawyer_names_internal()) == {"张三", "李四"}


@pytest.mark.django_db
def test_lawyer_service_adapter_public_and_internal_model_lookup_are_compatible() -> None:
    law_firm = LawFirm.objects.create(name="测试律所")
    lawyer = Lawyer.objects.create_user(
        username="lookup-user",
        password="secret",
        real_name="待查询律师",
        law_firm=law_firm,
    )

    adapter = LawyerServiceAdapter()

    model_from_public = adapter.get_lawyer_model(lawyer.id)
    model_from_internal = adapter.get_lawyer_internal(lawyer.id)

    assert model_from_public is not None
    assert model_from_internal is not None
    assert model_from_public.id == lawyer.id
    assert model_from_internal.id == lawyer.id
