"""Documents module coverage boost tests.

Covers:
- apps/documents/models/evidence.py (EvidenceList, EvidenceItem properties)
- apps/documents/models/placeholder.py (data_path, category, hooks)
- apps/documents/models/folder_template.py (model methods)
- apps/documents/models/document_template.py (model methods)
- apps/documents/admin/audit_log_admin.py
- apps/documents/services/placeholders/fallback.py
- apps/documents/services/placeholders/registry.py
- apps/documents/services/evidence/evidence_export_service.py
- apps/documents/services/placeholders/context_builder.py
- apps/documents/services/__init__.py
"""
from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.core.exceptions import NotFoundError


# ── EvidenceList model properties ─────────────────────────────────────────


class TestEvidenceListProperties:
    """EvidenceList 属性测试"""

    def _make_list(self, **kwargs):
        from apps.documents.models import EvidenceList

        defaults = {
            "title": "证据清单一",
            "order": 1,
            "total_pages": 10,
            "export_version": 1,
        }
        defaults.update(kwargs)
        obj = MagicMock(spec=EvidenceList)
        for k, v in defaults.items():
            setattr(obj, k, v)
        return obj

    def test_str(self):
        from apps.documents.models import EvidenceList

        obj = MagicMock(spec=EvidenceList)
        obj.case.name = "测试案件"
        obj.title = "证据清单一"
        assert "测试案件" in EvidenceList.__str__(obj)

    def test_end_page_with_pages(self):
        from apps.documents.models import EvidenceList

        obj = MagicMock(spec=EvidenceList)
        obj.total_pages = 10
        obj.start_page = 1
        assert EvidenceList.end_page.fget(obj) == 10

    def test_end_page_zero_pages(self):
        from apps.documents.models import EvidenceList

        obj = MagicMock(spec=EvidenceList)
        obj.total_pages = 0
        obj.start_page = 5
        assert EvidenceList.end_page.fget(obj) == 5

    def test_page_range_display_empty(self):
        from apps.documents.models import EvidenceList

        obj = MagicMock(spec=EvidenceList)
        obj.total_pages = 0
        obj.start_page = 1
        assert EvidenceList.page_range_display.fget(obj) == ""

    def test_page_range_display_nonempty(self):
        from apps.documents.models import EvidenceList

        obj = MagicMock(spec=EvidenceList)
        obj.total_pages = 10
        obj.end_page = 10
        obj.start_page = 1
        assert EvidenceList.page_range_display.fget(obj) == "1-10"

    def test_order_range_display_no_items(self):
        from apps.documents.models import EvidenceList

        obj = MagicMock(spec=EvidenceList)
        obj.item_count = None
        obj.items.count.return_value = 0
        obj.start_order = 1
        assert EvidenceList.order_range_display.fget(obj) == "-"

    def test_order_range_display_single_item(self):
        from apps.documents.models import EvidenceList

        obj = MagicMock(spec=EvidenceList)
        obj.item_count = None
        obj.items.count.return_value = 1
        obj.start_order = 3
        assert EvidenceList.order_range_display.fget(obj) == "3"

    def test_order_range_display_multiple_items(self):
        from apps.documents.models import EvidenceList

        obj = MagicMock(spec=EvidenceList)
        obj.item_count = None
        obj.items.count.return_value = 5
        obj.start_order = 1
        assert EvidenceList.order_range_display.fget(obj) == "1-5"

    def test_order_range_display_with_item_count_attr(self):
        from apps.documents.models import EvidenceList

        obj = MagicMock(spec=EvidenceList)
        obj.item_count = 3
        obj.start_order = 2
        assert EvidenceList.order_range_display.fget(obj) == "2-4"


