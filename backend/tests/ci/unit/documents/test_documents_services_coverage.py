"""Documents services coverage boost - catalog service, smart fill, evidence admin mixins."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ── CodePlaceholderCatalogService ────────────────────────────────────────


class TestCodePlaceholderCatalogService:
    """apps/documents/services/code_placeholders/catalog_service.py"""

    def _make_service(self):
        from apps.documents.services.code_placeholders.catalog_service import CodePlaceholderCatalogService

        return CodePlaceholderCatalogService()

    def test_list_definitions_returns_list(self):
        svc = self._make_service()
        result = svc.list_definitions()
        assert isinstance(result, list)

    def test_list_keys_returns_list(self):
        svc = self._make_service()
        result = svc.list_keys()
        assert isinstance(result, list)

    def test_get_definition_not_found(self):
        svc = self._make_service()
        result = svc.get_definition("__nonexistent_key_xyz__")
        assert result is None

    def test_is_placeholder_key_candidate_valid(self):
        svc = self._make_service()
        assert svc._is_placeholder_key_candidate("案件名称") is True

    def test_is_placeholder_key_candidate_invalid(self):
        svc = self._make_service()
        assert svc._is_placeholder_key_candidate("") is False

    def test_looks_like_template_placeholder_chinese(self):
        svc = self._make_service()
        assert svc._looks_like_template_placeholder("案件名称") is True

    def test_looks_like_template_placeholder_english(self):
        svc = self._make_service()
        assert svc._looks_like_template_placeholder("case_name") is False


class TestContextDictKeyVisitor:
    """_ContextDictKeyVisitor 测试"""

    def test_visitor_init(self):
        from apps.documents.services.code_placeholders.catalog_service import _ContextDictKeyVisitor

        visitor = _ContextDictKeyVisitor()
        assert visitor.keys == set()

    def test_visitor_collects_dict_keys(self):
        from apps.documents.services.code_placeholders.catalog_service import _ContextDictKeyVisitor

        code = """
def build_context():
    return {"案件名称": "test", "原告": "test2"}
"""
        tree = ast.parse(code)
        visitor = _ContextDictKeyVisitor()
        visitor.visit(tree)
        assert "案件名称" in visitor.keys
        assert "原告" in visitor.keys

    def test_visitor_collects_assign_context(self):
        from apps.documents.services.code_placeholders.catalog_service import _ContextDictKeyVisitor

        code = """
context = {"案件名称": "test", "被告": "test2"}
"""
        tree = ast.parse(code)
        visitor = _ContextDictKeyVisitor()
        visitor.visit(tree)
        assert "案件名称" in visitor.keys

    def test_visitor_ignores_non_dict(self):
        from apps.documents.services.code_placeholders.catalog_service import _ContextDictKeyVisitor

        code = """
def build_context():
    return "not a dict"
"""
        tree = ast.parse(code)
        visitor = _ContextDictKeyVisitor()
        visitor.visit(tree)
        assert len(visitor.keys) == 0


class TestExtractStringAssignment:
    """_extract_string_assignment 测试"""

    def test_valid_string_assignment(self):
        from apps.documents.services.code_placeholders.catalog_service import _extract_string_assignment

        code = 'CASE_NAME = "案件名称"'
        tree = ast.parse(code)
        stmt = tree.body[0]
        result = _extract_string_assignment(stmt)
        assert result == "案件名称"

    def test_non_assignment_returns_none(self):
        from apps.documents.services.code_placeholders.catalog_service import _extract_string_assignment

        code = 'print("hello")'
        tree = ast.parse(code)
        stmt = tree.body[0]
        result = _extract_string_assignment(stmt)
        assert result is None

    def test_non_string_value_returns_none(self):
        from apps.documents.services.code_placeholders.catalog_service import _extract_string_assignment

        code = "CASE_NAME = 123"
        tree = ast.parse(code)
        stmt = tree.body[0]
        result = _extract_string_assignment(stmt)
        assert result is None

    def test_empty_string_returns_none(self):
        from apps.documents.services.code_placeholders.catalog_service import _extract_string_assignment

        code = 'CASE_NAME = ""'
        tree = ast.parse(code)
        stmt = tree.body[0]
        result = _extract_string_assignment(stmt)
        assert result is None


class TestSpecMetadata:
    """_spec_metadata 测试"""

    def test_litigation_ai_path(self):
        from apps.documents.services.code_placeholders.catalog_service import _spec_metadata

        path = Path("/apps/litigation_ai/placeholders/spec.py")
        source, category, desc = _spec_metadata(path)
        assert category == "litigation"

    def test_other_path(self):
        from apps.documents.services.code_placeholders.catalog_service import _spec_metadata

        path = Path("/apps/contracts/placeholders/spec.py")
        source, category, desc = _spec_metadata(path)
        assert "contracts" in category


class TestExtractDefinitionsFromSpec:
    """_extract_definitions_from_spec 测试"""

    def test_valid_spec_file(self, tmp_path):
        from apps.documents.services.code_placeholders.catalog_service import _extract_definitions_from_spec

        spec_content = """
