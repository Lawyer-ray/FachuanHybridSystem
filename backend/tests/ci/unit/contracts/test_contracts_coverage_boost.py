"""Tests for contract schemas, display service, and admin service with mocking."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── Contract Schemas ────────────────────────────────────────────────────────


class TestFinalizedMaterialOutSchema:
    """contracts/schemas/contract_schemas.py FinalizedMaterialOut tests."""

    def test_resolve_category_label_with_display(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = MagicMock()
        obj.get_category_display.return_value = "归档文书"
        result = FinalizedMaterialOut.resolve_category_label(obj)
        assert result == "归档文书"

    def test_resolve_category_label_fallback(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = MagicMock()
        obj.get_category_display.side_effect = ValueError("no display")
        obj.category = "archive_document"
        result = FinalizedMaterialOut.resolve_category_label(obj)
        assert result == "archive_document"

    def test_resolve_filename_with_path(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = MagicMock()
        obj.file_path = "/uploads/2024/doc.pdf"
        result = FinalizedMaterialOut.resolve_filename(obj)
        assert result == "doc.pdf"

    def test_resolve_filename_empty(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = MagicMock()
        obj.file_path = ""
        result = FinalizedMaterialOut.resolve_filename(obj)
        assert result == ""

    def test_resolve_file_url_with_path(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = MagicMock()
        obj.file_path = "materials/test.pdf"
        result = FinalizedMaterialOut.resolve_file_url(obj)
        assert "materials/test.pdf" in result

    def test_resolve_file_url_empty(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = MagicMock()
        obj.file_path = ""
        result = FinalizedMaterialOut.resolve_file_url(obj)
        assert result == ""

    def test_resolve_uploaded_at_with_value(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut
        from datetime import datetime

        obj = MagicMock()
        obj.uploaded_at = datetime(2024, 1, 1, 12, 0, 0)
        result = FinalizedMaterialOut.resolve_uploaded_at(obj)
        assert "2024-01-01" in result

    def test_resolve_uploaded_at_none(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = MagicMock()
        obj.uploaded_at = None
        result = FinalizedMaterialOut.resolve_uploaded_at(obj)
        assert result is None

    def test_resolve_created_at_with_value(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut
        from datetime import datetime

        obj = MagicMock()
        obj.created_at = datetime(2024, 6, 15, 10, 0, 0)
        result = FinalizedMaterialOut.resolve_created_at(obj)
        assert "2024-06-15" in result

    def test_resolve_created_at_none(self) -> None:
        from apps.contracts.schemas.contract_schemas import FinalizedMaterialOut

        obj = MagicMock(spec=[])  # no created_at attr
        result = FinalizedMaterialOut.resolve_created_at(obj)
        assert result is None


class TestClientPaymentRecordOutSchema:
    """contracts/schemas/contract_schemas.py ClientPaymentRecordOut tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.schemas.contract_schemas import ClientPaymentRecordOut

        assert ClientPaymentRecordOut is not None


# ── Contract Display Service ────────────────────────────────────────────────


class TestContractDisplayService:
    """contracts/services/contract/query/display_service.py tests."""

    def test_init(self) -> None:
        from apps.contracts.services.contract.query.display_service import ContractDisplayService

        svc = ContractDisplayService(document_service=MagicMock(), template_cache=MagicMock())
        assert svc is not None

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.query.display_service import ContractDisplayService

        assert ContractDisplayService is not None


# ── Case Admin Service ──────────────────────────────────────────────────────


class TestCaseAdminServiceExtended:
    """cases/services/case/case_admin_service.py extended tests."""

    def _make_service(self) -> Any:
        from apps.cases.services.case.case_admin_service import CaseAdminService

        doc_service = MagicMock()
        filing_service = MagicMock()
        return CaseAdminService(
            document_service=doc_service, filing_number_service=filing_service
        ), doc_service, filing_service

    def test_get_matched_folder_templates(self) -> None:
        service, doc_service, _ = self._make_service()
        doc_service.get_matched_folder_templates.return_value = "民事案件模板"
        result = service.get_matched_folder_templates("civil")
        assert result == "民事案件模板"

    def test_get_matched_folder_templates_with_legal_statuses(self) -> None:
        service, doc_service, _ = self._make_service()
        doc_service.get_matched_folder_templates_with_legal_status.return_value = "原告模板"
        result = service.get_matched_folder_templates("civil", ["plaintiff"])
        # Result is wrapped in a tuple by the service
        assert "原告模板" in str(result)

    def test_get_matched_folder_templates_exception(self) -> None:
        service, doc_service, _ = self._make_service()
        doc_service.get_matched_folder_templates.side_effect = Exception("service down")
        result = service.get_matched_folder_templates("civil")
        assert "查询失败" in result

    def test_get_case_file_sub_type_choices(self) -> None:
        service, _, _ = self._make_service()
        result = service.get_case_file_sub_type_choices()
        # Should return list of tuples
        assert isinstance(result, list)

    def test_get_case_file_sub_type_choices_exception(self) -> None:
        service, _, _ = self._make_service()
        with patch("apps.cases.services.case.case_admin_service.import_module") as mock_import:
            mock_import.side_effect = ImportError("no module")
            result = service.get_case_file_sub_type_choices()
            assert result == []