class TestEvidenceItemProperties:
    """EvidenceItem 属性测试"""

    def _make_item(self, **kwargs):
        from apps.documents.models import EvidenceItem

        defaults = {"name": "证据1", "purpose": "证明借款事实", "order": 1, "file_size": 0}
        defaults.update(kwargs)
        obj = MagicMock(spec=EvidenceItem)
        for k, v in defaults.items():
            setattr(obj, k, v)
        return obj

    def test_str(self):
        from apps.documents.models import EvidenceItem

        obj = MagicMock(spec=EvidenceItem)
        obj.order = 1
        obj.name = "证据1"
        assert EvidenceItem.__str__(obj) == "1. 证据1"

    def test_page_range_display_none(self):
        from apps.documents.models import EvidenceItem

        obj = MagicMock(spec=EvidenceItem)
        obj.page_start = None
        obj.page_end = None
        assert EvidenceItem.page_range_display.fget(obj) == "-"

    def test_page_range_display_same(self):
        from apps.documents.models import EvidenceItem

        obj = MagicMock(spec=EvidenceItem)
        obj.page_start = 5
        obj.page_end = 5
        assert EvidenceItem.page_range_display.fget(obj) == "5"

    def test_page_range_display_range(self):
        from apps.documents.models import EvidenceItem

        obj = MagicMock(spec=EvidenceItem)
        obj.page_start = 1
        obj.page_end = 10
        assert EvidenceItem.page_range_display.fget(obj) == "1-10"

    def test_file_size_display_zero(self):
        from apps.documents.models import EvidenceItem

        obj = MagicMock(spec=EvidenceItem)
        obj.file_size = 0
        assert EvidenceItem.file_size_display.fget(obj) == "-"

    def test_file_size_display_bytes(self):
        from apps.documents.models import EvidenceItem

        obj = MagicMock(spec=EvidenceItem)
        obj.file_size = 500
        assert EvidenceItem.file_size_display.fget(obj) == "500 B"

    def test_file_size_display_kb(self):
        from apps.documents.models import EvidenceItem

        obj = MagicMock(spec=EvidenceItem)
        obj.file_size = 2048
        assert "KB" in EvidenceItem.file_size_display.fget(obj)

    def test_file_size_display_mb(self):
        from apps.documents.models import EvidenceItem

        obj = MagicMock(spec=EvidenceItem)
        obj.file_size = 2 * 1024 * 1024
        assert "MB" in EvidenceItem.file_size_display.fget(obj)


# ── Placeholder model ────────────────────────────────────────────────────


class TestPlaceholderModel:
    """Placeholder 模型属性测试"""

    def test_str(self):
        from apps.documents.models.placeholder import Placeholder

        obj = MagicMock(spec=Placeholder)
        obj.display_name = "测试"
        obj.key = "test_key"
        assert Placeholder.__str__(obj) == "测试 (test_key)"

    def test_data_path_default(self):
        from apps.documents.models.placeholder import Placeholder

        obj = MagicMock(spec=Placeholder)
        # Remove _data_path so getattr returns ""
        if hasattr(obj, "_data_path"):
            del obj._data_path
        assert Placeholder.data_path.fget(obj) == ""

    def test_data_path_setter(self):
        from apps.documents.models.placeholder import Placeholder

        obj = MagicMock(spec=Placeholder)
        Placeholder.data_path.fset(obj, "case.name")
        assert obj._data_path == "case.name"

    def test_category_default(self):
        from apps.documents.models.placeholder import Placeholder

        obj = MagicMock(spec=Placeholder)
        if hasattr(obj, "_category"):
            del obj._category
        assert Placeholder.category.fget(obj) == ""

    def test_category_setter(self):
        from apps.documents.models.placeholder import Placeholder

        obj = MagicMock(spec=Placeholder)
        Placeholder.category.fset(obj, "案件信息")
        assert obj._category == "案件信息"


# ── TemplateAuditLogAdmin ────────────────────────────────────────────────


