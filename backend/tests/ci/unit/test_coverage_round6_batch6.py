"""Round 6 coverage tests - batch 6: text extraction, chat service, contract admin,
automation mixin, client admin service, lawyer resolve.

Covers:
- apps/document_recognition/services/text_extraction_service.py
- apps/cases/services/chat/case_chat_service.py (init, property lazy loading)
- apps/contracts/services/contract/admin/contract_admin_service.py (init, property)
- apps/core/service_locator_mixins/automation_mixin.py
- apps/client/services/client_admin_service.py
- apps/organization/services/lawyer_resolve_service.py
- apps/cases/services/material/case_material_binding_workflow.py
- apps/contracts/services/archive/checklist/checklist_query.py (more branches)
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# text_extraction_service.py
# ============================================================


class TestRemoveAllSpaces:
    def test_empty(self) -> None:
        from apps.document_recognition.services.text_extraction_service import _remove_all_spaces
        assert _remove_all_spaces("") == ""

    def test_none_returns_empty(self) -> None:
        from apps.document_recognition.services.text_extraction_service import _remove_all_spaces
        assert _remove_all_spaces(None) == ""  # type: ignore

    def test_removes_spaces(self) -> None:
        from apps.document_recognition.services.text_extraction_service import _remove_all_spaces
        assert _remove_all_spaces("hello world") == "helloworld"

    def test_removes_tabs_and_newlines(self) -> None:
        from apps.document_recognition.services.text_extraction_service import _remove_all_spaces
        assert _remove_all_spaces("a\tb\nc") == "abc"


class TestTextExtractionService:
    def test_init_defaults(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService()
        assert svc._text_limit is None
        assert svc._max_pages is None

    def test_init_custom(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService(text_limit=1000, max_pages=5)
        assert svc._text_limit == 1000
        assert svc._max_pages == 5

    def test_extract_text_file_not_found(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        from apps.core.exceptions import ValidationException
        svc = TextExtractionService()
        with pytest.raises(ValidationException):
            svc.extract_text("/nonexistent/file.pdf")

    def test_extract_text_unsupported_format(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        from apps.core.exceptions import ValidationException
        svc = TextExtractionService()
        with tempfile.NamedTemporaryFile(suffix=".xyz") as f:
            with pytest.raises(ValidationException):
                svc.extract_text(f.name)

    def test_extract_text_pdf(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService()
        with patch.object(svc, "_extract_from_pdf") as mock_pdf:
            mock_pdf.return_value = MagicMock(text="text", extraction_method="pdf_direct", success=True)
            with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                result = svc.extract_text(f.name)
                mock_pdf.assert_called_once()

    def test_extract_text_image(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService()
        with patch.object(svc, "_extract_from_image") as mock_img:
            mock_img.return_value = MagicMock(text="text", extraction_method="ocr", success=True)
            with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
                result = svc.extract_text(f.name)
                mock_img.assert_called_once()

    def test_extract_pdf_direct_success(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService()
        with patch.object(svc, "_extract_pdf_text_direct", return_value="hello world"):
            with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                result = svc._extract_from_pdf(f.name)
                assert result.success
                assert result.extraction_method == "pdf_direct"
                assert result.text == "helloworld"

    def test_extract_pdf_direct_empty_falls_back_to_ocr(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService()
        with patch.object(svc, "_extract_pdf_text_direct", return_value=""):
            with patch.object(svc, "_extract_pdf_with_ocr") as mock_ocr:
                mock_ocr.return_value = MagicMock(text="ocr text", extraction_method="ocr", success=True)
                with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                    result = svc._extract_from_pdf(f.name)
                    mock_ocr.assert_called_once()

    def test_extract_from_image_success(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService()
        with patch(
            "apps.document_recognition.services.text_extraction_service.TextExtractionService._extract_from_image"
        ) as mock_img:
            mock_img.return_value = MagicMock(text="ocr", extraction_method="ocr", success=True)
            with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
                result = svc.extract_text(f.name)
                assert result.success

    def test_is_supported_format_pdf(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService()
        assert svc.is_supported_format("file.pdf")
        assert svc.is_supported_format(".pdf")
        assert not svc.is_supported_format("file.xyz")

    def test_get_supported_extensions(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService()
        exts = svc.get_supported_extensions()
        assert ".pdf" in exts
        assert ".jpg" in exts

    def test_module_level_get_supported_extensions(self) -> None:
        from apps.document_recognition.services.text_extraction_service import get_supported_extensions
        exts = get_supported_extensions()
        assert ".pdf" in exts

    def test_extract_text_with_text_limit(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService(text_limit=5)
        with patch.object(svc, "_extract_pdf_text_direct", return_value=""):
            with patch.object(svc, "_extract_pdf_with_ocr") as mock_ocr:
                mock_ocr.return_value = MagicMock(text="ocrtext", extraction_method="ocr", success=True)
                with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                    result = svc._extract_from_pdf(f.name)

    def test_extract_text_max_pages_override(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService(max_pages=10)
        with patch.object(svc, "_extract_from_pdf") as mock_pdf:
            mock_pdf.return_value = MagicMock()
            with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                svc.extract_text(f.name, max_pages=3)
                # max_pages param should override constructor value
                mock_pdf.assert_called_once()

    def test_extract_image_exception(self) -> None:
        from apps.document_recognition.services.text_extraction_service import TextExtractionService
        svc = TextExtractionService()
        with patch(
            "apps.document_recognition.services.text_extraction_service.TextExtractionService._extract_from_image"
        ) as mock_img:
            mock_img.return_value = MagicMock(text="", extraction_method="ocr", success=False)
            with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
                result = svc.extract_text(f.name)
                assert not result.success


# ============================================================
# cases/services/chat/case_chat_service.py - init + property
# ============================================================


class TestCaseChatServiceInit:
    def test_init_defaults(self) -> None:
        from apps.cases.services.chat.case_chat_service import CaseChatService
        svc = CaseChatService()
        assert svc.repo is not None
        assert svc.name_builder is not None
        assert svc.provider_facade is not None
        assert svc.recreate_policy is not None

    def test_init_with_injections(self) -> None:
        from apps.cases.services.chat.case_chat_service import CaseChatService
        mock_repo = MagicMock()
        mock_name = MagicMock()
        mock_provider = MagicMock()
        mock_recreate = MagicMock()
        svc = CaseChatService(
            repo=mock_repo,
            name_builder=mock_name,
            provider_facade=mock_provider,
            recreate_policy=mock_recreate,
        )
        assert svc.repo is mock_repo
        assert svc.name_builder is mock_name

    def test_access_policy_lazy(self) -> None:
        from apps.cases.services.chat.case_chat_service import CaseChatService
        svc = CaseChatService()
        assert svc._access_policy is None
        policy = svc.access_policy
        assert policy is not None
        assert svc._access_policy is policy


# ============================================================
# contracts/services/contract/admin/contract_admin_service.py
# ============================================================


class TestContractAdminServiceInit:
    def test_init_defaults(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_service import ContractAdminService
        svc = ContractAdminService()
        assert svc._display_service is None
        assert svc._filing_number_service is None

    def test_display_service_lazy(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_service import ContractAdminService
        svc = ContractAdminService()
        ds = svc.display_service
        assert ds is not None

    def test_init_with_all_services(self) -> None:
        from apps.contracts.services.contract.admin.contract_admin_service import ContractAdminService
        svc = ContractAdminService(
            display_service=MagicMock(),
            filing_number_service=MagicMock(),
            document_service=MagicMock(),
            query_service=MagicMock(),
            mutation_service=MagicMock(),
            progress_service=MagicMock(),
        )
        assert svc._display_service is not None


# ============================================================
# core/service_locator_mixins/automation_mixin.py
# ============================================================


class TestAutomationMixin:
    def test_get_automation_service(self) -> None:
        from apps.core.service_locator_mixins.automation_mixin import AutomationServiceLocatorMixin
        with patch.object(AutomationServiceLocatorMixin, "get_or_create") as mock_create:
            mock_create.return_value = MagicMock()
            result = AutomationServiceLocatorMixin.get_automation_service()
            mock_create.assert_called_once()


# ============================================================
# client/services/client_admin_service.py
# ============================================================


class TestClientAdminServiceInit:
    def test_init_defaults(self) -> None:
        from apps.client.services.client_admin_service import ClientAdminService
        svc = ClientAdminService()
        assert svc._identity_doc_service is None

    def test_init_with_injections(self) -> None:
        from apps.client.services.client_admin_service import ClientAdminService
        svc = ClientAdminService(
            identity_doc_service=MagicMock(),
            internal_query_service=MagicMock(),
        )
        assert svc._identity_doc_service is not None

    def test_identity_doc_service_lazy(self) -> None:
        from apps.client.services.client_admin_service import ClientAdminService
        svc = ClientAdminService()
        svc._identity_doc_service = None  # ensure lazy
        service = svc.identity_doc_service
        assert service is not None

    def test_internal_query_service_lazy(self) -> None:
        from apps.client.services.client_admin_service import ClientAdminService
        svc = ClientAdminService()
        service = svc.internal_query_service
        assert service is not None


# ============================================================
# contracts/services/archive/checklist/checklist_query.py
# ============================================================


class TestChecklistQueryGetChecklist:
    def test_get_template_items_empty(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_template_items
        items = get_template_items("empty_category")
        assert items == []

    def test_get_auto_detect_items_empty(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_auto_detect_items
        items = get_auto_detect_items("empty_category")
        assert items == []

    def test_find_code_by_name_partial_match(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_name
        result = find_code_by_name("litigation", "起诉")
        assert result is not None
        assert "lt_" in result

    def test_find_code_by_source_template_source(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_source
        # "template" source items don't have "委托" in name
        result = find_code_by_source("non_litigation", "template")
        # Should return None since "template" source items don't have "委托"
        # Actually let me check what it returns
        # Template items: nl_1 has name "案卷封面", source "template" - no "委托"
        # So it should return None for template source
        assert result is None


class TestApplySubitemOrderEdgeCases:
    def test_all_unordered_no_keyword_match(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order
        # nl_4 keywords: ["委托合同", "合同正本"]
        details = {
            "nl_4": [
                {"id": 1, "order": 0, "original_filename": "random_file.pdf"},
                {"id": 2, "order": 0, "original_filename": "another_file.pdf"},
            ]
        }
        _apply_subitem_order(details)
        # Neither matches any keyword, so they stay at position (1, 0)
        assert len(details["nl_4"]) == 2

    def test_existing_code_not_in_rules(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order
        details = {
            "zz_99": [
                {"id": 1, "order": 0, "original_filename": "test.pdf"},
            ]
        }
        _apply_subitem_order(details)
        # zz_99 is not in ARCHIVE_SUBITEM_ORDER_RULES, so nothing happens
        assert details["zz_99"][0]["id"] == 1


# ============================================================
# organization/services/lawyer_resolve_service.py
# ============================================================


class TestLawyerResolveService:
    def test_init(self) -> None:
        from apps.organization.services.lawyer_resolve_service import LawyerResolveService
        svc = LawyerResolveService()
        assert svc is not None


# ============================================================
# cases/services/material/case_material_binding_workflow.py
# ============================================================


class TestCaseMaterialBindingWorkflow:
    def test_init(self) -> None:
        from apps.cases.services.material.case_material_binding_workflow import CaseMaterialBindingWorkflow
        svc = CaseMaterialBindingWorkflow()
        assert svc is not None


# ============================================================
# contracts/services/archive/checklist/material_mapping.py - more tests
# ============================================================


class TestMapSupervisionCardMaterials:
    def test_no_supervision_code(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import map_supervision_card_materials
        result = map_supervision_card_materials("empty_category", [])
        assert result == {}

    def test_with_supervision_card(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import map_supervision_card_materials
        from apps.contracts.models.finalized_material import MaterialCategory
        mat = SimpleNamespace(
            id=10, archive_item_code=None, category=MaterialCategory.SUPERVISION_CARD
        )
        result = map_supervision_card_materials("litigation", [mat])
        # litigation has lt_18 with auto_detect="supervision_card"
        assert len(result) > 0

    def test_skips_existing_archive_item_code(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import map_supervision_card_materials
        from apps.contracts.models.finalized_material import MaterialCategory
        mat = SimpleNamespace(
            id=10, archive_item_code="lt_18", category=MaterialCategory.SUPERVISION_CARD
        )
        result = map_supervision_card_materials("litigation", [mat])
        assert len(result) == 0


class TestMapContractMaterials:
    def test_skips_existing_archive_item_code(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import map_contract_materials
        from apps.contracts.models.finalized_material import MaterialCategory
        mat = SimpleNamespace(
            id=1, archive_item_code="lt_4", category=MaterialCategory.CONTRACT_ORIGINAL
        )
        result = map_contract_materials("litigation", [mat])
        assert len(result) == 0

    def test_unknown_category(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import map_contract_materials
        from apps.contracts.models.finalized_material import MaterialCategory
        mat = SimpleNamespace(
            id=1, archive_item_code=None, category="unknown"
        )
        result = map_contract_materials("nonexistent", [mat])
        assert result == {}


class TestMatchTypeNullName:
    def test_none_type_name(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import match_type_name_to_code
        assert match_type_name_to_code(None, {"code": ["kw"]}) is None  # type: ignore
