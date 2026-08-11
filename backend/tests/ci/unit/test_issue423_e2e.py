"""Integration tests for issue 423 fixes.

End-to-end verification that verifies all 5 fixes actually work
through the Django stack (not just unit tests).
"""

import pytest
from django.test import TestCase


@pytest.mark.django_db
class TestIssue423Fixes(TestCase):
    """End-to-end tests for all issue 423 bugs."""

    # ── Fix 1: caseparty_api ServiceLocator injection ──

    def test_caseparty_service_factory_injects_dependencies(self) -> None:
        """CasePartyService factory injects client_service + contract_service,
        preventing '未注入' RuntimeError."""
        from apps.cases.services.party.case_party_service import CasePartyService
        from apps.core.interfaces import ServiceLocator

        # Replicate _get_case_party_service() code path
        svc = CasePartyService(
            client_service=ServiceLocator.get_client_service(),
            contract_service=ServiceLocator.get_contract_service(),
        )

        # Must not raise '未注入' error
        facade = svc.mutation_facade  # lazy property triggers _client_service check
        assert facade is not None
        assert svc._client_service is not None
        assert svc._contract_service is not None

    def test_caseparty_service_without_deps_raises_runtime_error(self) -> None:
        """Bare CasePartyService() still errors (expected for test coverage)."""
        from apps.cases.services.party.case_party_service import CasePartyService

        svc = CasePartyService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.mutation_facade

    # ── Fix 2: createsuperuser sets is_admin ──

    def test_lawyer_create_superuser_sets_is_admin(self) -> None:
        """LawyerManager.create_superuser sets is_admin=True."""
        from apps.organization.models import Lawyer

        user = Lawyer.objects.create_superuser(
            username="test_superadmin_423",
            email=None,
            password="testpass1234!",  # pragma: allowlist secret
        )
        assert user.is_superuser is True
        assert user.is_staff is True
        assert user.is_admin is True  # was False before fix #423
        assert user.is_active is True

    # ── Fix 3: property clue rejects invalid vehicle type ──

    def test_property_clue_rejects_vehicle_clue_type(self) -> None:
        """Service layer validates clue_type and rejects 'vehicle'.
        (vehicle was erroneously listed in MCP docstring but never in model.)"""
        from apps.client.services.property_clue_service import PropertyClueService
        from apps.core.exceptions import ValidationException

        svc = PropertyClueService()
        with pytest.raises(ValidationException, match="INVALID_CLUE_TYPE"):
            svc._validate_clue_type("vehicle")

    def test_property_clue_model_has_correct_choices(self) -> None:
        """PropertyClue model defines exactly 5 clue types."""
        from apps.client.models import PropertyClue

        keys = [c[0] for c in PropertyClue.CLUE_TYPE_CHOICES]
        assert sorted(keys) == ["alipay", "bank", "other", "real_estate", "wechat"]
        assert "vehicle" not in keys

    # ── Fix 4: payment schema has confirm field ──

    def test_payment_in_schema_has_confirm_field(self) -> None:
        """ContractPaymentIn must expose confirm: bool (defaults False)."""
        from apps.contracts.schemas import ContractPaymentIn

        schema = ContractPaymentIn.model_json_schema()
        assert "confirm" in schema["properties"]
        assert schema["properties"]["confirm"]["default"] is False
        assert "contract_id" in schema["required"]
        assert "amount" in schema["required"]

    # ── Fix 5: docstring correctness (static check) ──

    def test_mcp_payment_docstring_has_correct_fields(self) -> None:
        """MCP create_payment docstring must document actual schema fields."""
        from mcp_server.tools.contracts.payments import create_payment

        doc = create_payment.__doc__ or ""
        assert "received_at" in doc, "docstring must name actual field received_at"
        assert "invoice_status" in doc, "docstring must name actual field invoice_status"
        assert "confirm" in doc, "docstring must mention confirm (required True)"
        assert "invoiced_amount" in doc, "docstring must mention invoiced_amount"
        # Old wrong field names must NOT appear
        assert "payment_date" not in doc, "docstring must NOT mention payment_date"
        assert "payment_type" not in doc, "docstring must NOT mention payment_type"

    def test_mcp_property_clue_docstring_no_vehicle(self) -> None:
        """MCP create_property_clue docstring must NOT mention non-existent vehicle."""
        from mcp_server.tools.clients.property_clues import create_property_clue

        doc = create_property_clue.__doc__ or ""
        assert "vehicle" not in doc, "docstring must NOT mention vehicle"
        # Valid types SHOULD be present
        assert "bank" in doc
        assert "alipay" in doc
        assert "wechat" in doc
        assert "real_estate" in doc
