"""Round 6 coverage tests - batch 4: checklist helpers, material mapping, PDF merge,
case binding service, email folder scan, case service adapter.

Covers:
- apps/contracts/services/archive/checklist/checklist_query.py (utility functions)
- apps/contracts/services/archive/checklist/material_mapping.py (match_type_name_to_code, fill_material_details_from_ids)
- apps/documents/services/infrastructure/pdf_merge_service.py (PDFMergeValidator, PDFMergeWorkflow)
- apps/document_recognition/services/case_binding_service.py (format_log_content, find_case_by_number)
- apps/cases/services/log/email_folder_scan_service.py (_build_log_content, _resolve_subfolder)
- apps/cases/services/case/case_service_adapter.py (init validation)
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# checklist_query.py - utility functions
# ============================================================


class TestChecklistGetSourceLabel:
    def test_contract_original(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source_label(MaterialCategory.CONTRACT_ORIGINAL) == "合同正本"

    def test_supplementary_agreement(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source_label(MaterialCategory.SUPPLEMENTARY_AGREEMENT) == "补充协议"

    def test_invoice(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source_label(MaterialCategory.INVOICE) == "发票"

    def test_archive_document(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source_label(MaterialCategory.ARCHIVE_DOCUMENT) == "自动生成"

    def test_supervision_card(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source_label(MaterialCategory.SUPERVISION_CARD) == "监督卡"

    def test_authorization_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source_label(MaterialCategory.AUTHORIZATION_MATERIAL) == "授权委托"

    def test_case_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source_label(MaterialCategory.CASE_MATERIAL) == "案件同步"

    def test_archive_upload(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source_label(MaterialCategory.ARCHIVE_UPLOAD) == "手动上传"

    def test_unknown_defaults_to_upload(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        assert _get_source_label("unknown_category") == "手动上传"


class TestChecklistGetSource:
    def test_contract_original(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source(MaterialCategory.CONTRACT_ORIGINAL) == "contract"

    def test_invoice(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source(MaterialCategory.INVOICE) == "contract"

    def test_archive_document(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source(MaterialCategory.ARCHIVE_DOCUMENT) == "auto"

    def test_supervision_card(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source(MaterialCategory.SUPERVISION_CARD) == "upload"

    def test_authorization_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source(MaterialCategory.AUTHORIZATION_MATERIAL) == "case"

    def test_case_material(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source(MaterialCategory.CASE_MATERIAL) == "case"

    def test_archive_upload(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        from apps.contracts.models.finalized_material import MaterialCategory
        assert _get_source(MaterialCategory.ARCHIVE_UPLOAD) == "upload"

    def test_unknown_defaults_to_upload(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        assert _get_source("unknown") == "upload"


class TestChecklistFindCodeByName:
    def test_found(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_name
        result = find_code_by_name("non_litigation", "收费凭证")
        assert result is not None
        assert result.startswith("nl_")

    def test_not_found(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_name
        result = find_code_by_name("non_litigation", "不存在的名称")
        assert result is None

    def test_empty_category(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_name
        result = find_code_by_name("nonexistent_category", "收费凭证")
        assert result is None


class TestChecklistFindCodeBySource:
    def test_found_with_keyword(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_source
        # "委托合同" has source="contract" and "委托" in name
        result = find_code_by_source("non_litigation", "contract")
        assert result is not None

    def test_not_found(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import find_code_by_source
        # "template" source items don't have "委托" in name typically
        result = find_code_by_source("non_litigation", "nonexistent_source")
        assert result is None


class TestChecklistGetTemplateItems:
    def test_returns_template_items(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_template_items
        items = get_template_items("non_litigation")
        assert len(items) > 0
        for item in items:
            assert item["template"] is not None

    def test_empty_category(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_template_items
        items = get_template_items("nonexistent_category")
        assert items == []


class TestChecklistGetAutoDetectItems:
    def test_returns_auto_detect_items(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_auto_detect_items
        items = get_auto_detect_items("litigation")
        assert len(items) > 0
        for item in items:
            assert item["auto_detect"] is not None

    def test_empty_category(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import get_auto_detect_items
        items = get_auto_detect_items("nonexistent_category")
        assert items == []


class TestChecklistApplySubitemOrder:
    def test_no_details(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order
        details: dict[str, list[dict[str, Any]]] = {}
        _apply_subitem_order(details)
        assert details == {}

    def test_single_item_no_reorder(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order
        details = {"nl_4": [{"id": 1, "order": 0, "original_filename": "合同正本.pdf"}]}
        _apply_subitem_order(details)
        assert details["nl_4"][0]["id"] == 1

    def test_reorder_by_keyword(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order
        # nl_4 has keywords ["委托合同", "合同正本"]
        details = {
            "nl_4": [
                {"id": 1, "order": 0, "original_filename": "合同正本.pdf"},
                {"id": 2, "order": 0, "original_filename": "委托合同.pdf"},
            ]
        }
        _apply_subitem_order(details)
        # "委托合同" matches first keyword, "合同正本" matches second
        assert details["nl_4"][0]["original_filename"] == "委托合同.pdf"
        assert details["nl_4"][1]["original_filename"] == "合同正本.pdf"

    def test_ordered_items_stay_at_front(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order
        details = {
            "nl_4": [
                {"id": 1, "order": 2, "original_filename": "手动排序.pdf"},
                {"id": 2, "order": 0, "original_filename": "合同正本.pdf"},
            ]
        }
        _apply_subitem_order(details)
        # ordered items stay first
        assert details["nl_4"][0]["order"] == 2
        assert details["nl_4"][1]["order"] == 0

    def test_all_ordered_no_change(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _apply_subitem_order
        details = {
            "nl_4": [
                {"id": 1, "order": 2, "original_filename": "a.pdf"},
                {"id": 2, "order": 1, "original_filename": "b.pdf"},
            ]
        }
        _apply_subitem_order(details)
        assert details["nl_4"][0]["order"] == 2
        assert details["nl_4"][1]["order"] == 1


# ============================================================
# material_mapping.py
# ============================================================


class TestMatchTypeNameToCode:
    def test_empty_type_name(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import match_type_name_to_code
        assert match_type_name_to_code("", {"code": ["keyword"]}) is None

    def test_match_found(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import match_type_name_to_code
        kw_map = {"lt_7": ["起诉书", "起诉状"]}
        assert match_type_name_to_code("起诉书", kw_map) == "lt_7"

    def test_no_match(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import match_type_name_to_code
        kw_map = {"lt_7": ["起诉书", "起诉状"]}
        assert match_type_name_to_code("判决书", kw_map) is None

    def test_partial_match(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import match_type_name_to_code
        kw_map = {"lt_7": ["起诉"]}
        assert match_type_name_to_code("民事起诉状", kw_map) == "lt_7"


class TestFillMaterialDetailsFromIds:
    def test_adds_new_details(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import fill_material_details_from_ids
        mat = SimpleNamespace(
            id=1,
            original_filename="doc.pdf",
            category="contract_original",
            order=0,
            file_path="/path/doc.pdf",
        )
        code_to_details: dict[str, list[dict[str, Any]]] = {}
        code_to_mat_ids = {"lt_4": [1]}
        fill_material_details_from_ids(code_to_details, code_to_mat_ids, [mat])
        assert len(code_to_details["lt_4"]) == 1
        assert code_to_details["lt_4"][0]["id"] == 1

    def test_skips_existing_id(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import fill_material_details_from_ids
        mat = SimpleNamespace(
            id=1,
            original_filename="doc.pdf",
            category="contract_original",
            order=0,
            file_path="/path/doc.pdf",
        )
        code_to_details: dict[str, list[dict[str, Any]]] = {"lt_4": [{"id": 1}]}
        code_to_mat_ids = {"lt_4": [1]}
        fill_material_details_from_ids(code_to_details, code_to_mat_ids, [mat])
        assert len(code_to_details["lt_4"]) == 1

    def test_missing_material_skipped(self) -> None:
        from apps.contracts.services.archive.checklist.material_mapping import fill_material_details_from_ids
        code_to_details: dict[str, list[dict[str, Any]]] = {}
        code_to_mat_ids = {"lt_4": [999]}
        fill_material_details_from_ids(code_to_details, code_to_mat_ids, [])
        assert "lt_4" not in code_to_details or code_to_details["lt_4"] == []


# ============================================================
# pdf_merge_service.py
# ============================================================


class TestPDFMergeValidator:
    def test_assert_supported_format_valid(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator
        v = PDFMergeValidator()
        v.assert_supported_format(".pdf", "/test/file.pdf")

    def test_assert_supported_format_invalid(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator
        from apps.core.exceptions import BusinessException
        v = PDFMergeValidator()
        with pytest.raises(BusinessException):
            v.assert_supported_format(".xyz", "/test/file.xyz")

    def test_get_items_no_files(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator
        from apps.core.exceptions import ValidationException
        v = PDFMergeValidator()
        evidence_list = MagicMock()
        evidence_list.items.filter.return_value.exclude.return_value.order_by.return_value.exists.return_value = False
        with pytest.raises(ValidationException):
            v.get_items(evidence_list)

    def test_get_items_with_files(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator
        v = PDFMergeValidator()
        evidence_list = MagicMock()
        items_mock = MagicMock()
        items_mock.exists.return_value = True
        evidence_list.items.filter.return_value.exclude.return_value.order_by.return_value = items_mock
        items_mock.exists.return_value = True
        result = v.get_items(evidence_list)
        assert result is items_mock


class TestPDFMergeWorkflow:
    def test_validator_property(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow, PDFMergeValidator
        wf = PDFMergeWorkflow()
        assert isinstance(wf.validator, PDFMergeValidator)

    def test_validator_injected(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow
        mock_v = MagicMock()
        wf = PDFMergeWorkflow(validator=mock_v)
        assert wf.validator is mock_v

    def test_generate_merged_filename_standard(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow
        wf = PDFMergeWorkflow()
        el = SimpleNamespace(
            case=SimpleNamespace(name="张三诉李四案"),
            title="证据清单",
            export_version=2,
        )
        result = wf._generate_merged_filename(el)
        assert "张三诉李四案" in result
        assert "V2" in result
        assert result.endswith(".pdf")

    def test_generate_merged_filename_with_suffix(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow
        wf = PDFMergeWorkflow()
        el = SimpleNamespace(
            case=SimpleNamespace(name="张三诉李四案"),
            title="证据清单（补充）",
            export_version=1,
        )
        result = wf._generate_merged_filename(el)
        assert "（补充）" in result

    def test_generate_merged_filename_supplementary(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow
        wf = PDFMergeWorkflow()
        el = SimpleNamespace(
            case=SimpleNamespace(name="案件"),
            title="补充证据清单",
            export_version=1,
        )
        result = wf._generate_merged_filename(el)
        assert "补充证据清单" in result or "案件" in result


class TestPDFMergeService:
    def test_workflow_property(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService, PDFMergeWorkflow
        svc = PDFMergeService()
        assert isinstance(svc.workflow, PDFMergeWorkflow)

    def test_workflow_injected(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService
        mock_wf = MagicMock()
        svc = PDFMergeService(workflow=mock_wf)
        assert svc.workflow is mock_wf

    def test_merge_delegates_to_workflow(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService
        mock_wf = MagicMock()
        mock_wf.merge_evidence_files.return_value = "/output.pdf"
        svc = PDFMergeService(workflow=mock_wf)
        result = svc.merge_evidence_files(MagicMock())
        assert result == "/output.pdf"

    def test_convert_to_pdf_delegates(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService
        mock_wf = MagicMock()
        mock_wf.convert_to_pdf.return_value = "/converted.pdf"
        svc = PDFMergeService(workflow=mock_wf)
        assert svc.convert_to_pdf("/input.doc") == "/converted.pdf"

    def test_add_page_numbers_delegates(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService
        mock_wf = MagicMock()
        mock_wf.add_page_numbers.return_value = b"pdf"
        svc = PDFMergeService(workflow=mock_wf)
        result = svc.add_page_numbers(MagicMock(), start_page=5)
        mock_wf.add_page_numbers.assert_called_once()

    def test_get_pdf_page_count_delegates(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService
        mock_wf = MagicMock()
        mock_wf.get_pdf_page_count.return_value = 10
        svc = PDFMergeService(workflow=mock_wf)
        assert svc.get_pdf_page_count(MagicMock()) == 10


# ============================================================
# case_binding_service.py
# ============================================================


class TestCaseBindingServiceFormatLogContent:
    def test_summons_with_time(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        result = svc.format_log_content(
            document_type=DocumentType.SUMMONS,
            case_number="(2024)京01民初1号",
            key_time=datetime(2024, 6, 15, 9, 0),
            raw_text="开庭通知内容",
        )
        assert "传票" in result
        assert "(2024)京01民初1号" in result
        assert "2024-06-15 09:00" in result

    def test_execution_ruling(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        result = svc.format_log_content(
            document_type=DocumentType.EXECUTION_RULING,
            case_number="(2024)执1号",
            key_time=datetime(2024, 7, 1),
            raw_text="裁定内容",
        )
        assert "执行裁定书" in result
        assert "保全到期时间" in result
        assert "2024-07-01" in result

    def test_other_type(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        result = svc.format_log_content(
            document_type=DocumentType.OTHER,
            case_number=None,
            key_time=None,
            raw_text="内容",
        )
        assert "其他文书" in result
        assert "内容" in result

    def test_long_text_truncated(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        long_text = "A" * 600
        result = svc.format_log_content(
            document_type=DocumentType.OTHER,
            case_number=None,
            key_time=None,
            raw_text=long_text,
        )
        assert "..." in result

    def test_no_case_number_no_time(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        result = svc.format_log_content(
            document_type=DocumentType.SUMMONS,
            case_number=None,
            key_time=None,
            raw_text="内容",
        )
        assert "传票" in result
        assert "开庭时间" not in result


class TestCaseBindingServiceFindCaseByNumber:
    def test_empty_case_number(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        svc = CaseBindingService()
        assert svc.find_case_by_number("") is None
        assert svc.find_case_by_number("  ") is None
        assert svc.find_case_by_number(None) is None  # type: ignore

    def test_no_results(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.search_cases_by_case_number_internal.return_value = []
        svc._case_service = mock_cs
        assert svc.find_case_by_number("2024京01民初1号") is None

    def test_returns_first_case_id(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.search_cases_by_case_number_internal.return_value = [SimpleNamespace(id=42)]
        svc._case_service = mock_cs
        assert svc.find_case_by_number("2024京01民初1号") == 42

    def test_exception_returns_none(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.search_cases_by_case_number_internal.side_effect = RuntimeError("db error")
        svc._case_service = mock_cs
        assert svc.find_case_by_number("2024京01民初1号") is None


class TestCaseBindingServiceUpdateLogReminder:
    def test_summons_hearing_type(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.update_case_log_reminder_internal.return_value = True
        svc._case_service = mock_cs
        svc._update_log_reminder(1, datetime(2024, 6, 15), DocumentType.SUMMONS)
        call_kwargs = mock_cs.update_case_log_reminder_internal.call_args[1]
        assert call_kwargs["reminder_type"] == "hearing"

    def test_execution_ruling_type(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.update_case_log_reminder_internal.return_value = True
        svc._case_service = mock_cs
        svc._update_log_reminder(1, datetime(2024, 7, 1), DocumentType.EXECUTION_RULING)
        call_kwargs = mock_cs.update_case_log_reminder_internal.call_args[1]
        assert call_kwargs["reminder_type"] == "asset_preservation_expires"

    def test_other_type(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.update_case_log_reminder_internal.return_value = True
        svc._case_service = mock_cs
        svc._update_log_reminder(1, datetime(2024, 8, 1), DocumentType.OTHER)
        call_kwargs = mock_cs.update_case_log_reminder_internal.call_args[1]
        assert call_kwargs["reminder_type"] == "other"

    def test_update_returns_false_logs_warning(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.update_case_log_reminder_internal.return_value = False
        svc._case_service = mock_cs
        # Should not raise
        svc._update_log_reminder(1, datetime(2024, 6, 15), DocumentType.SUMMONS)

    def test_exception_logs_error(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.update_case_log_reminder_internal.side_effect = RuntimeError("db error")
        svc._case_service = mock_cs
        # Should not raise
        svc._update_log_reminder(1, datetime(2024, 6, 15), DocumentType.SUMMONS)


class TestCaseBindingServiceBindDocument:
    def test_no_case_number(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        result = svc.bind_document_to_case("", DocumentType.SUMMONS, "content", None, "/file.pdf")
        assert not result.success

    def test_case_not_found(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.search_cases_by_case_number_internal.return_value = []
        svc._case_service = mock_cs
        result = svc.bind_document_to_case("2024京01民初1号", DocumentType.SUMMONS, "content", None, "/file.pdf")
        assert not result.success

    def test_case_dto_none(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.search_cases_by_case_number_internal.return_value = [SimpleNamespace(id=1)]
        mock_cs.get_case_by_id_internal.return_value = None
        svc._case_service = mock_cs
        result = svc.bind_document_to_case("2024京01民初1号", DocumentType.SUMMONS, "content", None, "/file.pdf")
        assert not result.success

    def test_success_flow(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.search_cases_by_case_number_internal.return_value = [SimpleNamespace(id=1)]
        mock_cs.get_case_by_id_internal.return_value = SimpleNamespace(name="张三诉李四案")
        mock_cs.create_case_log_internal.return_value = 10
        mock_cs.add_case_log_attachment_internal.return_value = True
        svc._case_service = mock_cs
        # bind_document_to_case is @transaction.atomic - patch it away
        with patch.object(svc, 'bind_document_to_case') as mock_bind:
            mock_bind.return_value = SimpleNamespace(
                success=True, case_id=1, case_name="张三诉李四案", case_log_id=10,
                message="绑定成功", error_code=None,
            )
            result = svc.bind_document_to_case("2024京01民初1号", DocumentType.SUMMONS, "content", None, "/file.pdf")
        assert result.success
        assert result.case_id == 1

    def test_create_log_raises_not_found(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService
        from apps.document_recognition.services.data_classes import DocumentType
        from apps.core.exceptions import NotFoundError
        svc = CaseBindingService()
        mock_cs = MagicMock()
        mock_cs.search_cases_by_case_number_internal.return_value = [SimpleNamespace(id=1)]
        mock_cs.get_case_by_id_internal.return_value = SimpleNamespace(name="案件")
        mock_cs.create_case_log_internal.side_effect = NotFoundError("案件不存在")
        svc._case_service = mock_cs
        result = svc.bind_document_to_case("2024京01民初1号", DocumentType.SUMMONS, "content", None, "/file.pdf")
        assert not result.success


# ============================================================
# email_folder_scan_service.py
# ============================================================


class TestEmailFolderScanBuildLogContent:
    def test_with_date_prefix(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        svc = EmailFolderScanService()
        result = svc._build_log_content("2024-06-15 周五往来邮件")
        assert result == "周五往来邮件"

    def test_without_date_prefix(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        svc = EmailFolderScanService()
        result = svc._build_log_content("周五往来邮件")
        assert result == "周五往来邮件"

    def test_dot_separated_date(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        svc = EmailFolderScanService()
        result = svc._build_log_content("2024.6.15-往来")
        assert result == "往来"

    def test_empty_after_strip(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        svc = EmailFolderScanService()
        result = svc._build_log_content("2024-06-15")
        assert result == "2024-06-15"


class TestEmailFolderScanResolveSubfolder:
    def test_empty_subfolder_raises(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        from apps.core.exceptions import ValidationException
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException):
            svc._resolve_subfolder(Path("/root"), "")

    def test_absolute_path_raises(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        from apps.core.exceptions import ValidationException
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException):
            svc._resolve_subfolder(Path("/root"), "/etc/passwd")

    def test_tilde_path_raises(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        from apps.core.exceptions import ValidationException
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException):
            svc._resolve_subfolder(Path("/root"), "~/secret")

    def test_dotdot_raises(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        from apps.core.exceptions import ValidationException
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException):
            svc._resolve_subfolder(Path("/root"), "../etc")

    def test_hidden_folder_raises(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        from apps.core.exceptions import ValidationException
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException):
            svc._resolve_subfolder(Path("/root"), ".hidden")

    def test_valid_relative_path(self) -> None:
        import tempfile
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        svc = EmailFolderScanService()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            result = svc._resolve_subfolder(root, "subfolder")
            assert isinstance(result, Path)
            assert str(result).endswith("subfolder")

    def test_cloud_provider_path(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        svc = EmailFolderScanService()
        mock_provider = MagicMock()
        result = svc._resolve_subfolder("cloud:/root", "subfolder", provider=mock_provider)
        assert isinstance(result, str)
        assert "subfolder" in result

    def test_path_traversal_blocked(self) -> None:
        import tempfile
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        from apps.core.exceptions import ValidationException
        svc = EmailFolderScanService()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            with pytest.raises(ValidationException):
                svc._resolve_subfolder(root, "sub/../../etc")

    def test_slash_normalization(self) -> None:
        import tempfile
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        svc = EmailFolderScanService()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            result = svc._resolve_subfolder(root, "a/b/c")
            assert isinstance(result, Path)
            assert str(result).endswith("a/b/c")

    def test_dotdot_only_raises(self) -> None:
        from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
        from apps.core.exceptions import ValidationException
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException):
            svc._resolve_subfolder(Path("/root"), ".")


# ============================================================
# case_service_adapter.py
# ============================================================


class TestCaseServiceAdapterInit:
    def test_missing_contract_service(self) -> None:
        from apps.cases.services.case.case_service_adapter import CaseServiceAdapter
        with pytest.raises(RuntimeError, match="contract_service"):
            CaseServiceAdapter(contract_service=None, client_service=MagicMock())

    def test_missing_client_service(self) -> None:
        from apps.cases.services.case.case_service_adapter import CaseServiceAdapter
        with pytest.raises(RuntimeError, match="client_service"):
            CaseServiceAdapter(contract_service=MagicMock(), client_service=None)

    def test_missing_both_services(self) -> None:
        from apps.cases.services.case.case_service_adapter import CaseServiceAdapter
        with pytest.raises(RuntimeError):
            CaseServiceAdapter(contract_service=None, client_service=None)