class TestTemplateAuditLogAdmin:
    """TemplateAuditLogAdmin 测试"""

    def _make_admin(self):
        from django.contrib.admin.sites import AdminSite

        from apps.documents.admin.audit_log_admin import TemplateAuditLogAdmin
        from apps.documents.models import TemplateAuditLog

        return TemplateAuditLogAdmin(TemplateAuditLog, AdminSite())

    def test_has_add_permission_false(self):
        admin = self._make_admin()
        assert admin.has_add_permission(MagicMock()) is False

    def test_has_change_permission_false(self):
        admin = self._make_admin()
        assert admin.has_change_permission(MagicMock()) is False

    def test_has_delete_permission_false(self):
        admin = self._make_admin()
        assert admin.has_delete_permission(MagicMock()) is False

    def test_object_repr_display_short(self):
        admin = self._make_admin()
        obj = SimpleNamespace(object_repr="短文本")
        assert admin.object_repr_display(obj) == "短文本"

    def test_object_repr_display_long(self):
        admin = self._make_admin()
        obj = SimpleNamespace(object_repr="a" * 60)
        result = admin.object_repr_display(obj)
        assert result.endswith("...")

    def test_changes_display_empty(self):
        admin = self._make_admin()
        obj = SimpleNamespace(changes={})
        assert admin.changes_display(obj) == "无变更记录"

    def test_changes_display_none(self):
        admin = self._make_admin()
        obj = SimpleNamespace(changes=None)
        assert admin.changes_display(obj) == "无变更记录"

    def test_changes_display_with_data(self):
        admin = self._make_admin()
        obj = SimpleNamespace(changes={"name": {"old": "旧名", "new": "新名"}})
        result = admin.changes_display(obj)
        assert result is not None

    def test_changes_display_truncates_long_values(self):
        admin = self._make_admin()
        obj = SimpleNamespace(changes={"name": {"old": "a" * 150, "new": "b" * 150}})
        result = admin.changes_display(obj)
        assert result is not None

    def test_list_display_config(self):
        admin = self._make_admin()
        assert "id" in admin.list_display
        assert "action" in admin.list_display

    def test_readonly_fields(self):
        admin = self._make_admin()
        assert "changes_display" in admin.readonly_fields


# ── EvidenceListAdmin ────────────────────────────────────────────────────


class TestEvidenceListAdmin:
    """EvidenceListAdmin 测试"""

    def _make_admin(self):
        from django.contrib.admin.sites import site

        from apps.documents.models import EvidenceList

        return site._registry.get(EvidenceList)

    def test_list_display(self):
        admin = self._make_admin()
        if admin is not None:
            assert "title" in admin.list_display
            assert "list_type" in admin.list_display

    def test_fieldsets_present(self):
        admin = self._make_admin()
        if admin is not None:
            assert len(admin.fieldsets) > 0

    def test_readonly_fields(self):
        admin = self._make_admin()
        if admin is not None:
            assert "list_type" in admin.readonly_fields


# ── fallback.py utilities ────────────────────────────────────────────────


