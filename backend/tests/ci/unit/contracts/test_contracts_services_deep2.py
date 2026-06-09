"""Tests for supplementary agreement, lawyer assignment, filing number, display, progress, and archive services."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.models import (
    Contract,
    ContractAssignment,
    ContractPayment,
    ContractStatus,
    FeeMode,
    InvoiceStatus,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)
from apps.contracts.services.supplementary.supplementary_agreement_service import SupplementaryAgreementService
from apps.contracts.services.assignment.filing_number_service import FilingNumberService
from apps.contracts.services.contract.query.progress_service import ContractProgressService
from apps.contracts.services.contract.query.display_service import ContractDisplayService
from apps.contracts.services.contract.query.template_cache import ContractTemplateCache
from apps.contracts.services.contract.assemblers.contract_list_assembler import ContractListAssembler
from apps.contracts.services.contract.assemblers.contract_dto_assembler import ContractDtoAssembler
from apps.contracts.services.contract.query.facade import ContractQueryFacade
from apps.contracts.services.contract.domain.validator import ContractValidator
from apps.core.exceptions import NotFoundError, ValidationException
from apps.testing.factories import CaseFactory, ClientFactory, ContractFactory, LawyerFactory


# ── SupplementaryAgreementService tests ──


@pytest.mark.django_db
class TestSupplementaryAgreementService:
    def _make_service(self):
        mock_client_svc = MagicMock()
        mock_client_svc.get_clients_by_ids.return_value = [MagicMock(id=1)]
        return SupplementaryAgreementService(client_service=mock_client_svc)

    def test_create_supplementary_agreement(self, db):
        svc = self._make_service()
        c = ContractFactory()
        sa = svc.create_supplementary_agreement(c.pk, "SA-1", None)
        assert sa.pk is not None
        assert sa.name == "SA-1"
        assert sa.contract_id == c.pk

    def test_create_supplementary_agreement_not_found(self, db):
        svc = self._make_service()
        with pytest.raises(NotFoundError):
            svc.create_supplementary_agreement(99999, "SA-1", None)

    def test_create_supplementary_agreement_with_parties(self, db):
        svc = self._make_service()
        c = ContractFactory()
        client = ClientFactory()
        svc.client_service.get_clients_by_ids.return_value = [MagicMock(id=client.id)]
        sa = svc.create_supplementary_agreement(c.pk, "SA-1", [client.id])
        assert SupplementaryAgreementParty.objects.filter(supplementary_agreement=sa).count() == 1

    def test_get_supplementary_agreement(self, db):
        svc = self._make_service()
        c = ContractFactory()
        sa = SupplementaryAgreement.objects.create(contract=c, name="Test SA")
        result = svc.get_supplementary_agreement(sa.pk)
        assert result.pk == sa.pk

    def test_get_supplementary_agreement_not_found(self, db):
        svc = self._make_service()
        with pytest.raises(NotFoundError):
            svc.get_supplementary_agreement(99999)

    def test_list_by_contract(self, db):
        svc = self._make_service()
        c = ContractFactory()
        SupplementaryAgreement.objects.create(contract=c, name="SA-1")
        SupplementaryAgreement.objects.create(contract=c, name="SA-2")
        result = svc.list_by_contract(c.pk)
        assert len(result) == 2

    def test_update_supplementary_agreement_name(self, db):
        svc = self._make_service()
        c = ContractFactory()
        sa = SupplementaryAgreement.objects.create(contract=c, name="Old")
        updated = svc.update_supplementary_agreement(sa.pk, name="New")
        assert updated.name == "New"

    def test_update_supplementary_agreement_not_found(self, db):
        svc = self._make_service()
        with pytest.raises(NotFoundError):
            svc.update_supplementary_agreement(99999, name="X")

    def test_update_supplementary_agreement_parties(self, db):
        svc = self._make_service()
        c = ContractFactory()
        client = ClientFactory()
        sa = SupplementaryAgreement.objects.create(contract=c, name="SA")
        svc.client_service.get_clients_by_ids.return_value = [MagicMock(id=client.id)]
        updated = svc.update_supplementary_agreement(sa.pk, party_ids=[client.id])
        assert SupplementaryAgreementParty.objects.filter(supplementary_agreement=sa).count() == 1

    def test_update_supplementary_agreement_replace_parties(self, db):
        svc = self._make_service()
        c = ContractFactory()
        client1 = ClientFactory()
        client2 = ClientFactory()
        sa = SupplementaryAgreement.objects.create(contract=c, name="SA")
        SupplementaryAgreementParty.objects.create(supplementary_agreement=sa, client_id=client1.id)
        svc.client_service.get_clients_by_ids.return_value = [MagicMock(id=client2.id)]
        svc.update_supplementary_agreement(sa.pk, party_ids=[client2.id])
        assert SupplementaryAgreementParty.objects.filter(supplementary_agreement=sa).count() == 1

    def test_delete_supplementary_agreement(self, db):
        svc = self._make_service()
        c = ContractFactory()
        sa = SupplementaryAgreement.objects.create(contract=c, name="SA")
        svc.delete_supplementary_agreement(sa.pk)
        assert not SupplementaryAgreement.objects.filter(pk=sa.pk).exists()

    def test_delete_supplementary_agreement_not_found(self, db):
        svc = self._make_service()
        with pytest.raises(NotFoundError):
            svc.delete_supplementary_agreement(99999)


# ── FilingNumberService tests ──


@pytest.mark.django_db
class TestFilingNumberService:
    def test_generate_contract_filing_number(self, db):
        svc = FilingNumberService()
        c = ContractFactory()
        result = svc.generate_contract_filing_number(c.pk, "civil", 2026)
        assert "2026" in result
        assert "HT" in result

    def test_generate_contract_filing_number_empty_type(self, db):
        svc = FilingNumberService()
        with pytest.raises(ValidationException):
            svc.generate_contract_filing_number(1, "", 2026)

    def test_generate_contract_filing_number_invalid_year(self, db):
        svc = FilingNumberService()
        with pytest.raises(ValidationException):
            svc.generate_contract_filing_number(1, "civil", 1800)

    def test_format_case_type_labels(self, db):
        svc = FilingNumberService()
        assert svc._format_case_type_label("civil") == "民商事"
        assert svc._format_case_type_label("criminal") == "刑事"
        assert svc._format_case_type_label("administrative") == "行政"
        assert svc._format_case_type_label("labor") == "劳动仲裁"
        assert svc._format_case_type_label("intl") == "商事仲裁"
        assert svc._format_case_type_label("special") == "专项服务"
        assert svc._format_case_type_label("advisor") == "常法顾问"
        assert svc._format_case_type_label("unknown") == "unknown"

    def test_get_next_contract_sequence(self, db):
        svc = FilingNumberService()
        seq = svc._get_next_contract_sequence(2026)
        assert seq >= 1


# ── ContractProgressService tests ──


@pytest.mark.django_db
class TestContractProgressService:
    def test_get_payment_progress_fixed(self, db):
        svc = ContractProgressService()
        c = ContractFactory(fee_mode=FeeMode.FIXED, fixed_amount=Decimal("10000"))
        ContractPayment.objects.create(contract=c, amount=Decimal("5000"))
        result = svc.get_payment_progress(c)
        assert result["progress_percent"] == 50
        assert result["is_completed"] is False

    def test_get_payment_progress_completed(self, db):
        svc = ContractProgressService()
        c = ContractFactory(fee_mode=FeeMode.FIXED, fixed_amount=Decimal("10000"))
        ContractPayment.objects.create(contract=c, amount=Decimal("10000"))
        result = svc.get_payment_progress(c)
        assert result["progress_percent"] == 100
        assert result["is_completed"] is True

    def test_get_payment_progress_semi_risk(self, db):
        svc = ContractProgressService()
        c = ContractFactory(fee_mode=FeeMode.SEMI_RISK, fixed_amount=Decimal("5000"))
        ContractPayment.objects.create(contract=c, amount=Decimal("2500"))
        result = svc.get_payment_progress(c)
        assert result["progress_percent"] == 50

    def test_get_payment_progress_full_risk(self, db):
        svc = ContractProgressService()
        c = ContractFactory(fee_mode=FeeMode.FULL_RISK)
        result = svc.get_payment_progress(c)
        assert result["progress_percent"] is None

    def test_get_payment_progress_custom(self, db):
        svc = ContractProgressService()
        c = ContractFactory(fee_mode=FeeMode.CUSTOM)
        result = svc.get_payment_progress(c)
        assert result["progress_percent"] is None

    def test_get_payment_progress_over_100(self, db):
        svc = ContractProgressService()
        c = ContractFactory(fee_mode=FeeMode.FIXED, fixed_amount=Decimal("1000"))
        ContractPayment.objects.create(contract=c, amount=Decimal("2000"))
        result = svc.get_payment_progress(c)
        assert result["progress_percent"] == 100

    def test_get_invoice_summary(self, db):
        svc = ContractProgressService()
        c = ContractFactory()
        ContractPayment.objects.create(
            contract=c, amount=Decimal("1000"), invoiced_amount=Decimal("500"),
            invoice_status=InvoiceStatus.INVOICED_PARTIAL
        )
        result = svc.get_invoice_summary(c)
        assert result["total_received"] == Decimal("1000")
        assert result["invoiced_amount"] == Decimal("500")
        assert result["uninvoiced_amount"] == Decimal("500")
        assert result["has_pending"] is True

    def test_get_invoice_summary_fully_invoiced(self, db):
        svc = ContractProgressService()
        c = ContractFactory()
        ContractPayment.objects.create(
            contract=c, amount=Decimal("1000"), invoiced_amount=Decimal("1000"),
            invoice_status=InvoiceStatus.INVOICED_FULL
        )
        result = svc.get_invoice_summary(c)
        assert result["has_pending"] is False
        assert result["invoice_percent"] == 100

    def test_get_invoice_summary_empty(self, db):
        svc = ContractProgressService()
        c = ContractFactory()
        result = svc.get_invoice_summary(c)
        assert result["total_received"] == Decimal("0")

    def test_get_contract_not_found(self, db):
        svc = ContractProgressService()
        with pytest.raises(NotFoundError):
            svc._get_contract(99999)


# ── ContractTemplateCache tests ──


class TestContractTemplateCache:
    def test_set_and_get_document_templates(self):
        cache = ContractTemplateCache()
        templates = [{"name": "T1", "type_display": "文书"}]
        cache.set_document_templates("labor", templates)
        assert cache.get_document_templates("labor") == templates

    def test_get_document_templates_miss(self):
        cache = ContractTemplateCache()
        assert cache.get_document_templates("special") is None

    def test_set_and_get_folder_templates(self):
        cache = ContractTemplateCache()
        templates = [{"name": "F1"}]
        cache.set_folder_templates("labor", templates)
        assert cache.get_folder_templates("labor") == templates

    def test_set_and_get_template_check(self):
        cache = ContractTemplateCache()
        result = {"has_folder": True, "has_document": False}
        cache.set_template_check("labor", result)
        assert cache.get_template_check("labor") == result

    def test_clear_cache_for_case_type(self):
        cache = ContractTemplateCache()
        cache.set_document_templates("intl", [{"name": "T1"}])
        cache.clear_cache_for_case_type("intl")
        assert cache.get_document_templates("intl") is None

    def test_clear_all_cache(self):
        cache = ContractTemplateCache()
        cache.set_document_templates("advisor", [{"name": "T1"}])
        cache.set_folder_templates("special", [{"name": "F1"}])
        cache.clear_all_cache()
        assert cache.get_document_templates("advisor") is None
        assert cache.get_folder_templates("special") is None


# ── ContractDisplayService tests ──


@pytest.mark.django_db
class TestContractDisplayService:
    def _make_service(self):
        mock_doc_svc = MagicMock()
        mock_doc_svc.find_matching_contract_templates.return_value = [
            {"name": "起诉状", "type_display": "文书"}
        ]
        mock_doc_svc.find_matching_folder_templates.return_value = [
            {"name": "民事案件文件夹"}
        ]
        mock_doc_svc.check_has_matching_templates.return_value = {
            "has_folder": True, "has_document": True
        }
        return ContractDisplayService(
            document_service=mock_doc_svc,
            template_cache=ContractTemplateCache(),
        )

    def test_get_matched_document_template(self, db):
        svc = self._make_service()
        c = ContractFactory(case_type="labor")
        result = svc.get_matched_document_template(c)
        assert "起诉状" in result

    def test_get_matched_document_template_no_match(self, db):
        mock_doc_svc = MagicMock()
        mock_doc_svc.find_matching_contract_templates.return_value = []
        svc = ContractDisplayService(document_service=mock_doc_svc, template_cache=ContractTemplateCache())
        c = ContractFactory(case_type="criminal")
        result = svc.get_matched_document_template(c)
        assert result == "无匹配模板"

    def test_get_matched_document_templates_list(self, db):
        svc = self._make_service()
        c = ContractFactory(case_type="intl")
        result = svc.get_matched_document_templates_list(c)
        assert len(result) == 1

    def test_get_matched_folder_templates(self, db):
        svc = self._make_service()
        c = ContractFactory(case_type="advisor")
        result = svc.get_matched_folder_templates(c)
        assert "民事案件文件夹" in result

    def test_get_matched_folder_templates_no_match(self, db):
        mock_doc_svc = MagicMock()
        mock_doc_svc.find_matching_folder_templates.return_value = []
        svc = ContractDisplayService(document_service=mock_doc_svc, template_cache=ContractTemplateCache())
        c = ContractFactory(case_type="criminal")
        result = svc.get_matched_folder_templates(c)
        assert result == "无匹配模板"

    def test_get_matched_folder_templates_list(self, db):
        svc = self._make_service()
        c = ContractFactory(case_type="special")
        result = svc.get_matched_folder_templates_list(c)
        assert len(result) == 1

    def test_has_matched_templates(self, db):
        svc = self._make_service()
        c = ContractFactory(case_type="administrative")
        assert svc.has_matched_templates(c) is True

    def test_has_matched_templates_no_folder(self, db):
        mock_doc_svc = MagicMock()
        mock_doc_svc.check_has_matching_templates.return_value = {
            "has_folder": False, "has_document": True
        }
        svc = ContractDisplayService(document_service=mock_doc_svc, template_cache=ContractTemplateCache())
        c = ContractFactory(case_type="criminal")
        assert svc.has_matched_templates(c) is False

    def test_batch_get_template_info_empty(self, db):
        svc = self._make_service()
        result = svc.batch_get_template_info([])
        assert result == {}

    def test_batch_get_template_info(self, db):
        svc = self._make_service()
        c1 = ContractFactory(case_type="labor")
        c2 = ContractFactory(case_type="labor")
        result = svc.batch_get_template_info([c1, c2])
        assert c1.pk in result
        assert c2.pk in result

    def test_clear_cache_for_case_type(self, db):
        svc = self._make_service()
        svc.clear_cache_for_case_type("civil")

    def test_clear_all_cache(self, db):
        svc = self._make_service()
        svc.clear_all_cache()


# ── ContractListAssembler tests ──


@pytest.mark.django_db
class TestContractListAssembler:
    def test_enrich_empty(self, db):
        assembler = ContractListAssembler()
        assembler.enrich([])

    def test_enrich_with_contracts(self, db):
        assembler = ContractListAssembler()
        c = ContractFactory()
        # Mock the display service to avoid real DB template lookups
        with patch("apps.contracts.services.contract.query.ContractDisplayService") as MockDisplay:
            mock_svc = MagicMock()
            mock_svc.batch_get_template_info.return_value = {
                c.pk: {"document_template": "T", "folder_template": "F", "has_templates": True}
            }
            MockDisplay.return_value = mock_svc
            assembler.enrich([c])
        assert hasattr(c, "_computed_matched_document_template")


# ── ContractDTOAssembler tests ──


@pytest.mark.django_db
class TestContractDTOAssembler:
    def test_assemble_basic(self, db):
        assembler = ContractDtoAssembler()
        c = ContractFactory()
        result = assembler.to_dto(c)
        assert result is not None


# ── ArchiveQueryService tests ──


@pytest.mark.django_db
class TestArchiveQueryService:
    def test_get_contract_or_none_found(self, db):
        from apps.contracts.services.archive.archive_query_service import get_contract_or_none

        c = ContractFactory()
        result = get_contract_or_none(c.pk)
        assert result is not None
        assert result.pk == c.pk

    def test_get_contract_or_none_not_found(self, db):
        from apps.contracts.services.archive.archive_query_service import get_contract_or_none

        result = get_contract_or_none(99999)
        assert result is None

    def test_get_materials_for_contract(self, db):
        from apps.contracts.services.archive.archive_query_service import get_materials_for_contract

        c = ContractFactory()
        result = get_materials_for_contract(c.pk)
        assert result.count() == 0

    def test_get_material_or_none(self, db):
        from apps.contracts.services.archive.archive_query_service import get_material_or_none

        result = get_material_or_none(99999, 1)
        assert result is None

    def test_reorder_materials(self, db):
        from apps.contracts.services.archive.archive_query_service import reorder_materials

        c = ContractFactory()
        reorder_materials(c.pk, {})

    def test_move_material(self, db):
        from apps.contracts.services.archive.archive_query_service import move_material
        from apps.contracts.models import FinalizedMaterial

        c = ContractFactory()
        material = FinalizedMaterial.objects.create(
            contract=c, original_filename="test.pdf", file_path="test.pdf",
            archive_item_code="A", category="OTHER"
        )
        move_material(material, "B")
        material.refresh_from_db()
        assert material.archive_item_code == "B"
