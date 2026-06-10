"""Batch8 coverage tests for apps.contracts."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ── ArchiveLearningService ────────────────────────────────────────────────


class TestArchiveLearningService:
    """Test ArchiveLearningService."""

    def test_extract_keywords_empty_filename(self) -> None:
        from apps.contracts.services.archive.learning_service import extract_keywords

        result = extract_keywords("")
        assert result == []

    def test_extract_keywords_simple_doc_type(self) -> None:
        from apps.contracts.services.archive.learning_service import extract_keywords

        result = extract_keywords("起诉状.pdf")
        assert any("起诉状" in kw for kw in result)

    def test_extract_keywords_with_person_name(self) -> None:
        from apps.contracts.services.archive.learning_service import extract_keywords

        result = extract_keywords("张三起诉状.docx")
        assert any("起诉状" in kw for kw in result)

    def test_extract_keywords_pure_number(self) -> None:
        from apps.cases.models.log import _SENTINEL
        from apps.contracts.services.archive.learning_service import extract_keywords

        result = extract_keywords("12345.pdf")
        assert result == []

    def test_extract_keywords_with_parentheses(self) -> None:
        from apps.contracts.services.archive.learning_service import extract_keywords

        result = extract_keywords("案卷封面（某某案）.pdf")
        assert any("案卷封面" in kw or "封面" in kw for kw in result)

    def test_extract_keywords_case_number_removed(self) -> None:
        from apps.contracts.services.archive.learning_service import extract_keywords

        result = extract_keywords("(2024)粤0101民初1001号判决书.pdf")
        assert any("判决书" in kw for kw in result)

    def test_contains_document_keyword_true(self) -> None:
        from apps.contracts.services.archive.learning_service import _contains_document_keyword

        assert _contains_document_keyword("起诉状") is True

    def test_contains_document_keyword_false(self) -> None:
        from apps.contracts.services.archive.learning_service import _contains_document_keyword

        assert _contains_document_keyword("张福裕案件") is False

    def test_strip_non_keyword_parts_exact_match(self) -> None:
        from apps.contracts.services.archive.learning_service import _strip_non_keyword_parts

        result = _strip_non_keyword_parts("起诉状")
        assert result == "起诉状"

    def test_strip_non_keyword_parts_with_prefix(self) -> None:
        from apps.contracts.services.archive.learning_service import _strip_non_keyword_parts

        result = _strip_non_keyword_parts("张三起诉状")
        assert result == "起诉状"

    def test_strip_non_keyword_parts_compound_name(self) -> None:
        from apps.contracts.services.archive.learning_service import _strip_non_keyword_parts

        result = _strip_non_keyword_parts("案卷封面")
        assert result == "案卷封面"

    def test_is_non_keyword_attachment_empty(self) -> None:
        from apps.contracts.services.archive.learning_service import _is_non_keyword_attachment

        assert _is_non_keyword_attachment("") is False

    def test_is_non_keyword_attachment_non_chinese(self) -> None:
        from apps.contracts.services.archive.learning_service import _is_non_keyword_attachment

        assert _is_non_keyword_attachment("abc123") is False

    def test_is_non_keyword_attachment_person_name(self) -> None:
        from apps.contracts.services.archive.learning_service import _is_non_keyword_attachment

        assert _is_non_keyword_attachment("张三") is True

    def test_is_non_keyword_attachment_with_keyword(self) -> None:
        from apps.contracts.services.archive.learning_service import _is_non_keyword_attachment

        assert _is_non_keyword_attachment("起诉状") is False

    def test_generate_code_file_empty(self) -> None:
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        svc = ArchiveLearningService()
        result = svc._generate_code_file({})
        assert "LEARNED_FILENAME_KEYWORD_TO_ARCHIVE_CODE" in result
        assert "{}" in result

    def test_generate_code_file_with_rules(self) -> None:
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        svc = ArchiveLearningService()
        grouped = {"civil": {"B001": ["起诉状", "判决书"]}}
        result = svc._generate_code_file(grouped)
        assert "civil" in result
        assert "B001" in result
        assert "起诉状" in result


# ── ArchiveQueryService ───────────────────────────────────────────────────


class TestArchiveQueryService:
    """Test archive query service functions."""

    def test_get_contract_or_none_not_found(self, db: None) -> None:
        from apps.contracts.services.archive.archive_query_service import get_contract_or_none

        result = get_contract_or_none(99999)
        assert result is None

    def test_get_material_or_none_not_found(self, db: None) -> None:
        from apps.contracts.services.archive.archive_query_service import get_material_or_none

        result = get_material_or_none(99999, 99999)
        assert result is None

    def test_get_materials_for_contract_empty(self, db: None) -> None:
        from apps.contracts.services.archive.archive_query_service import get_materials_for_contract

        result = get_materials_for_contract(99999)
        assert result.count() == 0


# ── ArchiveChecklistService ───────────────────────────────────────────────


class TestArchiveChecklistService:
    """Test ArchiveChecklistService facade."""

    def test_get_template_items_unknown_category(self) -> None:
        from apps.contracts.services.archive.checklist.service import ArchiveChecklistService

        svc = ArchiveChecklistService()
        result = svc.get_template_items("unknown_category_xyz")
        assert isinstance(result, list)

    def test_get_auto_detect_items_unknown_category(self) -> None:
        from apps.contracts.services.archive.checklist.service import ArchiveChecklistService

        svc = ArchiveChecklistService()
        result = svc.get_auto_detect_items("unknown_category_xyz")
        assert isinstance(result, list)


# ── Contract schemas ──────────────────────────────────────────────────────


class TestContractSchemas:
    """Test contract schema resolvers."""

    def test_finalized_material_out_category_label(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = SimpleNamespace(category="evidence", get_category_display=lambda: "证据材料")
        result = FinalizedMaterialOut.resolve_category_label(obj)
        assert result == "证据材料"

    def test_finalized_material_out_category_label_error(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = SimpleNamespace(category="evidence")
        result = FinalizedMaterialOut.resolve_category_label(obj)
        assert result == "evidence"

    def test_finalized_material_out_filename(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = SimpleNamespace(file_path="2024/01/test.pdf")
        result = FinalizedMaterialOut.resolve_filename(obj)
        assert result == "test.pdf"

    def test_finalized_material_out_filename_empty(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = SimpleNamespace(file_path="")
        result = FinalizedMaterialOut.resolve_filename(obj)
        assert result == ""

    def test_finalized_material_out_file_url(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = SimpleNamespace(file_path="2024/01/test.pdf")
        result = FinalizedMaterialOut.resolve_file_url(obj)
        assert "test.pdf" in result

    def test_finalized_material_out_file_url_empty(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = SimpleNamespace(file_path="")
        result = FinalizedMaterialOut.resolve_file_url(obj)
        assert result == ""

    def test_finalized_material_out_uploaded_at(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        dt = datetime(2024, 1, 15, 10, 30)
        obj = SimpleNamespace(uploaded_at=dt)
        result = FinalizedMaterialOut.resolve_uploaded_at(obj)
        assert result == dt.isoformat()

    def test_finalized_material_out_uploaded_at_none(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = SimpleNamespace(uploaded_at=None)
        result = FinalizedMaterialOut.resolve_uploaded_at(obj)
        assert result is None

    def test_finalized_material_out_created_at(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        dt = datetime(2024, 1, 15, 10, 30)
        obj = SimpleNamespace(created_at=dt)
        result = FinalizedMaterialOut.resolve_created_at(obj)
        assert result == dt.isoformat()

    def test_finalized_material_out_created_at_none(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = SimpleNamespace(created_at=None)
        result = FinalizedMaterialOut.resolve_created_at(obj)
        assert result is None

    def test_client_payment_record_out_contract(self) -> None:
        from apps.contracts.schemas.contract_schemas import ClientPaymentRecordOut

        obj = SimpleNamespace(contract_id=42)
        result = ClientPaymentRecordOut.resolve_contract(obj)
        assert result == 42

    def test_client_payment_record_out_amount(self) -> None:
        from apps.contracts.schemas.contract_schemas import ClientPaymentRecordOut

        obj = SimpleNamespace(amount=100.50)
        result = ClientPaymentRecordOut.resolve_amount(obj)
        assert result == 100.50

    def test_client_payment_record_out_amount_none(self) -> None:
        from apps.contracts.schemas.contract_schemas import ClientPaymentRecordOut

        obj = SimpleNamespace(amount=None)
        result = ClientPaymentRecordOut.resolve_amount(obj)
        assert result == 0.0

    def test_client_payment_record_out_created_at(self) -> None:
        from apps.contracts.schemas.contract_schemas import ClientPaymentRecordOut

        dt = datetime(2024, 1, 15)
        obj = SimpleNamespace(created_at=dt)
        result = ClientPaymentRecordOut.resolve_created_at(obj)
        assert result == dt.isoformat()

    def test_client_payment_record_out_created_at_none(self) -> None:
        from apps.contracts.schemas.contract_schemas import ClientPaymentRecordOut

        obj = SimpleNamespace(created_at=None)
        result = ClientPaymentRecordOut.resolve_created_at(obj)
        assert result is None

    def test_contract_assignment_out_from_assignment(self) -> None:
        from apps.contracts.schemas.contract_schemas import ContractAssignmentOut

        lawyer = SimpleNamespace(real_name="TestLawyer", username="testuser")
        assignment = SimpleNamespace(id=1, lawyer_id=10, lawyer=lawyer, is_primary=True, order=1)
        result = ContractAssignmentOut.from_assignment(assignment)
        assert result.lawyer_name == "TestLawyer"
        assert result.is_primary is True

    def test_contract_assignment_out_no_real_name(self) -> None:
        from apps.contracts.schemas.contract_schemas import ContractAssignmentOut

        lawyer = SimpleNamespace(real_name=None, username="testuser")
        assignment = SimpleNamespace(id=1, lawyer_id=10, lawyer=lawyer, is_primary=False, order=1)
        result = ContractAssignmentOut.from_assignment(assignment)
        assert result.lawyer_name == "testuser"

    def test_contract_assignment_out_no_lawyer(self) -> None:
        from apps.contracts.schemas.contract_schemas import ContractAssignmentOut

        assignment = SimpleNamespace(id=1, lawyer_id=10, lawyer=None, is_primary=False, order=1)
        result = ContractAssignmentOut.from_assignment(assignment)
        assert result.lawyer_name == ""


# ── ContractServiceAdapter ────────────────────────────────────────────────


class TestContractServiceAdapter:
    """Test ContractServiceAdapter methods."""

    def test_get_fee_mode_display(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        mock_cs = MagicMock()
        svc = ContractServiceAdapter(contract_service=mock_cs)
        result = svc.get_fee_mode_display_internal("fixed")
        # Should return the display value or the raw value
        assert isinstance(result, str)

    def test_get_fee_mode_display_unknown(self) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        mock_cs = MagicMock()
        svc = ContractServiceAdapter(contract_service=mock_cs)
        result = svc.get_fee_mode_display_internal("unknown_mode")
        assert result == "unknown_mode"

    def test_get_contract_model_internal_not_found(self, db: None) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        mock_cs = MagicMock()
        svc = ContractServiceAdapter(contract_service=mock_cs)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = svc.get_contract_model_internal(99999)
        assert result is None

    def test_get_opposing_parties_internal(self, db: None) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        mock_cs = MagicMock()
        svc = ContractServiceAdapter(contract_service=mock_cs)
        with patch.object(svc, "get_party_roles_by_contract_internal", return_value=[
            SimpleNamespace(role_type="OPPOSING"),
            SimpleNamespace(role_type="PRINCIPAL"),
        ]):
            result = svc.get_opposing_parties_internal(1)
        assert len(result) == 1

    def test_get_principals_internal(self, db: None) -> None:
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        mock_cs = MagicMock()
        svc = ContractServiceAdapter(contract_service=mock_cs)
        with patch.object(svc, "get_party_roles_by_contract_internal", return_value=[
            SimpleNamespace(role_type="OPPOSING"),
            SimpleNamespace(role_type="PRINCIPAL"),
        ]):
            result = svc.get_principals_internal(1)
        assert len(result) == 1


# ── ArchiveGenerationService ──────────────────────────────────────────────


class TestArchiveGenerationService:
    """Test ArchiveGenerationService facade."""

    def test_get_template_path_returns_none(self) -> None:
        from apps.contracts.services.archive.generation.service import ArchiveGenerationService

        svc = ArchiveGenerationService()
        result = svc.get_template_path("nonexistent_subtype")
        assert result is None


# ── Contract models ───────────────────────────────────────────────────────


class TestContractModels:
    """Test contract model methods."""

    def test_contract_str(self, db: None) -> None:
        from apps.contracts.models import Contract

        contract = Contract.objects.create(name="TestContractB8")
        assert str(contract) == "TestContractB8"

    def test_contract_party_str(self, db: None) -> None:
        from apps.contracts.models import Contract, ContractParty
        from apps.client.models import Client

        contract = Contract.objects.create(name="PartyContract")
        client = Client.objects.create(name="PartyClient", client_type="natural")
        party = ContractParty.objects.create(contract=contract, client=client, role="PRINCIPAL")
        result = str(party)
        assert "PRINCIPAL" in result

    def test_financial_str(self, db: None) -> None:
        from apps.contracts.models import Contract, ContractFinanceLog
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="FinFirm")
        lawyer = Lawyer.objects.create_user(username="finuser", password="p", law_firm=firm)
        contract = Contract.objects.create(name="FinContract")
        log = ContractFinanceLog.objects.create(contract=contract, actor=lawyer, action="create", level="info")
        result = str(log)
        assert result is not None

    def test_supplementary_str(self, db: None) -> None:
        from apps.contracts.models import Contract, SupplementaryAgreement

        contract = Contract.objects.create(name="SuppContract")
        supp = SupplementaryAgreement.objects.create(
            contract=contract,
            name="TestSupp",
        )
        result = str(supp)
        assert "TestSupp" in result or str(supp.id) in result

    def test_invoice_str(self, db: None) -> None:
        from apps.contracts.models import Contract, Invoice

        contract = Contract.objects.create(name="InvContract")
        inv = Invoice.objects.create(contract=contract, amount=5000, invoice_number="INV-001")
        result = str(inv)
        assert "INV-001" in result or str(inv.id) in result


# ── Archive constants ─────────────────────────────────────────────────────


class TestArchiveConstants:
    """Test archive constants."""

    def test_checklist_item_dataclass(self) -> None:
        from apps.contracts.services.archive.constants import ChecklistItem

        item = ChecklistItem(code="B001", name="起诉状", required=False, auto_detect=False)
        assert item.code == "B001"
        assert item.name == "起诉状"

    def test_category_mapping(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        result = get_archive_category("civil")
        assert isinstance(result, str)

    def test_category_mapping_unknown(self) -> None:
        from apps.contracts.services.archive.category_mapping import get_archive_category

        result = get_archive_category("unknown_type_xyz")
        # Should return a default or empty string
        assert isinstance(result, str)


# ── Override service ──────────────────────────────────────────────────────


class TestOverrideService:
    """Test archive override service."""

    def test_override_service_imports(self) -> None:
        from apps.contracts.services.archive.override_service import (
            get_overrides_for_contract,
            set_override,
        )
        assert callable(get_overrides_for_contract)
        assert callable(set_override)

    def test_get_overrides_empty(self, db: None) -> None:
        from apps.contracts.services.archive.override_service import get_overrides_for_contract

        result = get_overrides_for_contract(99999)
        assert isinstance(result, dict)
