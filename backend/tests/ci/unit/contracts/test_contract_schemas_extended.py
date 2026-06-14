"""
Extended tests for contracts.schemas.contract_schemas.

Covers: ContractIn validators, ContractOut resolvers (resolve_total_received,
resolve_total_invoiced, resolve_unpaid_amount, resolve_primary_lawyer,
resolve_matched_*, resolve_can_archive, resolve_reminders),
ContractUpdate, ContractPaginatedOut.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from apps.contracts.schemas.contract_schemas import (
    ClientPaymentRecordOut,
    ContractAssignmentOut,
    ContractIn,
    ContractOut,
    ContractPaginatedOut,
    ContractUpdate,
    FinalizedMaterialOut,
    UpdateLawyersIn,
)
from apps.contracts.models import FeeMode


# ═══════════════════════════════════════════════════════════════════════════════
# ContractIn validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestContractInValidation:
    def test_empty_lawyer_ids_raises(self):
        with pytest.raises(ValidationError, match="至少需要指派一个律师"):
            ContractIn(
                name="Test", case_type="civil", lawyer_ids=[], fee_mode=FeeMode.FIXED, fixed_amount=1000
            )

    def test_fixed_fee_valid(self):
        schema = ContractIn(
            name="Test", case_type="civil", lawyer_ids=[1], fee_mode=FeeMode.FIXED, fixed_amount=5000
        )
        assert schema.lawyer_ids == [1]

    def test_fixed_fee_zero_amount_raises(self):
        with pytest.raises(ValidationError, match="固定收费需填写金额"):
            ContractIn(
                name="Test", case_type="civil", lawyer_ids=[1], fee_mode=FeeMode.FIXED, fixed_amount=0
            )

    def test_fixed_fee_negative_amount_raises(self):
        with pytest.raises(ValidationError, match="固定收费需填写金额"):
            ContractIn(
                name="Test", case_type="civil", lawyer_ids=[1], fee_mode=FeeMode.FIXED, fixed_amount=-100
            )

    def test_fixed_fee_none_amount_raises(self):
        with pytest.raises(ValidationError, match="固定收费需填写金额"):
            ContractIn(
                name="Test", case_type="civil", lawyer_ids=[1], fee_mode=FeeMode.FIXED, fixed_amount=None
            )

    def test_semi_risk_valid(self):
        schema = ContractIn(
            name="Test", case_type="civil", lawyer_ids=[1],
            fee_mode=FeeMode.SEMI_RISK, fixed_amount=5000, risk_rate=10
        )
        assert schema.fee_mode == FeeMode.SEMI_RISK

    def test_semi_risk_no_amount_raises(self):
        with pytest.raises(ValidationError, match="半风险需填写前期金额"):
            ContractIn(
                name="Test", case_type="civil", lawyer_ids=[1],
                fee_mode=FeeMode.SEMI_RISK, fixed_amount=0, risk_rate=10
            )

    def test_semi_risk_no_rate_raises(self):
        with pytest.raises(ValidationError, match="半风险需填写风险比例"):
            ContractIn(
                name="Test", case_type="civil", lawyer_ids=[1],
                fee_mode=FeeMode.SEMI_RISK, fixed_amount=5000, risk_rate=0
            )

    def test_full_risk_valid(self):
        schema = ContractIn(
            name="Test", case_type="civil", lawyer_ids=[1],
            fee_mode=FeeMode.FULL_RISK, risk_rate=30
        )
        assert schema.fee_mode == FeeMode.FULL_RISK

    def test_full_risk_no_rate_raises(self):
        with pytest.raises(ValidationError, match="全风险需填写风险比例"):
            ContractIn(
                name="Test", case_type="civil", lawyer_ids=[1],
                fee_mode=FeeMode.FULL_RISK, risk_rate=0
            )

    def test_custom_valid(self):
        schema = ContractIn(
            name="Test", case_type="civil", lawyer_ids=[1],
            fee_mode=FeeMode.CUSTOM, custom_terms="自定义条款内容"
        )
        assert schema.fee_mode == FeeMode.CUSTOM

    def test_custom_empty_terms_raises(self):
        with pytest.raises(ValidationError, match="自定义收费需填写条款文本"):
            ContractIn(
                name="Test", case_type="civil", lawyer_ids=[1],
                fee_mode=FeeMode.CUSTOM, custom_terms=""
            )

    def test_custom_whitespace_terms_raises(self):
        with pytest.raises(ValidationError, match="自定义收费需填写条款文本"):
            ContractIn(
                name="Test", case_type="civil", lawyer_ids=[1],
                fee_mode=FeeMode.CUSTOM, custom_terms="   "
            )


# ═══════════════════════════════════════════════════════════════════════════════
# ContractOut resolvers
# ═══════════════════════════════════════════════════════════════════════════════


class TestContractOutResolvers:
    # ── resolve_total_received ──

    def test_resolve_total_received_normal(self):
        obj = MagicMock()
        p1 = MagicMock(); p1.amount = 1000
        p2 = MagicMock(); p2.amount = 2000
        obj.payments.all.return_value = [p1, p2]
        assert ContractOut.resolve_total_received(obj) == 3000.0

    def test_resolve_total_received_none_amount(self):
        obj = MagicMock()
        p1 = MagicMock(); p1.amount = None
        obj.payments.all.return_value = [p1]
        assert ContractOut.resolve_total_received(obj) == 0.0

    def test_resolve_total_received_empty(self):
        obj = MagicMock()
        obj.payments.all.return_value = []
        assert ContractOut.resolve_total_received(obj) == 0.0

    def test_resolve_total_received_type_error(self):
        obj = MagicMock()
        obj.payments.all.side_effect = TypeError("bad")
        assert ContractOut.resolve_total_received(obj) == 0.0

    # ── resolve_total_invoiced ──

    def test_resolve_total_invoiced_normal(self):
        obj = MagicMock()
        p1 = MagicMock(); p1.invoiced_amount = 500
        p2 = MagicMock(); p2.invoiced_amount = 700
        obj.payments.all.return_value = [p1, p2]
        assert ContractOut.resolve_total_invoiced(obj) == 1200.0

    def test_resolve_total_invoiced_none(self):
        obj = MagicMock()
        p1 = MagicMock(); p1.invoiced_amount = None
        obj.payments.all.return_value = [p1]
        assert ContractOut.resolve_total_invoiced(obj) == 0.0

    def test_resolve_total_invoiced_error(self):
        obj = MagicMock()
        obj.payments.all.side_effect = ValueError("bad")
        assert ContractOut.resolve_total_invoiced(obj) == 0.0

    # ── resolve_unpaid_amount ──

    def test_resolve_unpaid_amount_positive(self):
        obj = MagicMock()
        obj.fixed_amount = 10000
        # Mock resolve_total_received to return 3000
        with patch.object(ContractOut, "resolve_total_received", return_value=3000.0):
            result = ContractOut.resolve_unpaid_amount(obj)
            assert result == 7000.0

    def test_resolve_unpaid_amount_zero(self):
        obj = MagicMock()
        obj.fixed_amount = 3000
        with patch.object(ContractOut, "resolve_total_received", return_value=3000.0):
            result = ContractOut.resolve_unpaid_amount(obj)
            assert result == 0.0

    def test_resolve_unpaid_amount_overpaid_returns_zero(self):
        obj = MagicMock()
        obj.fixed_amount = 3000
        with patch.object(ContractOut, "resolve_total_received", return_value=5000.0):
            result = ContractOut.resolve_unpaid_amount(obj)
            assert result == 0.0

    def test_resolve_unpaid_amount_none_fixed(self):
        obj = MagicMock()
        obj.fixed_amount = None
        assert ContractOut.resolve_unpaid_amount(obj) is None

    def test_resolve_unpaid_amount_type_error(self):
        obj = MagicMock()
        obj.fixed_amount = "invalid"
        with patch.object(ContractOut, "resolve_total_received", side_effect=TypeError("bad")):
            result = ContractOut.resolve_unpaid_amount(obj)
            assert result is None

    # ── resolve_cases ──

    def test_resolve_cases_with_dtos(self):
        obj = MagicMock()
        dto = MagicMock()
        obj.case_dtos = [dto]
        with patch("apps.contracts.schemas.contract_schemas.CaseOut") as MockCaseOut:
            MockCaseOut.from_dto.return_value = "case_out"
            result = ContractOut.resolve_cases(obj)
            assert result == ["case_out"]

    def test_resolve_cases_without_dtos(self):
        obj = MagicMock()
        obj.case_dtos = None
        obj.cases.all.return_value = [MagicMock()]
        with patch("apps.contracts.schemas.contract_schemas.CaseOut") as MockCaseOut:
            MockCaseOut.from_model.return_value = "case_from_model"
            result = ContractOut.resolve_cases(obj)
            assert result == ["case_from_model"]

    # ── resolve_fee_mode ──

    def test_resolve_fee_mode(self):
        obj = MagicMock()
        obj.get_fee_mode_display.return_value = "固定收费"
        assert ContractOut.resolve_fee_mode(obj) == "固定收费"

    # ── resolve_representation_stages ──

    def test_resolve_representation_stages_with_values(self):
        obj = MagicMock()
        obj.representation_stages = ["first_instance"]
        result = ContractOut.resolve_representation_stages(obj)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_resolve_representation_stages_none(self):
        obj = MagicMock()
        obj.representation_stages = None
        result = ContractOut.resolve_representation_stages(obj)
        assert result == []

    def test_resolve_representation_stages_unknown_code(self):
        obj = MagicMock()
        obj.representation_stages = ["unknown_code"]
        result = ContractOut.resolve_representation_stages(obj)
        # Unknown codes should be passed through as-is
        assert "unknown_code" in result

    # ── resolve_reminders ──

    def test_resolve_reminders(self):
        obj = MagicMock()
        obj.id = 42
        with patch("apps.core.interfaces.ServiceLocator") as MockSL:
            mock_svc = MagicMock()
            mock_svc.export_contract_reminders_internal.return_value = [{"id": 1}]
            MockSL.get_reminder_service.return_value = mock_svc
            result = ContractOut.resolve_reminders(obj)
            assert len(result) == 1

    # ── resolve_supplementary_agreements ──

    def test_resolve_supplementary_agreements(self):
        obj = MagicMock()
        obj.supplementary_agreements.all.return_value = [MagicMock(), MagicMock()]
        result = ContractOut.resolve_supplementary_agreements(obj)
        assert len(result) == 2

    # ── resolve_assignments ──

    def test_resolve_assignments(self):
        obj = MagicMock()
        assignment = MagicMock()
        obj.assignments.all.return_value = [assignment]
        with patch("apps.contracts.schemas.contract_schemas.ContractAssignmentOut") as MockOut:
            MockOut.from_assignment.return_value = "assignment_out"
            result = ContractOut.resolve_assignments(obj)
            assert result == ["assignment_out"]

    # ── resolve_primary_lawyer ──

    def test_resolve_primary_lawyer_with_dto(self):
        obj = MagicMock()
        dto = MagicMock()
        obj.primary_lawyer_dto = dto
        with patch("apps.contracts.schemas.contract_schemas.LawyerOut") as MockLO:
            MockLO.from_dto.return_value = "lawyer_out"
            result = ContractOut.resolve_primary_lawyer(obj)
            assert result == "lawyer_out"

    def test_resolve_primary_lawyer_from_assignments_primary(self):
        obj = MagicMock()
        obj.primary_lawyer_dto = None
        primary = MagicMock()
        primary.is_primary = True
        primary.lawyer = MagicMock()
        primary.lawyer.real_name = "张律师"
        obj.assignments.all.return_value = [primary]
        with patch("apps.contracts.schemas.contract_schemas.LawyerOut") as MockLO:
            MockLO.from_model.return_value = "lawyer_from_model"
            result = ContractOut.resolve_primary_lawyer(obj)
            assert result == "lawyer_from_model"

    def test_resolve_primary_lawyer_fallback_to_lowest_order(self):
        obj = MagicMock()
        obj.primary_lawyer_dto = None
        a1 = MagicMock(); a1.is_primary = False; a1.order = 2; a1.id = 1; a1.lawyer = MagicMock()
        a2 = MagicMock(); a2.is_primary = False; a2.order = 1; a2.id = 2; a2.lawyer = MagicMock()
        obj.assignments.all.return_value = [a1, a2]
        with patch("apps.contracts.schemas.contract_schemas.LawyerOut") as MockLO:
            MockLO.from_model.return_value = "fallback_lawyer"
            result = ContractOut.resolve_primary_lawyer(obj)
            # a2 has lower order (1 < 2)
            MockLO.from_model.assert_called_with(a2.lawyer)

    def test_resolve_primary_lawyer_no_assignments(self):
        obj = MagicMock()
        obj.primary_lawyer_dto = None
        obj.assignments.all.return_value = []
        result = ContractOut.resolve_primary_lawyer(obj)
        assert result is None

    def test_resolve_primary_lawyer_no_lawyer_on_assignment(self):
        obj = MagicMock()
        obj.primary_lawyer_dto = None
        a = MagicMock(); a.is_primary = True; a.lawyer = None
        obj.assignments.all.return_value = [a]
        result = ContractOut.resolve_primary_lawyer(obj)
        assert result is None

    # ── resolve_matched_* ──

    def test_resolve_matched_document_template_present(self):
        obj = MagicMock()
        obj._computed_matched_document_template = "tpl_v1"
        assert ContractOut.resolve_matched_document_template(obj) == "tpl_v1"

    def test_resolve_matched_document_template_none(self):
        obj = MagicMock(spec=[])
        obj._computed_matched_document_template = None
        assert ContractOut.resolve_matched_document_template(obj) is None

    def test_resolve_matched_folder_templates_present(self):
        obj = MagicMock()
        obj._computed_matched_folder_templates = "folder_tpl"
        assert ContractOut.resolve_matched_folder_templates(obj) == "folder_tpl"

    def test_resolve_matched_folder_templates_none(self):
        obj = MagicMock(spec=[])
        obj._computed_matched_folder_templates = None
        assert ContractOut.resolve_matched_folder_templates(obj) is None

    def test_resolve_has_matched_templates_true(self):
        obj = MagicMock()
        obj._computed_has_matched_templates = True
        assert ContractOut.resolve_has_matched_templates(obj) is True

    def test_resolve_has_matched_templates_false(self):
        obj = MagicMock(spec=[])
        assert ContractOut.resolve_has_matched_templates(obj) is False

    # ── resolve_client_payment_records ──

    def test_resolve_client_payment_records_success(self):
        obj = MagicMock()
        obj.client_payment_records.all.return_value = [MagicMock()]
        result = ContractOut.resolve_client_payment_records(obj)
        assert len(result) == 1

    def test_resolve_client_payment_records_error(self):
        obj = MagicMock()
        obj.client_payment_records.all.side_effect = Exception("db error")
        result = ContractOut.resolve_client_payment_records(obj)
        assert result == []

    # ── resolve_finalized_materials ──

    def test_resolve_finalized_materials_success(self):
        obj = MagicMock()
        obj.finalized_materials.all.return_value = [MagicMock(), MagicMock()]
        result = ContractOut.resolve_finalized_materials(obj)
        assert len(result) == 2

    def test_resolve_finalized_materials_error(self):
        obj = MagicMock()
        obj.finalized_materials.all.side_effect = Exception("db error")
        result = ContractOut.resolve_finalized_materials(obj)
        assert result == []

    # ── resolve_can_archive ──

    def test_resolve_can_archive_all_present(self):
        obj = MagicMock()
        m1 = MagicMock(); m1.category = "contract_original"
        m2 = MagicMock(); m2.category = "archive_document"
        m3 = MagicMock(); m3.category = "authorization_material"
        obj.finalized_materials.all.return_value = [m1, m2, m3]
        with patch("apps.contracts.models.finalized_material.MaterialCategory") as MockCat:
            MockCat.CONTRACT_ORIGINAL = "contract_original"
            MockCat.ARCHIVE_DOCUMENT = "archive_document"
            MockCat.AUTHORIZATION_MATERIAL = "authorization_material"
            assert ContractOut.resolve_can_archive(obj) is True

    def test_resolve_can_archive_missing(self):
        obj = MagicMock()
        m1 = MagicMock(); m1.category = "contract_original"
        obj.finalized_materials.all.return_value = [m1]
        with patch("apps.contracts.models.finalized_material.MaterialCategory") as MockCat:
            MockCat.CONTRACT_ORIGINAL = "contract_original"
            MockCat.ARCHIVE_DOCUMENT = "archive_document"
            MockCat.AUTHORIZATION_MATERIAL = "authorization_material"
            assert ContractOut.resolve_can_archive(obj) is False

    def test_resolve_can_archive_error(self):
        obj = MagicMock()
        obj.finalized_materials.all.side_effect = Exception("db error")
        assert ContractOut.resolve_can_archive(obj) is False


# ═══════════════════════════════════════════════════════════════════════════════
# FinalizedMaterialOut resolvers
# ═══════════════════════════════════════════════════════════════════════════════


class TestFinalizedMaterialOutExtended:
    def test_resolve_category_label_value_error(self):
        obj = MagicMock()
        obj.get_category_display.side_effect = ValueError("bad")
        obj.category = "test_cat"
        assert FinalizedMaterialOut.resolve_category_label(obj) == "test_cat"

    def test_resolve_created_at_has_attr_and_value(self):
        obj = SimpleNamespace(created_at=MagicMock())
        obj.created_at.isoformat.return_value = "2024-06-01T10:00:00"
        assert FinalizedMaterialOut.resolve_created_at(obj) == "2024-06-01T10:00:00"

    def test_resolve_created_at_no_attr(self):
        obj = SimpleNamespace()
        assert FinalizedMaterialOut.resolve_created_at(obj) is None

    def test_resolve_created_at_none_value(self):
        obj = SimpleNamespace(created_at=None)
        assert FinalizedMaterialOut.resolve_created_at(obj) is None


# ═══════════════════════════════════════════════════════════════════════════════
# ClientPaymentRecordOut resolvers
# ═══════════════════════════════════════════════════════════════════════════════


class TestClientPaymentRecordOutExtended:
    def test_resolve_amount_zero(self):
        obj = MagicMock()
        obj.amount = 0
        assert ClientPaymentRecordOut.resolve_amount(obj) == 0.0

    def test_resolve_amount_float(self):
        obj = MagicMock()
        obj.amount = 1234.56
        assert ClientPaymentRecordOut.resolve_amount(obj) == 1234.56


# ═══════════════════════════════════════════════════════════════════════════════
# UpdateLawyersIn
# ═══════════════════════════════════════════════════════════════════════════════


class TestUpdateLawyersInExtended:
    def test_single_lawyer(self):
        schema = UpdateLawyersIn(lawyer_ids=[42])
        assert schema.lawyer_ids == [42]

    def test_many_lawyers(self):
        schema = UpdateLawyersIn(lawyer_ids=list(range(1, 20)))
        assert len(schema.lawyer_ids) == 19


# ═══════════════════════════════════════════════════════════════════════════════
# ContractUpdate
# ═══════════════════════════════════════════════════════════════════════════════


class TestContractUpdate:
    def test_default_values(self):
        schema = ContractUpdate()
        assert schema.name is None
        assert schema.case_type is None
        assert schema.status is None
        assert schema.is_filed is None

    def test_set_fields(self):
        schema = ContractUpdate(name="New Name", case_type="criminal")
        assert schema.name == "New Name"
        assert schema.case_type == "criminal"


# ═══════════════════════════════════════════════════════════════════════════════
# ContractPaginatedOut
# ═══════════════════════════════════════════════════════════════════════════════


class TestContractPaginatedOut:
    def test_schema_structure(self):
        # ContractPaginatedOut is a Schema, test that it can be instantiated
        assert hasattr(ContractPaginatedOut, "model_fields")
        fields = ContractPaginatedOut.model_fields
        assert "items" in fields
        assert "total" in fields
        assert "page" in fields
        assert "page_size" in fields
        assert "total_pages" in fields


# ═══════════════════════════════════════════════════════════════════════════════
# ContractAssignmentOut edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestContractAssignmentOutExtended:
    def test_from_assignment_real_name_none(self):
        obj = MagicMock()
        obj.id = 1
        obj.lawyer_id = 10
        obj.lawyer.real_name = None
        obj.lawyer.username = "fallback_user"
        obj.is_primary = False
        obj.order = 0
        result = ContractAssignmentOut.from_assignment(obj)
        assert result.lawyer_name == "fallback_user"