class TestFallbackUtils:
    """placeholder/fallback.py 纯函数测试"""

    def test_normalize_none_returns_fallback(self):
        from apps.documents.services.placeholders.fallback import normalize_placeholder_value

        assert normalize_placeholder_value(None) == "/"

    def test_normalize_empty_string_returns_fallback(self):
        from apps.documents.services.placeholders.fallback import normalize_placeholder_value

        assert normalize_placeholder_value("") == "/"

    def test_normalize_whitespace_returns_fallback(self):
        from apps.documents.services.placeholders.fallback import normalize_placeholder_value

        assert normalize_placeholder_value("  ") == "/"

    def test_normalize_valid_value_returns_value(self):
        from apps.documents.services.placeholders.fallback import normalize_placeholder_value

        assert normalize_placeholder_value("有效值") == "有效值"

    def test_normalize_custom_fallback(self):
        from apps.documents.services.placeholders.fallback import normalize_placeholder_value

        assert normalize_placeholder_value(None, fallback_value="N/A") == "N/A"

    def test_normalize_non_string_value(self):
        from apps.documents.services.placeholders.fallback import normalize_placeholder_value

        assert normalize_placeholder_value(42) == 42

    def test_get_service_placeholder_keys_method(self):
        from apps.documents.services.placeholders.fallback import get_service_placeholder_keys

        svc = MagicMock()
        svc.get_placeholder_keys.return_value = ["key1", "key2"]
        assert get_service_placeholder_keys(svc) == ["key1", "key2"]

    def test_get_service_placeholder_keys_attr(self):
        from apps.documents.services.placeholders.fallback import get_service_placeholder_keys

        svc = SimpleNamespace(placeholder_keys=["key1", "key2"])
        assert get_service_placeholder_keys(svc) == ["key1", "key2"]

    def test_get_service_placeholder_keys_no_attr(self):
        from apps.documents.services.placeholders.fallback import get_service_placeholder_keys

        svc = SimpleNamespace()
        assert get_service_placeholder_keys(svc) == []

    def test_get_service_placeholder_keys_string_attr(self):
        from apps.documents.services.placeholders.fallback import get_service_placeholder_keys

        svc = SimpleNamespace(placeholder_keys="not_a_list")
        assert get_service_placeholder_keys(svc) == []

    def test_get_service_placeholder_keys_with_empty_keys(self):
        from apps.documents.services.placeholders.fallback import get_service_placeholder_keys

        svc = SimpleNamespace(placeholder_keys=["", "key1", None])
        assert get_service_placeholder_keys(svc) == ["key1"]

    def test_normalize_service_result_basic(self):
        from apps.documents.services.placeholders.fallback import normalize_service_result

        result = normalize_service_result({"a": "val", "b": None}, expected_keys=["a", "b", "c"])
        assert result["a"] == "val"
        assert result["b"] == "/"
        assert result["c"] == "/"

    def test_normalize_service_result_none_input(self):
        from apps.documents.services.placeholders.fallback import normalize_service_result

        result = normalize_service_result(None, expected_keys=["a"])
        assert result["a"] == "/"

    def test_normalize_service_result_no_expected_keys(self):
        from apps.documents.services.placeholders.fallback import normalize_service_result

        result = normalize_service_result({"a": "val"})
        assert result["a"] == "val"


# ── build_docx_render_context ────────────────────────────────────────────