# ── Case Chat Service ───────────────────────────────────────────────────────


class TestCaseChatServiceExtended:
    """cases/services/chat/case_chat_service.py extended tests."""

    def _make_service(self) -> Any:
        from apps.cases.services.chat.case_chat_service import CaseChatService

        repo = MagicMock()
        name_builder = MagicMock()
        provider_facade = MagicMock()
        recreate_policy = MagicMock()
        access_policy = MagicMock()
        return CaseChatService(
            repo=repo,
            name_builder=name_builder,
            provider_facade=provider_facade,
            recreate_policy=recreate_policy,
            access_policy=access_policy,
        ), repo, name_builder, provider_facade, recreate_policy, access_policy

    def test_resolve_access_from_params(self) -> None:
        service, *_ = self._make_service()
        user, org, perm = service._resolve_access(
            user="u1", org_access="o1", perm_open_access=False, ctx=None
        )
        assert user == "u1"
        assert org == "o1"
        assert perm is False

    def test_resolve_access_from_ctx(self) -> None:
        service, *_ = self._make_service()
        ctx = MagicMock()
        ctx.user = "ctx_user"
        ctx.org_access = "ctx_org"
        ctx.perm_open_access = True
        user, org, perm = service._resolve_access(
            user=None, org_access=None, perm_open_access=False, ctx=ctx
        )
        assert user == "ctx_user"
        assert org == "ctx_org"
        assert perm is True

    def test_access_policy_property(self) -> None:
        service, *_ = self._make_service()
        assert service.access_policy is not None


# ── Contract Admin Service ─────────────────────────────────────────────────


class TestContractAdminServiceExtended:
    """contracts/services/contract/admin/contract_admin_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_service import ContractAdminService

        assert ContractAdminService is not None

    def test_init(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_service import ContractAdminService

        svc = ContractAdminService()
        assert svc is not None


# ── Contract OA Sync Service ────────────────────────────────────────────────


class TestContractOASyncService:
    """contracts/services/contract/integrations/contract_oa_sync_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService

        assert ContractOASyncService is not None


# ── Archive Classifier ─────────────────────────────────────────────────────


class TestArchiveClassifier:
    """contracts/services/contract/integrations/archive_classifier.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.integrations.archive_classifier import classify_archive_material

        assert callable(classify_archive_material)


# ── Contract Payment Service ────────────────────────────────────────────────


class TestContractPaymentService:
    """contracts/services/payment/contract_payment_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.payment.contract_payment_service import ContractPaymentService

        assert ContractPaymentService is not None


# ── Supplementary Agreement Service ─────────────────────────────────────────


class TestSupplementaryAgreementService:
    """contracts/services/supplementary/supplementary_agreement_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.supplementary.supplementary_agreement_service import SupplementaryAgreementService

        assert SupplementaryAgreementService is not None


# ── Archive Learning Service ───────────────────────────────────────────────


class TestArchiveLearningService:
    """contracts/services/archive/learning_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.archive.learning_service import ArchiveLearningService

        assert ArchiveLearningService is not None

    def test_extract_keywords(self) -> None:
        from apps.contracts.services.archive.learning_service import extract_keywords

        result = extract_keywords("民事起诉状_张三vs李四.pdf")
        assert isinstance(result, list)

    def test_extract_keywords_empty(self) -> None:
        from apps.contracts.services.archive.learning_service import extract_keywords

        result = extract_keywords("")
        assert isinstance(result, list)


# ── Archive Supervision Card Extractor ──────────────────────────────────────