class CasePlaceholderKeys:
    CASE_NAME = "案件名称"
    PLAINTIFF = "原告"
"""
        spec_file = tmp_path / "spec.py"
        spec_file.write_text(spec_content, encoding="utf-8")
        result = _extract_definitions_from_spec(spec_file)
        assert len(result) == 2
        keys = [d.key for d in result]
        assert "案件名称" in keys
        assert "原告" in keys

    def test_empty_spec_file(self, tmp_path):
        from apps.documents.services.code_placeholders.catalog_service import _extract_definitions_from_spec

        spec_file = tmp_path / "spec.py"
        spec_file.write_text("", encoding="utf-8")
        result = _extract_definitions_from_spec(spec_file)
        assert result == []

    def test_syntax_error_returns_empty(self, tmp_path):
        from apps.documents.services.code_placeholders.catalog_service import _extract_definitions_from_spec

        spec_file = tmp_path / "spec.py"
        spec_file.write_text("def invalid syntax {{{", encoding="utf-8")
        result = _extract_definitions_from_spec(spec_file)
        assert result == []

    def test_nonexistent_file_returns_empty(self):
        from apps.documents.services.code_placeholders.catalog_service import _extract_definitions_from_spec

        result = _extract_definitions_from_spec(Path("/nonexistent/spec.py"))
        assert result == []


# ── SmartFillService ─────────────────────────────────────────────────────


class TestSmartFillService:
    """apps/documents/services/smart_fill/service.py"""

    def test_placeholder_result_dataclass(self):
        from apps.documents.services.smart_fill.service import PlaceholderResult

        pr = PlaceholderResult(key="k", value="v", source="llm")
        assert pr.key == "k"
        assert pr.value == "v"
        assert pr.source == "llm"

    def test_smart_fill_result_dataclass(self):
        from apps.documents.services.smart_fill.service import SmartFillResult

        result = SmartFillResult()
        assert result.placeholders == []
        assert result.rendered_bytes is None
        assert result.error is None

    def test_smart_fill_result_with_data(self):
        from apps.documents.services.smart_fill.service import PlaceholderResult, SmartFillResult

        items = [PlaceholderResult(key="k", value="v", source="auto")]
        result = SmartFillResult(placeholders=items, rendered_bytes=b"test")
        assert len(result.placeholders) == 1
        assert result.rendered_bytes == b"test"

    def test_build_catalog_with_auto_fill_keys(self):
        from apps.documents.services.smart_fill.service import SmartFillService

        svc = SmartFillService(llm_service=MagicMock())
        result = svc._build_catalog(["今天日期", "案件名称"])
        assert "自动填充" in result
        assert "案件名称" in result

    def test_build_catalog_with_definitions(self):
        from apps.documents.services.smart_fill.service import SmartFillService

        svc = SmartFillService(llm_service=MagicMock())
        mock_def = SimpleNamespace(
            key="案件名称", display_name="案件名称", description="案件的名称", example_value="张三诉李四"
        )
        with patch.object(
            svc._catalog_service, "list_definitions", return_value=[mock_def]
        ):
            result = svc._build_catalog(["案件名称"])
            assert "案件名称" in result

    def test_build_catalog_unknown_key(self):
        from apps.documents.services.smart_fill.service import SmartFillService

        svc = SmartFillService(llm_service=MagicMock())
        with patch.object(svc._catalog_service, "list_definitions", return_value=[]):
            result = svc._build_catalog(["自定义占位符"])
            assert "自定义占位符" in result

    def test_build_result_items_auto_fill(self):
        from apps.documents.services.smart_fill.service import SmartFillService

        svc = SmartFillService(llm_service=MagicMock())
        items = svc._build_result_items(["今天日期", "案件名称"], {"案件名称": "测试案件"})
        assert len(items) == 2
        auto_items = [i for i in items if i.source == "auto"]
        llm_items = [i for i in items if i.source == "llm"]
        assert len(auto_items) == 1
        assert len(llm_items) == 1

    def test_build_result_items_fallback(self):
        from apps.documents.services.smart_fill.service import SmartFillService

        svc = SmartFillService(llm_service=MagicMock())
        items = svc._build_result_items(["未知键"], {})
        assert len(items) == 1
        assert items[0].source == "fallback"

    @patch("apps.documents.services.smart_fill.service.extract_placeholders")
    def test_preview_no_placeholders(self, mock_extract):
        from apps.documents.services.smart_fill.service import SmartFillService

        mock_extract.return_value = []
        svc = SmartFillService(llm_service=MagicMock())
        result = svc.preview("test.docx", "some input")
        assert result.error is not None

    @patch("apps.documents.services.smart_fill.service.extract_placeholders")
    def test_preview_exception(self, mock_extract):
        from apps.documents.services.smart_fill.service import SmartFillService

        mock_extract.side_effect = Exception("file not found")
        svc = SmartFillService(llm_service=MagicMock())
        result = svc.preview("test.docx", "some input")
        assert result.error is not None

    def test_fill_with_error_propagates(self):
        from apps.documents.services.smart_fill.service import SmartFillService

        svc = SmartFillService(llm_service=MagicMock())
        with patch.object(svc, "preview") as mock_preview:
            from apps.documents.services.smart_fill.service import SmartFillResult

            mock_preview.return_value = SmartFillResult(error="preview failed")
            result = svc.fill("test.docx", "input")
            assert result.error == "preview failed"


# ── CodePlaceholderRegistry ──────────────────────────────────────────────


class TestCodePlaceholderRegistry:
    """apps/documents/services/code_placeholders/registry.py"""

    def test_registry_init(self):
        from apps.documents.services.code_placeholders.registry import CodePlaceholderRegistry

        reg = CodePlaceholderRegistry()
        assert reg is not None

    def test_list_definitions(self):
        from apps.documents.services.code_placeholders.registry import CodePlaceholderRegistry

        reg = CodePlaceholderRegistry()
        result = reg.list_definitions()
        assert isinstance(result, list)

    def test_definition_dataclass(self):
        from apps.documents.services.code_placeholders.registry import CodePlaceholderDefinition

        d = CodePlaceholderDefinition(
            key="test", source="src", category="cat", display_name="显示", description="描述"
        )
        assert d.key == "test"
        assert d.source == "src"


# ── autodiscover ─────────────────────────────────────────────────────────


class TestAutodiscover:
    """apps/documents/services/code_placeholders/autodiscover.py"""

    def test_module_import(self):
        from apps.documents.services.code_placeholders import autodiscover

        assert autodiscover is not None


# ── Evidence admin mixins ────────────────────────────────────────────────


class TestEvidenceAdminForms:
    """apps/documents/admin/evidence/forms.py"""

    def test_form_import(self):
        from apps.documents.admin.evidence.forms import EvidenceListForm

        assert EvidenceListForm is not None


class TestEvidenceAdminInlines:
    """apps/documents/admin/evidence/inlines.py"""

    def test_inline_import(self):
        from apps.documents.admin.evidence.inlines import EvidenceItemInline

        assert EvidenceItemInline is not None


class TestEvidenceAdminMixins:
    """apps/documents/admin/evidence/mixins/__init__.py"""

    def test_mixins_import(self):
        from apps.documents.admin.evidence.mixins import (
            EvidenceListAdminActionsMixin,
            EvidenceListAdminSaveMixin,
            EvidenceListAdminViewsMixin,
        )

        assert EvidenceListAdminActionsMixin is not None
        assert EvidenceListAdminSaveMixin is not None
        assert EvidenceListAdminViewsMixin is not None


# ── placeholder_admin_service ────────────────────────────────────────────


class TestPlaceholderAdminService:
    """apps/documents/services/placeholders/placeholder_admin_service.py"""

    def test_service_import(self):
        from apps.documents.services.placeholders.placeholder_admin_service import PlaceholderAdminService

        assert PlaceholderAdminService is not None


# ── placeholder_service ──────────────────────────────────────────────────


class TestPlaceholderService:
    """apps/documents/services/placeholders/placeholder_service.py"""

    def test_service_import(self):
        from apps.documents.services.placeholders.placeholder_service import PlaceholderService

        assert PlaceholderService is not None


# ── placeholder_usage_service ────────────────────────────────────────────


class TestPlaceholderUsageService:
    """apps/documents/services/placeholders/placeholder_usage_service.py"""

    def test_service_import(self):
        from apps.documents.services.placeholders.placeholder_usage_service import PlaceholderUsageService

        assert PlaceholderUsageService is not None


# ── proxy_matter_rule_init_service ───────────────────────────────────────


class TestProxyMatterRuleInitService:
    """apps/documents/services/proxy_matter_rule_init_service.py"""

    def test_service_import(self):
        from apps.documents.services.proxy_matter_rule_init_service import ProxyMatterRuleInitService

        assert ProxyMatterRuleInitService is not None


# ── Template services ────────────────────────────────────────────────────


class TestTemplateFolderService:
    """apps/documents/services/template/folder_service.py"""

    def test_service_import(self):
        from apps.documents.services.template.folder_service import FolderTemplateService

        assert FolderTemplateService is not None


class TestTemplateService:
    """apps/documents/services/template/template_service.py"""

    def test_service_import(self):
        from apps.documents.services.template.template_service import DocumentTemplateService

        assert DocumentTemplateService is not None


# ── Schemas ──────────────────────────────────────────────────────────────


class TestDocumentsSchemas:
    """apps/documents/schemas.py"""

    def test_schemas_import(self):
        from apps.documents import schemas

        assert schemas is not None


# ── Evidence storage ─────────────────────────────────────────────────────


class TestEvidenceStorage:
    """apps/documents/models/evidence_storage.py"""

    def test_storage_import(self):
        from apps.documents.models.evidence_storage import evidence_file_storage

        assert evidence_file_storage is not None


# ── usecases ─────────────────────────────────────────────────────────────


class TestFolderTemplateUsecases:
    """apps/documents/usecases/folder_template/folder_template_usecases.py"""

    def test_usecase_import(self):
        from apps.documents.usecases.folder_template.folder_template_usecases import FolderTemplateUsecases

        assert FolderTemplateUsecases is not None
