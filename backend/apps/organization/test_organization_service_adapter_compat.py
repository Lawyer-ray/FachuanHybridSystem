from __future__ import annotations

import pytest

from apps.organization.models import AccountCredential, LawFirm, Lawyer
from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter


@pytest.mark.django_db
def test_organization_service_adapter_public_and_internal_credential_methods_are_compatible() -> None:
    law_firm = LawFirm.objects.create(name="兼容测试律所")
    lawyer = Lawyer.objects.create_user(
        username="compat-lawyer",
        password="secret",  # pragma: allowlist secret
        real_name="兼容律师",
        law_firm=law_firm,
    )
    cred_a = AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="wkxx",
        url="https://wkxx.example.com",
        account="wk-account",
        password="wk-secret",  # pragma: allowlist secret
    )
    AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="court_zxfw",
        url="https://court.example.com",
        account="court-account",
        password="court-secret",  # pragma: allowlist secret
    )

    adapter = OrganizationServiceAdapter()

    assert {c.id for c in adapter.get_all_credentials()} == {c.id for c in adapter.get_all_credentials_internal()}

    assert adapter.get_credential(cred_a.id).id == adapter.get_credential_internal(cred_a.id).id
    assert {c.id for c in adapter.get_credentials_by_site("wkxx")} == {
        c.id for c in adapter.get_credentials_by_site_internal("wkxx")
    }
    assert (
        adapter.get_credential_by_account("wk-account", "wkxx").id
        == adapter.get_credential_by_account_internal("wk-account", "wkxx").id
    )

    adapter.update_login_success(cred_a.id)
    adapter.update_login_failure_internal(cred_a.id)
    cred_a.refresh_from_db()
    assert cred_a.login_success_count == 1
    assert cred_a.login_failure_count == 1


@pytest.mark.django_db
def test_organization_service_adapter_public_and_internal_lawyer_methods_are_compatible() -> None:
    law_firm = LawFirm.objects.create(name="律师兼容测试律所")
    admin = Lawyer.objects.create_user(
        username="admin-compat",
        password="secret",  # pragma: allowlist secret
        real_name="管理员",
        law_firm=law_firm,
        is_admin=True,
    )
    normal = Lawyer.objects.create_user(
        username="normal-compat",
        password="secret",  # pragma: allowlist secret
        real_name="普通律师",
        law_firm=law_firm,
        is_admin=False,
    )

    adapter = OrganizationServiceAdapter()

    admin_public = adapter.get_lawyer_by_id(admin.id)
    admin_internal = adapter.get_lawyer_by_id_internal(admin.id)
    assert admin_public is not None
    assert admin_internal is not None
    assert admin_public.id == admin_internal.id == admin.id

    normal_public = adapter.get_lawyer_by_id(normal.id)
    normal_internal = adapter.get_lawyer_by_id_internal(normal.id)
    assert normal_public is not None
    assert normal_internal is not None
    assert normal_public.id == normal_internal.id == normal.id

    assert adapter.get_default_lawyer_id() == adapter.get_default_lawyer_id_internal() == admin.id
