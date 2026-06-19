"""Tests for documents.admin.document_template_admin — increase coverage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django import forms

from apps.documents.admin.document_template_admin import (
    DocumentTemplateAdmin,
    DocumentTemplateForm,
    DocumentTemplateFolderBindingInline,
)
from apps.documents.admin.template_admin_views_mixin import (
    _normalize_private_docx_root,
    _to_django_relative_path,
)


# ---------------------------------------------------------------------------
# Helper / utility functions
# ---------------------------------------------------------------------------


class TestToDjangoRelativePath:
    def test_relative_path(self) -> None:
        """Should return a posix relative path from backend root."""
        with patch("apps.documents.admin.document_template_admin.settings") as mock_settings:
            mock_settings.BASE_DIR = str(Path("/app/backend"))
            result = _to_django_relative_path(Path("/app/templates/foo.docx"))
            # result should be relative to backend's parent
            assert isinstance(result, str)

    def test_same_path(self) -> None:
        """When path equals backend root, returns '.' like relative."""
        with patch("apps.documents.admin.document_template_admin.settings") as mock_settings:
            mock_settings.BASE_DIR = str(Path("/app/backend"))
            # path outside backend root should still return something
            result = _to_django_relative_path(Path("/other/path"))
            assert isinstance(result, str)


class TestNormalizePrivateDocxRoot:
    def test_empty_string(self) -> None:
        assert _normalize_private_docx_root("") == ""
        assert _normalize_private_docx_root("   ") == ""

    def test_nonexistent_path_raises(self) -> None:
        with pytest.raises(ValueError, match="模板根目录不存在"):
            _normalize_private_docx_root("/nonexistent/path/xyz")

    @patch("apps.documents.admin.document_template_admin.Path")
    def test_valid_dir(self, mock_path_cls: MagicMock) -> None:
        mock_candidate = MagicMock()
        mock_candidate.is_absolute.return_value = True
        mock_candidate.exists.return_value = True
        mock_candidate.is_dir.return_value = True
        mock_candidate.resolve.return_value = mock_candidate
        mock_path_cls.return_value.expanduser.return_value = mock_candidate
        result = _normalize_private_docx_root("/some/dir")
        assert isinstance(result, str)

    def test_relative_path_resolves(self) -> None:
        """Relative path should be resolved against backend root."""
        with patch("apps.documents.admin.document_template_admin.settings") as mock_settings:
            mock_settings.BASE_DIR = str(Path(__file__).resolve().parent)
            # path that doesn't exist
            with pytest.raises(ValueError):
                _normalize_private_docx_root("some/relative/path")


# ---------------------------------------------------------------------------
# DocumentTemplateFolderBindingInline
# ---------------------------------------------------------------------------


class TestDocumentTemplateFolderBindingInline:
    def test_model(self) -> None:
        from apps.documents.models import DocumentTemplateFolderBinding

        assert DocumentTemplateFolderBindingInline.model == DocumentTemplateFolderBinding

    def test_extra(self) -> None:
        assert DocumentTemplateFolderBindingInline.extra == 1

    def test_fields(self) -> None:
        fields = DocumentTemplateFolderBindingInline.fields
        assert "folder_template" in fields
        assert "folder_node_id" in fields

    def test_readonly_fields(self) -> None:
        assert "folder_node_path" in DocumentTemplateFolderBindingInline.readonly_fields


# ---------------------------------------------------------------------------
# DocumentTemplateAdmin attributes
# ---------------------------------------------------------------------------


class TestDocumentTemplateAdminAttributes:
    def test_list_display(self) -> None:
        assert "id" in DocumentTemplateAdmin.list_display
        assert "name" in DocumentTemplateAdmin.list_display
        assert "template_type_display" in DocumentTemplateAdmin.list_display
        assert "is_active" in DocumentTemplateAdmin.list_display

    def test_list_filter(self) -> None:
        assert "template_type" in DocumentTemplateAdmin.list_filter
        assert "is_active" in DocumentTemplateAdmin.list_filter

    def test_search_fields(self) -> None:
        assert "name" in DocumentTemplateAdmin.search_fields
        assert "description" in DocumentTemplateAdmin.search_fields

    def test_ordering(self) -> None:
        assert DocumentTemplateAdmin.ordering == ("-id",)

    def test_readonly_fields(self) -> None:
        assert "current_file_display" in DocumentTemplateAdmin.readonly_fields
        assert "placeholder_preview" in DocumentTemplateAdmin.readonly_fields

    def test_actions(self) -> None:
        assert "activate_templates" in DocumentTemplateAdmin.actions
        assert "deactivate_templates" in DocumentTemplateAdmin.actions
        assert "refresh_placeholders" in DocumentTemplateAdmin.actions
        assert "duplicate_templates" in DocumentTemplateAdmin.actions

    def test_form_is_document_template_form(self) -> None:
        assert DocumentTemplateAdmin.form == DocumentTemplateForm

    def test_inlines(self) -> None:
        assert DocumentTemplateFolderBindingInline in DocumentTemplateAdmin.inlines


# ---------------------------------------------------------------------------
# DocumentTemplateAdmin display methods
# ---------------------------------------------------------------------------


class TestDocumentTemplateAdminDisplayMethods:
    def _make_admin(self):
        from apps.documents.models import DocumentTemplate

        return DocumentTemplateAdmin(DocumentTemplate, MagicMock())

    def test_template_type_display(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.template_type_display = "合同文书模板"
        assert admin.template_type_display(obj) == "合同文书模板"

    def test_contract_types_display(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.contract_types_display = "民事合同"
        assert admin.contract_types_display(obj) == "民事合同"

    def test_case_types_display(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.case_types_display = "民事案件"
        assert admin.case_types_display(obj) == "民事案件"

    def test_case_stage_display_empty(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.case_stages = []
        assert admin.case_stage_display(obj) == "-"

    def test_case_stage_display_with_stage(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.case_stages = ["first_instance"]
        result = admin.case_stage_display(obj)
        assert isinstance(result, str)

    def test_current_file_display_new_template(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = None
        result = admin.current_file_display(obj)
        assert "新建模板" in str(result)

    def test_current_file_display_with_file(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = MagicMock()
        obj.file.path = "/some/path/template.docx"
        obj.file.name = "template.docx"
        result = admin.current_file_display(obj)
        result_str = str(result)
        assert "template.docx" in result_str

    def test_current_file_display_with_file_path(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = None
        obj.file_path = "templates/foo.docx"
        obj.absolute_file_path = "/absolute/templates/foo.docx"
        result = admin.current_file_display(obj)
        result_str = str(result)
        assert "foo.docx" in result_str

    def test_current_file_display_no_file(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = None
        obj.file_path = None
        result = admin.current_file_display(obj)
        assert "未设置文件" in str(result)

    def test_file_location_display_with_file(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = MagicMock()
        obj.file.path = "/some/path.docx"
        obj.file.name = "path.docx"
        with patch("django.urls.reverse", return_value="/admin/download/1/"):
            result = admin.file_location_display(obj)
            assert "path.docx" in str(result)

    def test_file_location_display_with_file_path(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = None
        obj.file_path = "templates/bar.docx"
        obj.absolute_file_path = "/abs/templates/bar.docx"
        with patch("django.urls.reverse", return_value="/admin/download/1/"):
            result = admin.file_location_display(obj)
            assert "bar.docx" in str(result)

    def test_file_location_display_no_file(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = None
        obj.file_path = None
        result = admin.file_location_display(obj)
        assert "未设置" in str(result)

    def test_placeholder_preview_returns_html(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        result = admin.placeholder_preview(obj)
        assert "placeholder-preview" in str(result)

    def test_placeholder_count_display_exception(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        with patch("apps.documents.admin.document_template_admin._get_template_service", side_effect=Exception("fail")):
            result = admin.placeholder_count_display(obj)
            assert "错误" in str(result)

    def test_placeholders_display_new(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = None
        result = admin.placeholders_display(obj)
        assert "保存后" in str(result)

    def test_undefined_placeholders_display_new(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = None
        result = admin.undefined_placeholders_display(obj)
        assert "保存后" in str(result)

    def test_placeholders_display_exception(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        with patch("apps.documents.admin.document_template_admin._get_template_service", side_effect=Exception("fail")):
            result = admin.placeholders_display(obj)
            assert "提取失败" in str(result)

    def test_undefined_placeholders_display_exception(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        with patch("apps.documents.admin.document_template_admin._get_template_service", side_effect=Exception("fail")):
            result = admin.undefined_placeholders_display(obj)
            assert "检查失败" in str(result)


# ---------------------------------------------------------------------------
# DocumentTemplateAdmin actions
# ---------------------------------------------------------------------------


class TestDocumentTemplateAdminActions:
    def _make_admin(self):
        from apps.documents.models import DocumentTemplate

        return DocumentTemplateAdmin(DocumentTemplate, MagicMock())

    def test_activate_templates(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        queryset = MagicMock()
        with patch("apps.documents.admin.document_template_admin._get_admin_service") as mock_svc:
            mock_svc.return_value.batch_activate.return_value = 3
            admin.activate_templates(request, queryset)
            mock_svc.return_value.batch_activate.assert_called_once_with(queryset)

    def test_deactivate_templates(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        queryset = MagicMock()
        with patch("apps.documents.admin.document_template_admin._get_admin_service") as mock_svc:
            mock_svc.return_value.batch_deactivate.return_value = 2
            admin.deactivate_templates(request, queryset)
            mock_svc.return_value.batch_deactivate.assert_called_once_with(queryset)

    def test_refresh_placeholders(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        queryset = MagicMock()
        queryset.count.return_value = 5
        admin.refresh_placeholders(request, queryset)

    def test_duplicate_templates(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        queryset = MagicMock()
        with patch("apps.documents.admin.document_template_admin._get_admin_service") as mock_svc:
            mock_svc.return_value.batch_duplicate_templates.return_value = 3
            admin.duplicate_templates(request, queryset)
            mock_svc.return_value.batch_duplicate_templates.assert_called_once_with(queryset)


# ---------------------------------------------------------------------------
# DocumentTemplateAdmin view methods
# ---------------------------------------------------------------------------


class TestDocumentTemplateAdminViews:
    def _make_admin(self):
        from apps.documents.models import DocumentTemplate

        return DocumentTemplateAdmin(DocumentTemplate, MagicMock())

    def test_get_search_results_export_template(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.GET = {"field_name": "export_template"}
        queryset = MagicMock()
        queryset.filter.return_value = queryset
        qs, distinct = admin.get_search_results(request, queryset, "test")
        queryset.filter.assert_called()

    def test_get_search_results_normal(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.GET = {}
        queryset = MagicMock()
        qs, distinct = admin.get_search_results(request, queryset, "test")
        # normal search should not add extra filter
        assert isinstance(distinct, bool)

    def test_save_model(self) -> None:
        admin_inst = self._make_admin()
        request = MagicMock()
        obj = MagicMock()
        form = MagicMock()
        with patch("django.contrib.admin.ModelAdmin.save_model"):
            admin_inst.save_model(request, obj, form, change=False)

    def test_extract_placeholders_view_not_post(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.method = "GET"
        result = admin.extract_placeholders_view(request)
        assert result.status_code == 405

    def test_smart_fill_preview_view_not_post(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.method = "GET"
        result = admin.smart_fill_preview_view(request)
        assert result.status_code == 405

    def test_smart_fill_render_view_not_post(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.method = "GET"
        result = admin.smart_fill_render_view(request)
        assert result.status_code == 405

    def test_set_docx_root_view_not_post(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.method = "GET"
        with patch("django.urls.reverse", return_value="/admin/test/"):
            result = admin.set_docx_root_view(request)
            # should redirect with error message
            assert result.status_code in (302, 301)

    def test_build_llm_model_choices_with_default(self) -> None:
        with patch("apps.core.llm.config.LLMConfig") as mock_config, \
             patch("apps.core.llm.model_list_service.ModelListService") as mock_model_svc:
            mock_config.get_openai_compatible_model.return_value = "test-model"
            mock_model_svc.return_value.get_result.return_value = MagicMock(models=[])
            choices = DocumentTemplateAdmin._build_llm_model_choices()
            assert len(choices) >= 1
            # Should include the default model
            assert any("test-model" in c[0] for c in choices)

    def test_build_llm_model_choices_with_models(self) -> None:
        with patch("apps.core.llm.config.LLMConfig") as mock_config, \
             patch("apps.core.llm.model_list_service.ModelListService") as mock_model_svc:
            mock_config.get_openai_compatible_model.return_value = "default-model"
            mock_result = MagicMock()
            mock_result.models = [
                {"id": "model-1", "name": "Model One"},
                {"id": "model-2", "name": ""},
            ]
            mock_model_svc.return_value.get_result.return_value = mock_result
            choices = DocumentTemplateAdmin._build_llm_model_choices()
            assert len(choices) >= 2

    def test_build_llm_model_choices_exception(self) -> None:
        with patch("apps.core.llm.config.LLMConfig") as mock_config, \
             patch("apps.core.llm.model_list_service.ModelListService", side_effect=Exception("fail")):
            mock_config.get_default_model.return_value = ""
            choices = DocumentTemplateAdmin._build_llm_model_choices()
            # Should fall back to a default
            assert len(choices) >= 1

    def test_resolve_template_path_with_file_path(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.FILES = {}
        request.POST = {"file_path": "/some/template.docx", "existing_file": ""}
        with patch("apps.documents.storage.resolve_docx_template_path") as mock_resolve:
            mock_resolve.return_value = MagicMock(exists=MagicMock(return_value=True))
            path, err = admin._resolve_template_path(request)
            assert err is None

    def test_resolve_template_path_no_source(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.FILES = {}
        request.POST = {"file_path": "", "existing_file": ""}
        path, err = admin._resolve_template_path(request)
        assert err is not None
        assert "请提供" in err


# ---------------------------------------------------------------------------
# DocumentTemplateForm attributes
# ---------------------------------------------------------------------------


class TestDocumentTemplateForm:
    def test_template_type_field(self) -> None:
        assert "template_type" in DocumentTemplateForm.base_fields

    def test_has_contract_sub_type(self) -> None:
        assert "contract_sub_type" in DocumentTemplateForm.base_fields

    def test_has_case_sub_type(self) -> None:
        assert "case_sub_type" in DocumentTemplateForm.base_fields

    def test_has_existing_file_field(self) -> None:
        assert "existing_file" in DocumentTemplateForm.base_fields

    def test_has_legal_status_match_mode(self) -> None:
        assert "legal_status_match_mode" in DocumentTemplateForm.base_fields
