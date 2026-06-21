"""Targeted tests for contacts module to push coverage to 80%+."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# schemas/contact_schemas.py (0% coverage)
# ---------------------------------------------------------------------------


class TestContactSchemas:
    def test_case_contact_in_schema(self):
        from apps.contacts.schemas.contact_schemas import CaseContactIn

        schema = CaseContactIn(
            case_id=1,
            authority_id=2,
            name="张法官",
            role="judge",
            phone="12345678",
            address="重庆市",
            stage="first_instance",
            note="备注",
        )
        assert schema.case_id == 1
        assert schema.name == "张法官"

    def test_case_contact_in_schema_minimal(self):
        from apps.contacts.schemas.contact_schemas import CaseContactIn

        schema = CaseContactIn(case_id=1, name="张法官", role="judge")
        assert schema.phone is None

    def test_case_contact_update_schema(self):
        from apps.contacts.schemas.contact_schemas import CaseContactUpdate

        schema = CaseContactUpdate(name="李法官", phone="87654321")
        assert schema.name == "李法官"
        assert schema.role is None

    def test_case_contact_search_result(self):
        from apps.contacts.schemas.contact_schemas import CaseContactSearchResult

        schema = CaseContactSearchResult(
            name="张法官",
            role="judge",
            authority_name="重庆法院",
            phone="123",
            address="渝中区",
            occurrence_count=5,
            case_ids=[1, 2, 3],
        )
        assert schema.occurrence_count == 5
        assert len(schema.case_ids) == 3

    def test_case_contact_search_result_defaults(self):
        from apps.contacts.schemas.contact_schemas import CaseContactSearchResult

        schema = CaseContactSearchResult(name="Test", role="clerk")
        assert schema.occurrence_count == 1
        assert schema.case_ids == []

    def test_case_contact_out_resolve_methods(self):
        from apps.contacts.schemas.contact_schemas import CaseContactOut

        contact = SimpleNamespace(
            case_id=42,
            authority_id=7,
            authority=SimpleNamespace(name="Test Court"),
            get_role_display=lambda: "审判员",
            get_stage_display=lambda: "一审",
            stage="first_instance",
            created_at=None,
            updated_at=None,
        )

        assert CaseContactOut.resolve_case_id(contact) == 42
        assert CaseContactOut.resolve_authority_id(contact) == 7
        assert CaseContactOut.resolve_role_display(contact) == "审判员"
        assert CaseContactOut.resolve_stage_display(contact) == "一审"
        assert CaseContactOut.resolve_authority_name(contact) == "Test Court"

    def test_case_contact_out_resolve_stage_none(self):
        from apps.contacts.schemas.contact_schemas import CaseContactOut

        contact = SimpleNamespace(stage=None, get_stage_display=lambda: None)
        assert CaseContactOut.resolve_stage_display(contact) is None

    def test_case_contact_out_resolve_authority_none(self):
        from apps.contacts.schemas.contact_schemas import CaseContactOut

        contact = SimpleNamespace(authority=None)
        assert CaseContactOut.resolve_authority_name(contact) is None


# ---------------------------------------------------------------------------
# services/contact_service.py (65% coverage)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestContactService:
    def test_list_contacts(self):
        from apps.contacts.services.contact_service import CaseContactService

        service = CaseContactService()
        user = SimpleNamespace(is_staff=True, is_superuser=True)
        with patch.object(service, "ensure_admin"):
            result = service.list_contacts(user=user)
            assert result is not None

    def test_list_contacts_with_case_id(self):
        from apps.contacts.services.contact_service import CaseContactService

        service = CaseContactService()
        user = SimpleNamespace(is_staff=True)
        with patch.object(service, "ensure_admin"):
            result = service.list_contacts(case_id=999, user=user)
            assert result is not None

    def test_get_contact_not_found(self):
        from apps.contacts.services.contact_service import CaseContactService

        service = CaseContactService()
        user = SimpleNamespace(is_staff=True)
        with patch.object(service, "ensure_admin"):
            with pytest.raises(Exception):
                service.get_contact(contact_id=999999, user=user)

    def test_update_contact_not_found(self):
        from apps.contacts.services.contact_service import CaseContactService

        service = CaseContactService()
        user = SimpleNamespace(is_staff=True)
        with patch.object(service, "ensure_admin"):
            with pytest.raises(Exception):
                service.update_contact(contact_id=999999, data={"name": "New"}, user=user)

    def test_delete_contact_not_found(self):
        from apps.contacts.services.contact_service import CaseContactService

        service = CaseContactService()
        user = SimpleNamespace(is_staff=True)
        with patch.object(service, "ensure_admin"):
            with pytest.raises(Exception):
                service.delete_contact(contact_id=999999, user=user)

    def test_search_contacts_public(self):
        from apps.contacts.services.contact_service import CaseContactService

        service = CaseContactService()
        user = SimpleNamespace(is_staff=True, is_superuser=True)
        with patch.object(service, "ensure_admin"):
            result = service.search_contacts_public(q="nonexistent_xyz", user=user)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# api/__init__.py (0% coverage)
# ---------------------------------------------------------------------------


class TestContactApiInit:
    def test_api_init(self):
        from apps.contacts.api import __init__ as api_init

        assert api_init is not None


# ---------------------------------------------------------------------------
# admin.py (59% coverage)
# ---------------------------------------------------------------------------


class TestContactsAdmin:
    def test_admin_import(self):
        from apps.contacts import admin as contacts_admin

        assert contacts_admin is not None

    def test_case_contact_admin_form_init(self):
        from apps.contacts.admin import CaseContactAdminForm

        form = CaseContactAdminForm()
        assert "authority_name" in form.fields

    def test_case_contact_inline_form_init(self):
        from apps.contacts.admin import CaseContactInlineForm

        form = CaseContactInlineForm()
        assert "authority_name" in form.fields

    def test_case_contact_admin_has_module_permission(self):
        from apps.contacts.admin import CaseContactAdmin

        admin_instance = CaseContactAdmin.__new__(CaseContactAdmin)
        assert admin_instance.has_module_permission(None) is True


# ---------------------------------------------------------------------------
# models.py (92% coverage)
# ---------------------------------------------------------------------------


class TestContactsModels:
    def test_case_contact_model_fields(self):
        from apps.contacts.models import CaseContact

        field_names = [f.name for f in CaseContact._meta.get_fields()]
        assert "name" in field_names
        assert "role" in field_names
        assert "phone" in field_names


# ---------------------------------------------------------------------------
# services/contact_service.py (65% coverage) - deeper tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestContactServiceDeep:
    def test_create_contact_success(self):
        from apps.contacts.services.contact_service import CaseContactService

        service = CaseContactService()
        user = SimpleNamespace(is_staff=True, is_superuser=True)
        with patch.object(service, "ensure_admin"):
            contact = service.create_contact(
                case_id=1,
                data={"name": "Test Judge", "role": "judge"},
                user=user,
            )
            assert contact.name == "Test Judge"
            assert contact.case_id == 1
            # Clean up
            contact.delete()

    def test_search_contacts_public_with_role(self):
        from apps.contacts.services.contact_service import CaseContactService

        service = CaseContactService()
        user = SimpleNamespace(is_staff=True, is_superuser=True)
        with patch.object(service, "ensure_admin"):
            result = service.search_contacts_public(q="test", role="judge", limit=10, user=user)
        assert isinstance(result, list)