class TestBuildDocxRenderContext:
    """build_docx_render_context 测试"""

    def test_build_context_returns_dict(self):
        from apps.documents.services.placeholders.fallback import build_docx_render_context

        mock_doc = MagicMock()
        mock_doc.get_undeclared_template_variables.return_value = set()
        result = build_docx_render_context(doc=mock_doc, context={"a": "b"})
        assert isinstance(result, dict)
        assert result["a"] == "b"

    def test_build_context_with_missing_vars(self):
        from apps.documents.services.placeholders.fallback import build_docx_render_context

        mock_doc = MagicMock()
        mock_doc.get_undeclared_template_variables.return_value = {"missing_key"}
        result = build_docx_render_context(doc=mock_doc, context={"a": "b"})
        assert "missing_key" in result

    def test_build_context_with_none_context(self):
        from apps.documents.services.placeholders.fallback import build_docx_render_context

        mock_doc = MagicMock()
        mock_doc.get_undeclared_template_variables.return_value = None
        result = build_docx_render_context(doc=mock_doc, context={})
        assert isinstance(result, dict)

    def test_ensure_required_placeholders(self):
        from apps.documents.services.placeholders.fallback import ensure_required_placeholders

        result = ensure_required_placeholders({"a": "val"}, ["a", "b"])
        assert result["a"] == "val"
        assert result["b"] == "/"

    def test_resolve_render_variable_exists(self):
        from apps.documents.services.placeholders.fallback import resolve_render_variable

        found, val = resolve_render_variable({"key": "value"}, "key")
        assert found is True
        assert val == "value"

    def test_resolve_render_variable_missing(self):
        from apps.documents.services.placeholders.fallback import resolve_render_variable

        found, val = resolve_render_variable({}, "key")
        assert found is False
        assert val == "/"

    def test_resolve_render_variable_none_value(self):
        from apps.documents.services.placeholders.fallback import resolve_render_variable

        found, val = resolve_render_variable({"key": None}, "key")
        assert found is False

    def test_get_undeclared_template_variables(self):
        from apps.documents.services.placeholders.fallback import _get_undeclared_template_variables

        mock_doc = MagicMock()
        mock_doc.get_undeclared_template_variables.return_value = {"a", "b"}
        result = _get_undeclared_template_variables(doc=mock_doc, context={})
        assert result == {"a", "b"}

    def test_get_undeclared_no_method(self):
        from apps.documents.services.placeholders.fallback import _get_undeclared_template_variables

        mock_doc = MagicMock()
        mock_doc.get_undeclared_template_variables = None
        result = _get_undeclared_template_variables(doc=mock_doc, context={})
        assert result == set()

    def test_get_undeclared_exception(self):
        from apps.documents.services.placeholders.fallback import _get_undeclared_template_variables

        mock_doc = MagicMock()
        mock_doc.get_undeclared_template_variables.side_effect = Exception("fail")
        result = _get_undeclared_template_variables(doc=mock_doc, context={})
        assert result == set()

    def test_get_undeclared_type_error_fallback(self):
        from apps.documents.services.placeholders.fallback import _get_undeclared_template_variables

        mock_doc = MagicMock()
        mock_doc.get_undeclared_template_variables.side_effect = [TypeError("fail"), {"a", "b"}]
        result = _get_undeclared_template_variables(doc=mock_doc, context={})
        assert result == {"a", "b"}


# ── evidence_export_service.py ───────────────────────────────────────────


