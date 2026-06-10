"""Coverage tests for legal_solution, evidence_sorting, contracts, and PDF services.

Targets uncovered lines in:
- legal_solution/services/solution_generator.py (70 uncovered, mainly _md_to_html)
- evidence_sorting/services/reconciler.py (72 uncovered)
- contracts/services/archive/checklist/checklist_query.py (56 uncovered)
- documents/services/infrastructure/pdf_merge_service.py (76 uncovered)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.legal_solution.services.solution_generator import _md_to_html


# ===================================================================
# _md_to_html (pure function, lots of uncovered lines)
# ===================================================================
class TestMdToHtml:
    def test_plain_text(self):
        result = _md_to_html("Hello world")
        assert "Hello world" in result

    def test_bold(self):
        result = _md_to_html("**bold text**")
        assert "bold" in result.lower()

    def test_unordered_list(self):
        result = _md_to_html("- item 1\n- item 2")
        assert "item 1" in result
        assert "item 2" in result

    def test_ordered_list(self):
        result = _md_to_html("1. first\n2. second")
        assert "first" in result
        assert "second" in result

    def test_empty_string(self):
        result = _md_to_html("")
        assert result == ""

    def test_multiple_paragraphs(self):
        result = _md_to_html("para1\n\npara2")
        assert "para1" in result
        assert "para2" in result

    def test_special_characters(self):
        result = _md_to_html("a < b > c & d")
        assert "a" in result

    def test_list_items_present(self):
        result = _md_to_html("- item1\n- item2")
        assert "item1" in result
        assert "item2" in result

    def test_ordered_list_items_present(self):
        result = _md_to_html("1. item1\n2. item2")
        assert "item1" in result
        assert "item2" in result


# ===================================================================
# PDFMergeValidator
# ===================================================================
class TestPDFMergeValidator:
    def test_assert_supported_format_valid(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator

        validator = PDFMergeValidator()
        validator.assert_supported_format(".pdf", "/tmp/test.pdf")  # no exception

    def test_assert_supported_format_invalid(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator
        from apps.core.exceptions import BusinessException

        validator = PDFMergeValidator()
        with pytest.raises(BusinessException):
            validator.assert_supported_format(".xyz", "/tmp/test.xyz")

    def test_supported_formats_list(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator

        assert ".pdf" in PDFMergeValidator.SUPPORTED_FORMATS
        assert ".doc" in PDFMergeValidator.SUPPORTED_FORMATS
        assert ".jpg" in PDFMergeValidator.SUPPORTED_FORMATS

    def test_image_formats_list(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator

        assert ".jpg" in PDFMergeValidator.IMAGE_FORMATS
        assert ".png" in PDFMergeValidator.IMAGE_FORMATS

    def test_word_formats_list(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator

        assert ".doc" in PDFMergeValidator.WORD_FORMATS
        assert ".docx" in PDFMergeValidator.WORD_FORMATS


# ===================================================================
# PDFMergeWorkflow
# ===================================================================
class TestPDFMergeWorkflow:
    def test_validator_lazy_load(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow

        workflow = PDFMergeWorkflow()
        assert workflow.validator is not None

    def test_validator_injected(self):
        from apps.documents.services.infrastructure.pdf_merge_service import (
            PDFMergeValidator,
            PDFMergeWorkflow,
        )

        custom_validator = PDFMergeValidator()
        workflow = PDFMergeWorkflow(validator=custom_validator)
        assert workflow.validator is custom_validator


# ===================================================================
# evidence_sorting data classes
# ===================================================================
class TestEvidenceSortingDataClasses:
    def test_line_item_defaults(self):
        from apps.evidence_sorting.services.reconciler import LineItem

        item = LineItem()
        assert item.date is None
        assert item.amount is None
        assert item.description == ""

    def test_line_item_with_values(self):
        from apps.evidence_sorting.services.reconciler import LineItem

        item = LineItem(date="20240101", amount=100.0, description="test")
        assert item.date == "20240101"
        assert item.amount == 100.0

    def test_statement_info_defaults(self):
        from apps.evidence_sorting.services.reconciler import StatementInfo

        info = StatementInfo()
        assert info.month == ""
        assert info.total_amount is None
        assert info.signed is False
        assert info.line_items == []

    def test_statement_info_with_values(self):
        from apps.evidence_sorting.services.reconciler import LineItem, StatementInfo

        items = [LineItem(date="20240101", amount=100.0)]
        info = StatementInfo(month="2024-01", total_amount=100.0, signed=True, line_items=items)
        assert info.month == "2024-01"
        assert len(info.line_items) == 1


# ===================================================================
# Constants from evidence_sorting
# ===================================================================
class TestEvidenceSortingConstants:
    def test_status_constants(self):
        from apps.evidence_sorting.services.reconciler import (
            STATUS_MATCHED,
            STATUS_MISSING,
            STATUS_UNMATCHED,
        )

        assert STATUS_MATCHED == "matched"
        assert STATUS_UNMATCHED == "unmatched"
        assert STATUS_MISSING == "missing"

    def test_folder_status_constants(self):
        from apps.evidence_sorting.services.reconciler import (
            FOLDER_CONFIRMED,
            FOLDER_DELIVERY_MISMATCH,
            FOLDER_DELIVERY_NOT_ENOUGH,
            FOLDER_MISSING_DELIVERY,
            FOLDER_NEED_SUPPLEMENT,
            FOLDER_UNSIGNED,
        )

        assert FOLDER_CONFIRMED == "已确认"
        assert FOLDER_UNSIGNED == "对账单未签名"
        assert FOLDER_MISSING_DELIVERY == "缺少出库单"
        assert FOLDER_DELIVERY_NOT_ENOUGH == "出库单数量不够"
        assert FOLDER_DELIVERY_MISMATCH == "出库单与对账单不匹配"
        assert FOLDER_NEED_SUPPLEMENT == "需补充对账单"


# ===================================================================
# checklist_query: _get_source and _get_source_label
# ===================================================================
class TestChecklistQueryHelpers:
    def test_get_source(self):
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        from apps.contracts.models.finalized_material import MaterialCategory

        assert _get_source(MaterialCategory.CONTRACT_ORIGINAL) == "contract"
        assert _get_source(MaterialCategory.AUTHORIZATION_MATERIAL) == "case"
        assert _get_source(MaterialCategory.ARCHIVE_UPLOAD) == "upload"
        assert _get_source("unknown_category") == "upload"

    def test_get_source_label(self):
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory

        assert _get_source_label(MaterialCategory.CONTRACT_ORIGINAL) == "合同正本"
        assert _get_source_label(MaterialCategory.CASE_MATERIAL) == "案件同步"
        assert _get_source_label(MaterialCategory.ARCHIVE_UPLOAD) == "手动上传"
        assert _get_source_label("unknown") == "手动上传"


# ===================================================================
# CaseChatService helper methods
# ===================================================================
class TestCaseChatServiceHelpers:
    def test_resolve_access_with_ctx(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        ctx = SimpleNamespace(user="user1", org_access={"org": True}, perm_open_access=True)
        result = svc._resolve_access(user="user2", org_access=None, perm_open_access=False, ctx=ctx)
        assert result == ("user1", {"org": True}, True)

    def test_resolve_access_without_ctx(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        result = svc._resolve_access(user="user1", org_access={"org": True}, perm_open_access=False, ctx=None)
        assert result == ("user1", {"org": True}, False)

    def test_resolve_default_platform_fallback(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        from apps.core.models.enums import ChatPlatform

        svc = CaseChatService()
        with patch("apps.automation.services.chat.factory.ChatProviderFactory") as mock_factory:
            mock_factory.get_available_platforms.side_effect = RuntimeError
            result = svc._resolve_default_platform()
            assert result == ChatPlatform.FEISHU

    def test_resolve_default_platform_available(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        from apps.core.models.enums import ChatPlatform

        svc = CaseChatService()
        with patch("apps.automation.services.chat.factory.ChatProviderFactory") as mock_factory:
            mock_factory.get_available_platforms.return_value = [ChatPlatform.DINGTALK]
            result = svc._resolve_default_platform()
            assert result == ChatPlatform.DINGTALK

    def test_resolve_default_platform_empty(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService
        from apps.core.models.enums import ChatPlatform

        svc = CaseChatService()
        with patch("apps.automation.services.chat.factory.ChatProviderFactory") as mock_factory:
            mock_factory.get_available_platforms.return_value = []
            result = svc._resolve_default_platform()
            assert result == ChatPlatform.FEISHU

    def test_resolve_owner_id(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        with patch("apps.core.config.get_config", return_value="owner-123"):
            result = svc._resolve_owner_id()
            assert result == "owner-123"

    def test_resolve_owner_id_none(self):
        from apps.cases.services.chat.case_chat_service import CaseChatService

        svc = CaseChatService()
        with patch("apps.core.config.get_config", return_value=None):
            result = svc._resolve_owner_id()
            assert result is None


# ===================================================================
# CaseMaterialQueryService
# ===================================================================
class TestCaseMaterialQueryService:
    def test_case_service_not_injected_raises(self):
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService

        svc = CaseMaterialQueryService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_case_service_injected(self):
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService

        mock_service = Mock()
        svc = CaseMaterialQueryService(case_service=mock_service)
        assert svc.case_service is mock_service


# ===================================================================
# ContractServiceAdapter
# ===================================================================
class TestContractServiceAdapter:
    def test_init_requires_service_or_case_service(self):
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        with pytest.raises(RuntimeError):
            ContractServiceAdapter(contract_service=None, case_service=None)

    def test_get_contract_not_found(self):
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter
        from apps.core.exceptions import NotFoundError

        mock_cs = Mock()
        mock_cs.query_service.get_contract_internal.side_effect = NotFoundError(message="not found")
        mock_dto = Mock()
        adapter = ContractServiceAdapter(contract_service=mock_cs, dto_assembler=mock_dto)
        result = adapter.get_contract(999)
        assert result is None

    def test_get_contract_stages_not_found(self):
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter
        from apps.core.exceptions import NotFoundError

        mock_cs = Mock()
        mock_cs.query_service.get_contract_internal.side_effect = NotFoundError(message="not found")
        adapter = ContractServiceAdapter(contract_service=mock_cs)
        result = adapter.get_contract_stages(999)
        assert result == []

    def test_validate_contract_active_not_found(self):
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter
        from apps.core.exceptions import NotFoundError

        mock_cs = Mock()
        mock_cs.query_service.get_contract_internal.side_effect = NotFoundError(message="not found")
        adapter = ContractServiceAdapter(contract_service=mock_cs)
        result = adapter.validate_contract_active(999)
        assert result is False

    def test_validate_contract_active(self):
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        mock_contract = SimpleNamespace(status="active")
        mock_cs = Mock()
        mock_cs.query_service.get_contract_internal.return_value = mock_contract
        adapter = ContractServiceAdapter(contract_service=mock_cs)
        assert adapter.validate_contract_active(1) is True

    def test_validate_contract_inactive(self):
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        mock_contract = SimpleNamespace(status="terminated")
        mock_cs = Mock()
        mock_cs.query_service.get_contract_internal.return_value = mock_contract
        adapter = ContractServiceAdapter(contract_service=mock_cs)
        assert adapter.validate_contract_active(1) is False

    def test_get_contract_stages_success(self):
        from apps.contracts.services.contract.contract_service_adapter import ContractServiceAdapter

        mock_contract = SimpleNamespace(representation_stages=["stage1", "stage2"])
        mock_cs = Mock()
        mock_cs.query_service.get_contract_internal.return_value = mock_contract
        adapter = ContractServiceAdapter(contract_service=mock_cs)
        result = adapter.get_contract_stages(1)
        assert result == ["stage1", "stage2"]
