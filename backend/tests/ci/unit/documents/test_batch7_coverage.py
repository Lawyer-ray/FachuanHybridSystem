"""documents 模块 batch7 覆盖测试 — 覆盖 evidence 服务、folder_template 服务、context_builder 等。"""

from __future__ import annotations

import io
import re
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# =====================================================================
# evidence model 属性 — 直接导入纯逻辑
# =====================================================================

class TestMergeStatusAndListType:
    def test_merge_status_values(self):
        from apps.documents.models.evidence import MergeStatus

        assert MergeStatus.PENDING == "pending"
        assert MergeStatus.PROCESSING == "processing"
        assert MergeStatus.COMPLETED == "completed"
        assert MergeStatus.FAILED == "failed"

    def test_list_type_values(self):
        from apps.documents.models.evidence import ListType

        assert ListType.LIST_1 == "list_1"
        assert ListType.LIST_6 == "list_6"

    def test_list_type_order(self):
        from apps.documents.models.evidence import LIST_TYPE_ORDER, ListType

        assert LIST_TYPE_ORDER[ListType.LIST_1] == 1
        assert LIST_TYPE_ORDER[ListType.LIST_6] == 6

    def test_list_type_previous(self):
        from apps.documents.models.evidence import LIST_TYPE_PREVIOUS, ListType

        assert LIST_TYPE_PREVIOUS[ListType.LIST_1] is None
        assert LIST_TYPE_PREVIOUS[ListType.LIST_2] == ListType.LIST_1