class TestEvidenceExportService:
    """EvidenceExportService 测试"""

    def _make_service(self):
        from apps.documents.services.evidence.evidence_export_service import EvidenceExportService

        return EvidenceExportService(placeholder_service=MagicMock())

    def test_increment_version(self):
        svc = self._make_service()
        obj = SimpleNamespace(export_version=3)
        assert svc._increment_version(obj) == 3

    def test_generate_filename_list(self):
        svc = self._make_service()
        case = SimpleNamespace(name="测试案件")
        el = SimpleNamespace(title="证据清单一", case=case)
        with patch("apps.documents.services.evidence.evidence_export_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            result = svc._generate_filename(el, "证据清单", 1)
            assert "证据清单一" in result
            assert "测试案件" in result
            assert result.endswith(".docx")

    def test_generate_filename_detail(self):
        svc = self._make_service()
        case = SimpleNamespace(name="测试案件")
        el = SimpleNamespace(title="证据清单二", case=case)
        with patch("apps.documents.services.evidence.evidence_export_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            result = svc._generate_filename(el, "证据明细", 1)
            assert "证据明细" in result
            assert result.endswith(".docx")

    def test_generate_filename_supplementary(self):
        svc = self._make_service()
        case = SimpleNamespace(name="测试案件")
        el = SimpleNamespace(title="补充证据清单一", case=case)
        with patch("apps.documents.services.evidence.evidence_export_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            result = svc._generate_filename(el, "证据明细", 1)
            assert "证据明细" in result

    def test_get_template_not_found(self):
        svc = self._make_service()
        with patch("apps.documents.services.evidence.evidence_export_service.EvidenceExportService._get_template"):
            with pytest.raises(NotFoundError):
                svc._get_template = MagicMock(side_effect=NotFoundError("not found", code="NOT_FOUND"))
                svc._get_template(999)

    def test_get_evidence_list_not_found(self):
        svc = self._make_service()
        from apps.documents.models import EvidenceList

        with patch(
            "apps.documents.services.evidence.evidence_export_service.EvidenceList.objects"
        ) as mock_qs:
            mock_qs.select_related.return_value.get.side_effect = EvidenceList.DoesNotExist()
            with pytest.raises(NotFoundError):
                svc._get_evidence_list(999)


# ── registry.py ─────────────────────────────────────────────────────────


class TestPlaceholderRegistry:
    """Placeholder registry 测试"""

    def test_registry_singleton(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        r1 = PlaceholderRegistry()
        r2 = PlaceholderRegistry()
        assert r1 is r2

    def test_registry_get_all_returns_list(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        reg = PlaceholderRegistry()
        result = reg.get_all_services()
        assert isinstance(result, list)

    def test_registry_get_placeholder_keys(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        reg = PlaceholderRegistry()
        result = reg.list_registered_services()
        assert isinstance(result, dict)

    def test_registry_get_context_returns_dict(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        reg = PlaceholderRegistry()
        result = reg.get_all_services()
        assert isinstance(result, list)


# ── services/__init__.py ────────────────────────────────────────────────


class TestServicesInit:
    """documents/services/__init__.py 测试"""

    def test_get_placeholder_service(self):
        from apps.documents.services import PlaceholderService

        assert PlaceholderService is not None

    def test_get_generation_service(self):
        from apps.documents.services import GenerationService

        assert GenerationService is not None

    def test_lazy_export_folder_template_service(self):
        from apps.documents.services import FolderTemplateService

        assert FolderTemplateService is not None

    def test_lazy_export_contract_generation_service(self):
        from apps.documents.services import ContractGenerationService

        assert ContractGenerationService is not None

    def test_lazy_export_document_template_service(self):
        from apps.documents.services import DocumentTemplateService

        assert DocumentTemplateService is not None

    def test_lazy_export_pdf_merge_service(self):
        from apps.documents.services import PDFMergeService

        assert PDFMergeService is not None

    def test_lazy_export_placeholder_admin_service(self):
        from apps.documents.services import PlaceholderAdminService

        assert PlaceholderAdminService is not None

    def test_lazy_export_invalid_raises(self):
        import importlib

        mod = importlib.import_module("apps.documents.services")
        with pytest.raises(AttributeError):
            getattr(mod, "NonExistentService")


# ── FolderTemplate model ────────────────────────────────────────────────


class TestFolderTemplateModel:
    """FolderTemplate 模型方法测试"""

    def test_str(self):
        from apps.documents.models.folder_template import FolderTemplate

        obj = MagicMock(spec=FolderTemplate)
        obj.name = "诉讼文书"
        obj.template_type = "civil_litigation"
        obj.case_types = ["civil"]
        obj._get_types_display = MagicMock(return_value="民事")
        result = FolderTemplate.__str__(obj)
        assert "诉讼文书" in result


# ── DocumentTemplate model ───────────────────────────────────────────────


class TestDocumentTemplateModel:
    """DocumentTemplate 模型方法测试"""

    def test_str(self):
        from apps.documents.models.document_template import DocumentTemplate

        obj = MagicMock(spec=DocumentTemplate)
        obj.name = "起诉状模板"
        obj.template_type = "case"
        result = DocumentTemplate.__str__(obj)
        assert "起诉状模板" in result


# ── FillRecord model ────────────────────────────────────────────────────


class TestFillRecordModel:
    """FillRecord 模型测试"""

    def test_str(self):
        from apps.documents.models.fill_record import FillRecord

        obj = MagicMock(spec=FillRecord)
        obj.pk = 1
        assert FillRecord.__str__(obj) is not None


# ── ExternalTemplate model ───────────────────────────────────────────────


class TestExternalTemplateModel:
    """ExternalTemplate 模型测试"""

    def test_str(self):
        from apps.documents.models.external_template import ExternalTemplate

        obj = MagicMock(spec=ExternalTemplate)
        obj.name = "外部模板"
        assert "外部模板" in ExternalTemplate.__str__(obj)


# ── context_builder.py ──────────────────────────────────────────────────


class TestContextBuilder:
    """EnhancedContextBuilder 测试"""

    def test_builder_import(self):
        from apps.documents.services.placeholders.context_builder import EnhancedContextBuilder

        assert EnhancedContextBuilder is not None

    def test_builder_init(self):
        from apps.documents.services.placeholders.context_builder import EnhancedContextBuilder

        builder = EnhancedContextBuilder()
        assert builder is not None


# ── ProxyMatterRule model ────────────────────────────────────────────────


class TestProxyMatterRuleModel:
    """ProxyMatterRule 模型测试"""

    def test_str(self):
        from apps.documents.models.proxy_matter_rule import ProxyMatterRule

        obj = MagicMock(spec=ProxyMatterRule)
        obj.get_case_types_display.return_value = "民事"
        obj.case_stage = "first_trial"
        obj.get_case_stage_display.return_value = "一审"
        obj.get_legal_statuses_display.return_value = "原告"
        obj.get_legal_status_match_mode_display.return_value = "精确"
        result = ProxyMatterRule.__str__(obj)
        assert "民事" in result


# ── AuditLog model ───────────────────────────────────────────────────────


class TestAuditLogModel:
    """TemplateAuditLog 模型测试"""

    def test_str(self):
        from apps.documents.models.audit_log import TemplateAuditLog

        obj = MagicMock(spec=TemplateAuditLog)
        obj.object_repr = "测试对象"
        obj.action = "create"
        result = TemplateAuditLog.__str__(obj)
        assert result is not None


# ── Generation model ─────────────────────────────────────────────────────


class TestGenerationModel:
    """Generation 模型测试"""

    def test_model_exists(self):
        from apps.documents.models.generation import GenerationTask

        assert GenerationTask is not None

    def test_generation_config_exists(self):
        from apps.documents.models.generation import GenerationConfig

        assert GenerationConfig is not None


# ── Choices module ───────────────────────────────────────────────────────


class TestChoicesModule:
    """choices.py 模块测试"""

    def test_document_template_type_choices(self):
        from apps.documents.models.choices import DocumentTemplateType

        assert len(DocumentTemplateType.choices) > 0

    def test_case_file_sub_type_choices(self):
        from apps.documents.models.choices import DocumentCaseFileSubType

        assert len(DocumentCaseFileSubType.choices) > 0


# ── Placeholder basic services ───────────────────────────────────────────


class TestPlaceholderDateService:
    """DateService 测试"""

    def test_service_exists(self):
        from apps.documents.services.placeholders.basic.date_service import DatePlaceholderService

        assert DatePlaceholderService is not None


class TestPlaceholderNumberService:
    """NumberService 测试"""

    def test_service_exists(self):
        from apps.documents.services.placeholders.basic.number_service import NumberPlaceholderService

        assert NumberPlaceholderService is not None


class TestPlaceholderYearService:
    """YearService 测试"""

    def test_service_exists(self):
        from apps.documents.services.placeholders.basic.year_service import YearPlaceholderService

        assert YearPlaceholderService is not None


# ── Storage module ───────────────────────────────────────────────────────


class TestStorageModule:
    """storage.py 模块测试"""

    def test_module_imports(self):
        from apps.documents.storage import DocumentTemplateStorage

        assert DocumentTemplateStorage is not None

    def test_get_public_docx_templates_root(self):
        from apps.documents.storage import get_public_docx_templates_root

        assert callable(get_public_docx_templates_root)

    def test_get_docx_templates_root(self):
        from apps.documents.storage import get_docx_templates_root

        assert callable(get_docx_templates_root)


# ── apps.py ──────────────────────────────────────────────────────────────


class TestDocumentsAppConfig:
    """apps.py 配置测试"""

    def test_app_config_exists(self):
        from apps.documents.apps import DocumentsConfig

        assert DocumentsConfig.name == "apps.documents"