class TestSupervisionCardExtractor:
    """contracts/services/archive/supervision_card_extractor.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.archive.supervision_card_extractor import SupervisionCardExtractor

        assert SupervisionCardExtractor is not None


# ── Batch Folder Binding Service ────────────────────────────────────────────


class TestBatchFolderBindingService:
    """contracts/services/contract/integrations/batch_folder_binding_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.integrations.batch_folder_binding_service import ContractBatchFolderBindingService

        assert ContractBatchFolderBindingService is not None


# ── Quality Card Detector ───────────────────────────────────────────────────


class TestQualityCardDetector:
    """contracts/services/contract/integrations/quality_card_detector.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.integrations import quality_card_detector

        assert hasattr(quality_card_detector, "_QUALITY_CARD_KEYWORD")


# ── Invoice Upload Service ──────────────────────────────────────────────────


class TestInvoiceUploadService:
    """contracts/services/contract/integrations/invoice_upload_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.integrations.invoice_upload_service import InvoiceUploadService

        assert InvoiceUploadService is not None


# ── Client Payment Service ──────────────────────────────────────────────────


class TestClientPaymentService:
    """contracts/services/client_payment/client_payment_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.client_payment.client_payment_service import ClientPaymentRecordService

        assert ClientPaymentRecordService is not None


# ── Client Payment Image Service ────────────────────────────────────────────


class TestClientPaymentImageService:
    """contracts/services/client_payment/client_payment_image_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.client_payment.client_payment_image_service import ClientPaymentImageService

        assert ClientPaymentImageService is not None


# ── Contract Party Service ──────────────────────────────────────────────────


class TestContractPartyService:
    """contracts/services/party/contract_party_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.party.contract_party_service import ContractPartyService

        assert ContractPartyService is not None


# ── Contract Mutation Service ───────────────────────────────────────────────


class TestContractMutationService:
    """contracts/services/contract/mutation/service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.mutation.service import ContractMutationService

        assert ContractMutationService is not None


# ── Contract Query Service ──────────────────────────────────────────────────


class TestContractQueryService:
    """contracts/services/contract/query/service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.query.service import ContractQueryService

        assert ContractQueryService is not None


# ── Lawyer Assignment Service ───────────────────────────────────────────────


class TestLawyerAssignmentService:
    """contracts/services/assignment/lawyer_assignment_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.assignment.lawyer_assignment_service import LawyerAssignmentService

        assert LawyerAssignmentService is not None


# ── Filing Number Service ───────────────────────────────────────────────────


class TestFilingNumberService:
    """contracts/services/assignment/filing_number_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.assignment.filing_number_service import FilingNumberService

        assert FilingNumberService is not None


# ── Contract Import Service ─────────────────────────────────────────────────


class TestContractImportService:
    """contracts/services/contract_import_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract_import_service import ContractImportService

        assert ContractImportService is not None


# ── Folder Binding Service ──────────────────────────────────────────────────


class TestContractFolderBindingService:
    """contracts/services/folder/folder_binding_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.folder.folder_binding_service import FolderBindingService

        assert FolderBindingService is not None


# ── Template Cache ──────────────────────────────────────────────────────────


class TestContractTemplateCache:
    """contracts/services/contract/query/template_cache.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.query.template_cache import ContractTemplateCache

        assert ContractTemplateCache is not None


# ── Progress Service ────────────────────────────────────────────────────────


class TestProgressService:
    """contracts/services/contract/query/progress_service.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.query.progress_service import ContractProgressService

        assert ContractProgressService is not None


# ── Contract Details Assembler ──────────────────────────────────────────────


class TestContractDetailsAssembler:
    """contracts/services/contract/assemblers/contract_details_assembler.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.assemblers.contract_details_assembler import ContractDetailsAssembler

        assert ContractDetailsAssembler is not None


# ── Contract DTO Assembler ──────────────────────────────────────────────────


class TestContractDTOAssembler:
    """contracts/services/contract/assemblers/contract_dto_assembler.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.assemblers.contract_dto_assembler import ContractDtoAssembler

        assert ContractDtoAssembler is not None


# ── Contract List Assembler ─────────────────────────────────────────────────


class TestContractListAssembler:
    """contracts/services/contract/assemblers/contract_list_assembler.py tests."""

    def test_module_importable(self) -> None:
        from apps.contracts.services.contract.assemblers.contract_list_assembler import ContractListAssembler

        assert ContractListAssembler is not None