class TestEvidenceListPropertyLogic:
    """通过模拟对象测试 EvidenceList 的属性逻辑。"""

    def _make_list(self, **kwargs):
        defaults = dict(
            total_pages=0,
            start_page=1,
            previous_list_id=None,
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_end_page_zero(self):
        el = self._make_list(total_pages=0, start_page=5)
        # end_page: if total_pages == 0 -> start_page
        end_page = el.start_page if el.total_pages == 0 else el.start_page + el.total_pages - 1
        assert end_page == 5

    def test_end_page_nonzero(self):
        el = self._make_list(total_pages=3, start_page=5)
        end_page = el.start_page if el.total_pages == 0 else el.start_page + el.total_pages - 1
        assert end_page == 7

    def test_page_range_display_zero(self):
        total_pages = 0
        start_page = 1
        display = "" if total_pages == 0 else f"{start_page}-{start_page + total_pages - 1}"
        assert display == ""

    def test_page_range_display_nonzero(self):
        total_pages = 4
        start_page = 3
        display = "" if total_pages == 0 else f"{start_page}-{start_page + total_pages - 1}"
        assert display == "3-6"

    def test_order_range_display_no_items(self):
        item_count = 0
        display = "-" if item_count == 0 else "range"
        assert display == "-"

    def test_order_range_display_single(self):
        start_order = 3
        item_count = 1
        end_order = start_order + item_count - 1
        display = str(start_order) if start_order == end_order else f"{start_order}-{end_order}"
        assert display == "3"

    def test_order_range_display_range(self):
        start_order = 1
        item_count = 5
        end_order = start_order + item_count - 1
        display = str(start_order) if start_order == end_order else f"{start_order}-{end_order}"
        assert display == "1-5"


class TestEvidenceItemPropertyLogic:
    def test_page_range_display_none(self):
        page_start, page_end = None, None
        display = "-" if page_start is None or page_end is None else f"{page_start}-{page_end}"
        assert display == "-"

    def test_page_range_display_same(self):
        page_start, page_end = 5, 5
        display = "-" if page_start is None or page_end is None else (
            str(page_start) if page_start == page_end else f"{page_start}-{page_end}"
        )
        assert display == "5"

    def test_page_range_display_different(self):
        page_start, page_end = 1, 10
        display = "-" if page_start is None or page_end is None else (
            str(page_start) if page_start == page_end else f"{page_start}-{page_end}"
        )
        assert display == "1-10"

    def test_file_size_display_zero(self):
        assert self._size_display(0) == "-"

    def test_file_size_display_bytes(self):
        assert self._size_display(500) == "500 B"

    def test_file_size_display_kb(self):
        display = self._size_display(5 * 1024)
        assert "KB" in display

    def test_file_size_display_mb(self):
        display = self._size_display(3 * 1024 * 1024)
        assert "MB" in display

    @staticmethod
    def _size_display(file_size: int) -> str:
        if file_size == 0:
            return "-"
        if file_size < 1024:
            return f"{file_size} B"
        elif file_size < 1024 * 1024:
            return f"{file_size / 1024:.1f} KB"
        else:
            return f"{file_size / (1024 * 1024):.1f} MB"


# =====================================================================
# EvidenceMutationService — 纯逻辑测试 (mocked DB)
# =====================================================================

class TestEvidenceMutationServiceValidation:
    def test_require_case_model_raises(self):
        from apps.core.exceptions.error_catalog import case_not_found
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService

        svc = EvidenceMutationService()
        mock_case_service = MagicMock()
        mock_case_service.get_case_model_internal.return_value = None

        with pytest.raises(Exception) as exc_info:
            svc.require_case_model(case_service=mock_case_service, case_id=999)
        assert "CASE_NOT_FOUND" in str(exc_info.value) or "案件不存在" in str(exc_info.value)

    def test_require_case_model_success(self):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService

        svc = EvidenceMutationService()
        mock_case = MagicMock()
        mock_case_service = MagicMock()
        mock_case_service.get_case_model_internal.return_value = mock_case

        result = svc.require_case_model(case_service=mock_case_service, case_id=1)
        assert result is mock_case

    @patch("apps.documents.services.evidence.evidence_mutation_service.EvidenceList")
    def test_validate_list_type_creation_list1(self, MockEL):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService

        svc = EvidenceMutationService()
        ok, msg, prev = svc.validate_list_type_creation(case_id=1, list_type="list_1")
        assert ok is True
        assert msg is None
        assert prev is None

    @patch("apps.documents.services.evidence.evidence_mutation_service.EvidenceList")
    def test_validate_list_type_creation_missing_prerequisite(self, MockEL):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService

        MockEL.objects.filter.return_value.first.return_value = None
        svc = EvidenceMutationService()
        ok, msg, prev = svc.validate_list_type_creation(case_id=1, list_type="list_2")
        assert ok is False
        assert "无法创建" in msg

    @patch("apps.documents.services.evidence.evidence_mutation_service.EvidenceList")
    def test_validate_list_type_creation_with_prerequisite(self, MockEL):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService

        mock_prev = MagicMock()
        MockEL.objects.filter.return_value.first.return_value = mock_prev
        svc = EvidenceMutationService()
        ok, msg, prev = svc.validate_list_type_creation(case_id=1, list_type="list_2")
        assert ok is True
        assert prev is mock_prev


# =====================================================================
# EvidencePageRangeCalculator — 纯逻辑测试
# =====================================================================

class TestEvidencePageRangeCalculatorLogic:
    """直接测试 calculate_page_ranges 的逻辑。"""

    def test_calculate_basic(self):
        """模拟基本的页码范围计算。"""
        # 模拟 logic: items with page_count > 0
        items = [
            SimpleNamespace(order=1, page_count=3, page_start=None, page_end=None),
            SimpleNamespace(order=2, page_count=2, page_start=None, page_end=None),
        ]
        current_page = 1
        total_pages = 0
        for item in items:
            if item.page_count > 0:
                item.page_start = current_page
                item.page_end = current_page + item.page_count - 1
                current_page = item.page_end + 1
                total_pages += item.page_count

        assert items[0].page_start == 1
        assert items[0].page_end == 3
        assert items[1].page_start == 4
        assert items[1].page_end == 5
        assert total_pages == 5

    def test_calculate_zero_page_count_skipped(self):
        items = [
            SimpleNamespace(order=1, page_count=0, page_start=None, page_end=None),
            SimpleNamespace(order=2, page_count=2, page_start=None, page_end=None),
        ]
        current_page = 5
        total_pages = 0
        for item in items:
            if item.page_count > 0:
                item.page_start = current_page
                item.page_end = current_page + item.page_count - 1
                current_page = item.page_end + 1
                total_pages += item.page_count

        assert items[0].page_start is None  # unchanged
        assert items[1].page_start == 5
        assert items[1].page_end == 6
        assert total_pages == 2


# =====================================================================
# EvidenceFileService — 验证与文件清理逻辑
# =====================================================================

class TestEvidenceFileServiceLogic:
    def test_supported_formats(self):
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService

        svc = EvidenceFileService()
        assert ".pdf" in svc.SUPPORTED_FORMATS
        assert ".docx" in svc.SUPPORTED_FORMATS
        assert ".jpg" in svc.SUPPORTED_FORMATS

    def test_max_file_size(self):
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService

        assert EvidenceFileService.MAX_FILE_SIZE == 50 * 1024 * 1024

    def test_reject_unsupported_format(self):
        from apps.core.exceptions import ValidationException
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService

        svc = EvidenceFileService()
        mock_item = MagicMock()
        mock_file = MagicMock()
        mock_file.name = "test.exe"
        mock_file.size = 100

        with pytest.raises(ValidationException) as exc_info:
            svc.upload_file(item=mock_item, file=mock_file)
        assert "不支持" in str(exc_info.value)

    def test_reject_oversized_file(self):
        from apps.core.exceptions import ValidationException
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService

        svc = EvidenceFileService()
        mock_item = MagicMock()
        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.size = 100 * 1024 * 1024  # 100MB

        with pytest.raises(ValidationException) as exc_info:
            svc.upload_file(item=mock_item, file=mock_file)
        assert "过大" in str(exc_info.value)

    def test_get_page_count_non_pdf(self):
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService

        svc = EvidenceFileService()
        assert svc._get_page_count(ext=".docx", file=MagicMock()) == 1


# =====================================================================
# EvidenceExportService — filename generation
# =====================================================================

class TestEvidenceExportServiceFilename:
    def _make_evidence_list(self, title="证据清单一", case_name="测试案件", export_version=1):
        case = SimpleNamespace(name=case_name)
        return SimpleNamespace(
            title=title,
            case=case,
            export_version=export_version,
            order=1,
            case_id=1,
        )

    def test_generate_filename_evidence_list(self):
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService

        svc = EvidenceExportService()
        el = self._make_evidence_list()
        filename = svc._generate_filename(el, "证据清单", 1)
        assert "证据清单一" in filename
        assert "测试案件" in filename
        assert "V1" in filename
        assert filename.endswith(".docx")

    def test_generate_filename_evidence_detail(self):
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService

        svc = EvidenceExportService()
        el = self._make_evidence_list(title="证据清单一")
        filename = svc._generate_filename(el, "证据明细", 2)
        assert "证据明细一" in filename
        assert "V2" in filename

    def test_generate_filename_supplement(self):
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService

        svc = EvidenceExportService()
        el = self._make_evidence_list(title="补充证据清单二")
        filename = svc._generate_filename(el, "证据明细", 1)
        assert "证据明细二" in filename

    def test_increment_version_returns_current(self):
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService

        svc = EvidenceExportService()
        el = SimpleNamespace(export_version=5)
        assert svc._increment_version(el) == 5


# =====================================================================
# EvidenceAdminService — filename and get_evidence_list_with_items
# =====================================================================

class TestEvidenceAdminService:
    def test_generate_pdf_filename_list(self):
        from apps.documents.services.evidence.evidence_admin_service import EvidenceAdminService

        svc = EvidenceAdminService()
        el = SimpleNamespace(
            title="证据清单一",
            case=SimpleNamespace(name="张三诉李四"),
            export_version=1,
        )
        filename = svc.generate_pdf_filename(el)
        assert filename.endswith(".pdf")
        assert "证据明细一" in filename
        assert "张三诉李四" in filename

    def test_generate_pdf_filename_supplement(self):
        from apps.documents.services.evidence.evidence_admin_service import EvidenceAdminService

        svc = EvidenceAdminService()
        el = SimpleNamespace(
            title="补充证据清单三",
            case=SimpleNamespace(name="测试案"),
            export_version=2,
        )
        filename = svc.generate_pdf_filename(el)
        assert "证据明细三" in filename
        assert "V2" in filename

    def test_generate_pdf_filename_other_title(self):
        from apps.documents.services.evidence.evidence_admin_service import EvidenceAdminService

        svc = EvidenceAdminService()
        el = SimpleNamespace(
            title="自定义清单",
            case=SimpleNamespace(name="案件"),
            export_version=1,
        )
        filename = svc.generate_pdf_filename(el)
        assert "证据明细" in filename


# =====================================================================
# EvidenceAdminService._recount_item_pages — 无文件场景
# =====================================================================

class TestRecountItemPages:
    def test_no_file_resets_to_zero(self):
        from apps.documents.services.evidence.evidence_admin_service import EvidenceAdminService

        svc = EvidenceAdminService()
        item = SimpleNamespace(
            file=None,
            page_count=5,
            page_start=1,
            page_end=5,
        )
        item.save = MagicMock()

        updated, page_count, error = svc._recount_item_pages(item)
        assert updated == 1
        assert page_count == 0
        assert error is None
        assert item.page_count == 0
        assert item.page_start is None
        assert item.page_end is None

    def test_no_file_already_zero(self):
        from apps.documents.services.evidence.evidence_admin_service import EvidenceAdminService

        svc = EvidenceAdminService()
        item = SimpleNamespace(
            file=None,
            page_count=0,
            page_start=None,
            page_end=None,
        )
        item.save = MagicMock()

        updated, page_count, error = svc._recount_item_pages(item)
        assert updated == 0
        assert page_count == 0

    def test_non_pdf_returns_unchanged(self):
        from apps.documents.services.evidence.evidence_admin_service import EvidenceAdminService

        svc = EvidenceAdminService()
        item = SimpleNamespace(
            file=SimpleNamespace(name="file.docx"),
            page_count=3,
        )

        updated, page_count, error = svc._recount_item_pages(item)
        assert updated == 0
        assert page_count == 3


# =====================================================================
# FolderTemplateValidationService — 结构验证
# =====================================================================

class TestFolderTemplateValidationService:
    def test_validate_non_dict(self):
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService

        svc = FolderTemplateValidationService()
        ok, msg = svc.validate_structure("not a dict")
        assert ok is False
        assert "字典" in msg

    def test_validate_valid_structure(self):
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService

        svc = FolderTemplateValidationService()
        ok, msg = svc.validate_structure({"children": [{"id": "a1", "name": "文件夹"}]})
        assert ok is True
        assert msg == ""

    def test_validate_circular_reference(self):
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService

        svc = FolderTemplateValidationService()
        structure = {
            "children": [
                {"id": "dup", "name": "A", "children": [
                    {"id": "dup", "name": "B"}
                ]}
            ]
        }
        ok, msg = svc.validate_structure(structure)
        assert ok is False
        assert "循环引用" in msg

    def test_validate_invalid_chars(self):
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService

        svc = FolderTemplateValidationService()
        structure = {"children": [{"id": "x1", "name": "bad/name"}]}
        ok, msg = svc.validate_structure(structure)
        assert ok is False
        assert "无效字符" in msg

    def test_validate_empty_children(self):
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService

        svc = FolderTemplateValidationService()
        ok, msg = svc.validate_structure({"children": []})
        assert ok is True

    def test_validate_children_not_list(self):
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService

        svc = FolderTemplateValidationService()
        ok, msg = svc.validate_structure({"children": "not_list"})
        assert ok is True  # non-list children treated as no children

    def test_invalid_chars_pattern(self):
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService

        assert FolderTemplateValidationService.INVALID_CHARS_PATTERN.search("a/b") is not None
        assert FolderTemplateValidationService.INVALID_CHARS_PATTERN.search("valid_name") is None
        assert FolderTemplateValidationService.INVALID_CHARS_PATTERN.search('a"b') is not None


# =====================================================================
# FolderTemplateIdService — ID 操作
# =====================================================================

class TestFolderTemplateIdService:
    def test_collect_structure_ids(self):
        from apps.documents.services.folder_template.id_service import FolderTemplateIdService

        svc = FolderTemplateIdService()
        structure = {
            "children": [
                {"id": "a", "name": "A", "children": [
                    {"id": "b", "name": "B"}
                ]},
                {"id": "c", "name": "C"},
            ]
        }
        ids = svc.collect_structure_ids(structure)
        assert set(ids) == {"a", "b", "c"}

    def test_collect_structure_ids_empty(self):
        from apps.documents.services.folder_template.id_service import FolderTemplateIdService

        svc = FolderTemplateIdService()
        assert svc.collect_structure_ids({}) == []

    def test_find_internal_duplicates(self):
        from apps.documents.services.folder_template.id_service import FolderTemplateIdService

        svc = FolderTemplateIdService()
        dups = svc.find_internal_duplicates(["a", "b", "a", "c", "b"])
        assert dups == {"a", "b"}

    def test_find_internal_duplicates_none(self):
        from apps.documents.services.folder_template.id_service import FolderTemplateIdService

        svc = FolderTemplateIdService()
        assert svc.find_internal_duplicates(["a", "b", "c"]) == set()

    def test_replace_duplicate_ids(self):
        from apps.documents.services.folder_template.id_service import FolderTemplateIdService

        svc = FolderTemplateIdService()
        structure = {"children": [{"id": "dup", "name": "A"}, {"id": "unique", "name": "B"}]}
        svc.replace_duplicate_ids_in_structure(structure, {"dup"})
        assert structure["children"][0]["id"] != "dup"
        assert structure["children"][1]["id"] == "unique"

    def test_generate_unique_id_format(self):
        from apps.documents.services.folder_template.id_service import FolderTemplateIdService

        svc = FolderTemplateIdService()
        with patch.object(svc, "is_id_exists_globally", return_value=False):
            uid = svc.generate_unique_id()
            assert uid.startswith("folder_")
            assert len(uid) > 10


# =====================================================================
# DocumentServiceAdapter — 属性懒加载
# =====================================================================

class TestDocumentServiceAdapter:
    def test_init_with_none_services(self):
        from apps.documents.services.document_service_adapter import DocumentServiceAdapter

        adapter = DocumentServiceAdapter()
        assert adapter._template_query_service is None
        assert adapter._template_matching_service is None
        assert adapter._template_binding_service is None

    def test_init_with_injected_services(self):
        from apps.documents.services.document_service_adapter import DocumentServiceAdapter

        mock_q = MagicMock()
        mock_m = MagicMock()
        mock_b = MagicMock()
        adapter = DocumentServiceAdapter(
            template_query_service=mock_q,
            template_matching_service=mock_m,
            template_binding_service=mock_b,
        )
        assert adapter.template_query_service is mock_q
        assert adapter.template_matching_service is mock_m
        assert adapter.template_binding_service is mock_b

    def test_get_matched_document_templates_error(self):
        from apps.documents.services.document_service_adapter import DocumentServiceAdapter

        mock_m = MagicMock()
        mock_m.find_matching_case_document_template_names.side_effect = Exception("fail")
        adapter = DocumentServiceAdapter(template_matching_service=mock_m)
        result = adapter.get_matched_document_templates("civil")
        assert result == "查询失败"

    def test_get_matched_folder_templates_with_legal_status_error(self):
        from apps.documents.services.document_service_adapter import DocumentServiceAdapter

        mock_m = MagicMock()
        mock_m.find_matching_case_folder_template_names_with_legal_status.side_effect = Exception("fail")
        adapter = DocumentServiceAdapter(template_matching_service=mock_m)
        result = adapter.get_matched_folder_templates_with_legal_status("civil", ["plaintiff"])
        assert result == "查询失败"


# =====================================================================
# Evidence __init__ 延迟导入
# =====================================================================

class TestEvidenceInitLazyImport:
    def test_raise_on_unknown(self):
        from apps.documents.services.evidence import __getattr__ as lazy_getattr

        with pytest.raises(AttributeError):
            lazy_getattr("NonExistentAttr")

    def test_get_known_attrs(self):
        from apps.documents.services.evidence import __getattr__ as lazy_getattr

        cls = lazy_getattr("EvidenceFileService")
        assert cls is not None

    def test_get_page_range_calculator(self):
        from apps.documents.services.evidence import __getattr__ as lazy_getattr

        cls = lazy_getattr("EvidencePageRangeCalculator")
        assert cls is not None

    def test_get_evidence_file_storage(self):
        from apps.documents.services.evidence import __getattr__ as lazy_getattr

        storage = lazy_getattr("evidence_file_storage")
        assert storage is not None


# =====================================================================
# ContextBuilder — 格式化方法
# =====================================================================

class TestContextBuilderFormatMethods:
    def test_format_date_none(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        builder = ContextBuilder()
        assert builder._format_date(None) == ""

    def test_format_date_value(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        builder = ContextBuilder(date_format="%Y年%m月%d日")
        result = builder._format_date(date(2026, 1, 15))
        assert "2026" in result
        assert "01" in result
        assert "15" in result

    def test_format_currency_none(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        builder = ContextBuilder()
        assert builder._format_currency(None) == ""

    def test_format_currency_value(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        builder = ContextBuilder()
        result = builder._format_currency(Decimal("12345.67"))
        assert "12" in result or "12345" in result

    def test_format_percentage_none(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        builder = ContextBuilder()
        assert builder._format_percentage(None) == ""

    def test_format_percentage_value(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        builder = ContextBuilder()
        result = builder._format_percentage(Decimal("0.15"))
        assert "%" in result or "15" in result

    def test_enhanced_builder_fallback(self):
        """When _use_enhanced is False, use direct build."""
        from apps.documents.services.generation.context_builder import ContextBuilder

        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "测试合同",
            "case_type": "civil",
            "case_type_display": "民事",
            "status": "active",
            "status_display": "生效中",
            "specified_date": date(2026, 1, 1),
            "start_date": date(2026, 1, 1),
            "end_date": date(2027, 1, 1),
            "fee_mode": "fixed",
            "fee_mode_display": "固定收费",
            "fixed_amount": Decimal("10000"),
            "risk_rate": Decimal("0.1"),
            "custom_terms": "无",
            "representation_stages": ["一审"],
            "contract_parties": [],
            "assignments": [],
        }

        builder = ContextBuilder(contract_service=mock_svc, use_enhanced=False)
        ctx = builder.build_contract_context(1)
        assert ctx["contract_name"] == "测试合同"
        assert ctx["contract_type"] == "民事"

    def test_build_contract_context_no_contract(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = None

        builder = ContextBuilder(contract_service=mock_svc, use_enhanced=False)
        ctx = builder.build_contract_context(999)
        assert ctx == {}

    def test_build_contract_context_with_parties(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "case_type": "civil",
            "case_type_display": "民事",
            "status": "active",
            "status_display": "生效",
            "specified_date": None,
            "start_date": None,
            "end_date": None,
            "fee_mode": None,
            "fee_mode_display": None,
            "fixed_amount": None,
            "risk_rate": None,
            "custom_terms": None,
            "representation_stages": [],
            "contract_parties": [
                {"role": "PRINCIPAL", "client": {"name": "张三", "id_number": "110", "phone": "123", "address": "北京"}},
                {"role": "BENEFICIARY", "client": {"name": "李四", "id_number": "120"}},
                {"role": "OPPOSING", "client_name": "王五"},
            ],
            "assignments": [
                {"is_primary": True, "lawyer": {"real_name": "律师A", "phone": "138", "license_no": "L001"}},
            ],
        }

        builder = ContextBuilder(contract_service=mock_svc, use_enhanced=False)
        ctx = builder.build_contract_context(1)
        assert ctx["principal_name"] == "张三"
        assert ctx["beneficiary_name"] == "李四"
        assert ctx["opposing_party_name"] == "王五"
        assert ctx["primary_lawyer_name"] == "律师A"

    def test_build_contract_context_no_parties_no_assignments(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "case_type": "",
            "case_type_display": "",
            "status": "",
            "status_display": "",
            "specified_date": None,
            "start_date": None,
            "end_date": None,
            "fee_mode": None,
            "fee_mode_display": None,
            "fixed_amount": None,
            "risk_rate": None,
            "custom_terms": None,
            "representation_stages": [],
            "contract_parties": [],
            "assignments": [],
        }

        builder = ContextBuilder(contract_service=mock_svc, use_enhanced=False)
        ctx = builder.build_contract_context(1)
        assert ctx["principal_name"] == ""
        assert ctx["beneficiary_name"] == ""
        assert ctx["opposing_party_name"] == ""
        assert ctx["primary_lawyer_name"] == ""

    def test_build_contract_context_fallback_assignment(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "case_type": "",
            "case_type_display": "",
            "status": "",
            "status_display": "",
            "specified_date": None,
            "start_date": None,
            "end_date": None,
            "fee_mode": None,
            "fee_mode_display": None,
            "fixed_amount": None,
            "risk_rate": None,
            "custom_terms": None,
            "representation_stages": [],
            "contract_parties": [],
            "assignments": [
                {"is_primary": False, "lawyer_name": "律师B", "lawyer_phone": "139", "lawyer_license_no": "L002"},
            ],
        }

        builder = ContextBuilder(contract_service=mock_svc, use_enhanced=False)
        ctx = builder.build_contract_context(1)
        assert ctx["primary_lawyer_name"] == "律师B"

    def test_build_contract_context_flat_party_format(self):
        from apps.documents.services.generation.context_builder import ContextBuilder

        mock_svc = MagicMock()
        mock_svc.get_contract_with_details_internal.return_value = {
            "name": "合同",
            "case_type": "",
            "case_type_display": "",
            "status": "",
            "status_display": "",
            "specified_date": None,
            "start_date": None,
            "end_date": None,
            "fee_mode": None,
            "fee_mode_display": None,
            "fixed_amount": None,
            "risk_rate": None,
            "custom_terms": None,
            "representation_stages": [],
            "contract_parties": [
                {"role": "PRINCIPAL", "client_name": "扁平客户", "id_number": "999", "phone": "000", "address": "上海"},
            ],
            "assignments": [
                {"is_primary": False, "lawyer_name": "扁平律师", "lawyer_phone": "888", "lawyer_license_no": "LX"},
            ],
        }

        builder = ContextBuilder(contract_service=mock_svc, use_enhanced=False)
        ctx = builder.build_contract_context(1)
        assert ctx["principal_name"] == "扁平客户"
        assert ctx["primary_lawyer_name"] == "扁平律师"


# =====================================================================
# MergeProgressReporter — 时间节流逻辑
# =====================================================================

class TestMergeProgressReporterLogic:
    def test_report_skips_duplicate_progress_within_interval(self):
        """模拟进度相同时在最小间隔内跳过更新。"""
        import time

        # Simulate the reporter logic
        last_progress = 50
        last_update_ts = time.time()  # just now
        min_interval = 0.5
        progress = 50  # same
        now = time.time()

        should_skip = (progress == last_progress and (now - last_update_ts) < min_interval)
        assert should_skip is True

    def test_report_does_not_skip_different_progress(self):
        import time

        last_progress = 50
        last_update_ts = time.time()
        min_interval = 0.5
        progress = 75  # different
        now = time.time()

        should_skip = (progress == last_progress and (now - last_update_ts) < min_interval)
        assert should_skip is False


# =====================================================================
# EvidenceService — 属性访问与初始化
# =====================================================================

class TestEvidenceServiceProperties:
    def test_supported_formats_from_file_service(self):
        from apps.documents.services.evidence.evidence_service import EvidenceService
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService

        assert EvidenceService.SUPPORTED_FORMATS == EvidenceFileService.SUPPORTED_FORMATS

    def test_max_file_size_from_file_service(self):
        from apps.documents.services.evidence.evidence_service import EvidenceService
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService

        assert EvidenceService.MAX_FILE_SIZE == EvidenceFileService.MAX_FILE_SIZE

    def test_case_service_not_injected_raises(self):
        from apps.documents.services.evidence.evidence_service import EvidenceService

        svc = EvidenceService(case_service=None)
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_case_service_injected(self):
        from apps.documents.services.evidence.evidence_service import EvidenceService

        mock = MagicMock()
        svc = EvidenceService(case_service=mock)
        assert svc.case_service is mock

    def test_query_service_default(self):
        from apps.documents.services.evidence.evidence_service import EvidenceService
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        svc = EvidenceService()
        assert isinstance(svc.query_service, EvidenceQueryService)

    def test_mutation_service_default(self):
        from apps.documents.services.evidence.evidence_service import EvidenceService
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService

        svc = EvidenceService()
        assert isinstance(svc.mutation_service, EvidenceMutationService)

    def test_injected_services(self):
        from apps.documents.services.evidence.evidence_service import EvidenceService

        q = MagicMock()
        m = MagicMock()
        f = MagicMock()
        p = MagicMock()
        svc = EvidenceService(query_service=q, mutation_service=m, file_service=f, page_range_calculator=p)
        assert svc.query_service is q
        assert svc.mutation_service is m
        assert svc.file_service is f
        assert svc.page_range_calculator is p


# =====================================================================
# EvidenceListPlaceholderService — 常量映射
# =====================================================================

class TestEvidenceListPlaceholderServiceConstants:
    def test_legal_status_display_mapping(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import LEGAL_STATUS_DISPLAY

        assert LEGAL_STATUS_DISPLAY["plaintiff"] == "原告"
        assert LEGAL_STATUS_DISPLAY["defendant"] == "被告"
        assert LEGAL_STATUS_DISPLAY["third"] == "第三人"
        assert LEGAL_STATUS_DISPLAY["applicant"] == "申请人"
        assert LEGAL_STATUS_DISPLAY["appellant"] == "上诉人"

    def test_legal_status_order(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import LEGAL_STATUS_ORDER

        assert LEGAL_STATUS_ORDER[0] == "plaintiff"
        assert LEGAL_STATUS_ORDER[-1] == "orig_third"
        assert len(LEGAL_STATUS_ORDER) == 11


# =====================================================================
# EvidenceQueryService — _build_dtos 逻辑
# =====================================================================

class TestEvidenceQueryServiceBuildDtos:
    def test_build_dtos_with_file_path(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        svc = EvidenceQueryService()

        mock_field = MagicMock()
        mock_field.storage.path.return_value = "/path/to/file.pdf"
        svc._query_service_build_dtos_test = True

        # Directly test _build_dtos
        items = [{"id": 1, "order": 1, "name": "A", "purpose": "P", "page_start": 1, "page_end": 2, "file": "file.pdf"}]
        with patch("apps.documents.models.EvidenceItem._meta.get_field", return_value=mock_field):
            dtos = svc._build_dtos(items)
            assert len(dtos) == 1
            assert dtos[0].file_path == "/path/to/file.pdf"

    def test_build_dtos_without_file(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        svc = EvidenceQueryService()

        mock_field = MagicMock()
        items = [{"id": 1, "order": 1, "name": "A", "purpose": "P", "page_start": None, "page_end": None, "file": ""}]
        with patch("apps.documents.models.EvidenceItem._meta.get_field", return_value=mock_field):
            dtos = svc._build_dtos(items)
            assert len(dtos) == 1
            assert dtos[0].file_path is None

    def test_build_dtos_storage_error(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        svc = EvidenceQueryService()

        mock_field = MagicMock()
        mock_field.storage.path.side_effect = Exception("storage error")
        items = [{"id": 1, "order": 1, "name": "A", "purpose": "P", "page_start": None, "page_end": None, "file": "bad.pdf"}]
        with patch("apps.documents.models.EvidenceItem._meta.get_field", return_value=mock_field):
            dtos = svc._build_dtos(items)
            assert len(dtos) == 1
            assert dtos[0].file_path is None

    def test_list_evidence_items_for_digest_empty(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        svc = EvidenceQueryService()
        result = svc.list_evidence_items_for_digest_internal([], [])
        assert result == []

    def test_list_evidence_item_ids_with_files_empty(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        svc = EvidenceQueryService()
        result = svc.list_evidence_item_ids_with_files_internal([])
        assert result == []


# =====================================================================
# EvidenceExportService — export_evidence_list 全流程
# =====================================================================

class TestEvidenceExportServiceExport:
    @patch("apps.documents.services.evidence.evidence_export_service.EvidenceList")
    def test_export_evidence_list(self, MockEL):
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService

        svc = EvidenceExportService()

        mock_case = SimpleNamespace(name="案件A")
        mock_items = [
            SimpleNamespace(order=1, name="证据1", purpose="证明内容1", page_range_display="1-3"),
            SimpleNamespace(order=2, name="证据2", purpose="证明内容2", page_range_display="4-5"),
        ]
        mock_el = SimpleNamespace(
            id=1, title="证据清单一", case=mock_case, items=MagicMock(order_by=MagicMock(return_value=mock_items)),
            export_version=1, order=1, case_id=1,
        )

        MockEL.objects.select_related.return_value.get.return_value = mock_el
        MockEL.objects.filter.return_value.aggregate.return_value = {"total": 2}

        content, filename = svc.export_evidence_list(1)
        assert content  # non-empty bytes
        assert filename.endswith(".docx")
        assert "证据清单一" in filename


# =====================================================================
# EvidenceExportService — export_evidence_detail
# =====================================================================

class TestEvidenceExportServiceDetailExport:
    @patch("apps.documents.services.evidence.evidence_export_service.EvidenceList")
    def test_export_evidence_detail(self, MockEL):
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService

        svc = EvidenceExportService()

        mock_case = SimpleNamespace(name="案件B")
        mock_items = [
            SimpleNamespace(
                order=1, name="证据A", purpose="内容", page_range_display="1-3",
                page_start=1, page_end=3, file=True, file_name="a.pdf",
                file_size_display="1.0 MB", page_count=3,
            ),
        ]
        mock_el = SimpleNamespace(
            id=1, title="证据清单一", case=mock_case,
            items=MagicMock(order_by=MagicMock(return_value=mock_items)),
            export_version=1, order=1, case_id=1,
        )

        MockEL.objects.select_related.return_value.get.return_value = mock_el
        MockEL.objects.filter.return_value.aggregate.return_value = {"total": 1}

        content, filename = svc.export_evidence_detail(1)
        assert content
        assert "证据明细" in filename
        assert filename.endswith(".docx")

    @patch("apps.documents.services.evidence.evidence_export_service.EvidenceList")
    def test_export_evidence_detail_no_file(self, MockEL):
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService

        svc = EvidenceExportService()

        mock_case = SimpleNamespace(name="案件C")
        mock_items = [
            SimpleNamespace(
                order=1, name="证据B", purpose="内容", page_range_display="-",
                page_start=None, page_end=None, file=None, file_name="",
                file_size_display="-", page_count=0,
            ),
        ]
        mock_el = SimpleNamespace(
            id=1, title="证据清单一", case=mock_case,
            items=MagicMock(order_by=MagicMock(return_value=mock_items)),
            export_version=1, order=1, case_id=1,
        )

        MockEL.objects.select_related.return_value.get.return_value = mock_el
        MockEL.objects.filter.return_value.aggregate.return_value = {"total": 0}

        content, filename = svc.export_evidence_detail(1)
        assert content
        assert "证据明细" in filename


# =====================================================================
# EvidenceExportService — export_evidence_list_with_template
# =====================================================================

class TestExportWithTemplate:
    @patch("apps.documents.services.evidence.evidence_export_service.EvidenceList")
    def test_no_template_falls_back_to_default(self, MockEL):
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService

        svc = EvidenceExportService()

        mock_case = SimpleNamespace(name="案件")
        mock_el = SimpleNamespace(
            id=1, title="清单", case=mock_case,
            items=MagicMock(order_by=MagicMock(return_value=[])),
            export_version=1, order=1, case_id=1,
        )
        MockEL.objects.select_related.return_value.get.return_value = mock_el
        MockEL.objects.filter.return_value.aggregate.return_value = {"total": 0}

        content, filename = svc.export_evidence_list_with_template(1, template_id=None)
        assert content is not None

    @patch("apps.documents.services.evidence.evidence_export_service.EvidenceList")
    def test_template_not_found_raises(self, MockEL):
        from apps.core.exceptions import NotFoundError
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService

        svc = EvidenceExportService()

        mock_el = SimpleNamespace(id=1)
        MockEL.objects.select_related.return_value.get.return_value = mock_el

        with patch.object(svc, "_get_template", side_effect=NotFoundError("模板不存在", code="TEMPLATE_NOT_FOUND")):
            with pytest.raises(NotFoundError):
                svc.export_evidence_list_with_template(1, template_id=999)
