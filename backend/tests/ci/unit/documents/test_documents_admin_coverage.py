"""Document Template Admin 测试 - 覆盖 DocumentTemplateAdmin"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model

from apps.documents.admin.document_template_admin import (
    DocumentTemplateAdmin,
    DocumentTemplateForm,
)
from apps.documents.admin.template_admin_views_mixin import (
    _normalize_private_docx_root,
    _to_django_relative_path,
)
from apps.documents.models import DocumentTemplate

User = get_user_model()


def _make_admin():
    return DocumentTemplateAdmin(DocumentTemplate, AdminSite())


@pytest.mark.django_db
class TestDocumentTemplateAdminAttributes:
    """验证 Admin 配置属性"""

    def test_list_display(self):
        admin = _make_admin()
        assert "id" in admin.list_display
        assert "name" in admin.list_display
        assert "template_type_display" in admin.list_display
        assert "file_location_display" in admin.list_display
        assert "is_active" in admin.list_display

    def test_list_filter(self):
        admin = _make_admin()
        assert "template_type" in admin.list_filter
        assert "is_active" in admin.list_filter

    def test_search_fields(self):
        admin = _make_admin()
        assert "name" in admin.search_fields
        assert "description" in admin.search_fields

    def test_ordering(self):
        admin = _make_admin()
        assert "-id" in admin.ordering

    def test_readonly_fields(self):
        admin = _make_admin()
        assert "current_file_display" in admin.readonly_fields
        assert "placeholder_preview" in admin.readonly_fields
        assert "placeholders_display" in admin.readonly_fields
        assert "undefined_placeholders_display" in admin.readonly_fields

    def test_actions(self):
        admin = _make_admin()
        assert "activate_templates" in admin.actions
        assert "deactivate_templates" in admin.actions
        assert "refresh_placeholders" in admin.actions
        assert "duplicate_templates" in admin.actions

    def test_change_list_template(self):
        admin = _make_admin()
        assert "change_list" in admin.change_list_template


@pytest.mark.django_db
class TestDocumentTemplateAdminDisplayMethods:
    """测试 display 方法"""

    def test_template_type_display(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.template_type_display = "合同模板"
        result = admin.template_type_display(obj)
        assert result == "合同模板"

    def test_contract_types_display(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.contract_types_display = "借款合同"
        result = admin.contract_types_display(obj)
        assert result == "借款合同"

    def test_case_types_display(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.case_types_display = "民事"
        result = admin.case_types_display(obj)
        assert result == "民事"

    def test_case_stage_display_empty(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.case_stages = []
        result = admin.case_stage_display(obj)
        assert result == "-"

    def test_case_stage_display_with_stages(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.case_stages = ["first_instance"]
        result = admin.case_stage_display(obj)
        assert isinstance(result, str)

    def test_current_file_display_no_pk(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = None
        result = admin.current_file_display(obj)
        assert "新建" in result

    def test_current_file_display_with_file(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = MagicMock()
        obj.file.path = "/some/file.docx"
        obj.file.name = "file.docx"
        result = str(admin.current_file_display(obj))
        assert "file.docx" in result

    def test_current_file_display_with_file_path(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = None
        obj.file_path = "templates/file.docx"
        obj.absolute_file_path = "/full/path/templates/file.docx"
        result = str(admin.current_file_display(obj))
        assert "file.docx" in result

    def test_current_file_display_no_file(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = None
        obj.file_path = ""
        result = str(admin.current_file_display(obj))
        assert "未设置" in result

    def test_placeholder_preview(self):
        admin = _make_admin()
        obj = MagicMock()
        result = str(admin.placeholder_preview(obj))
        assert "placeholder-preview" in result

    def test_file_location_display_with_file(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = MagicMock()
        obj.file.path = "/some/file.docx"
        obj.file.name = "file.docx"
        with patch("django.urls.reverse", return_value="/admin/download/1/"):
            result = str(admin.file_location_display(obj))
            assert "file.docx" in result

    def test_file_location_display_with_file_path(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = None
        obj.file_path = "templates/file.docx"
        obj.absolute_file_path = "/full/path/file.docx"
        with patch("django.urls.reverse", return_value="/admin/download/1/"):
            result = str(admin.file_location_display(obj))
            assert "file.docx" in result

    def test_file_location_display_no_file(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.file = None
        obj.file_path = ""
        result = str(admin.file_location_display(obj))
        assert "未设置" in result


@pytest.mark.django_db
class TestDocumentTemplateAdminPlaceholderMethods:
    """测试占位符相关方法"""

    def test_placeholders_display_no_pk(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = None
        result = admin.placeholders_display(obj)
        assert "保存" in result

    def test_undefined_placeholders_display_no_pk(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = None
        result = admin.undefined_placeholders_display(obj)
        assert "保存" in result


@pytest.mark.django_db
class TestDocumentTemplateAdminNormalizationHelpers:
    """测试路径标准化辅助函数"""

    def test_to_django_relative_path(self):
        from pathlib import Path

        result = _to_django_relative_path(Path("/some/absolute/path"))
        assert isinstance(result, str)

    def test_normalize_private_docx_root_empty(self):
        result = _normalize_private_docx_root("")
        assert result == ""

    def test_normalize_private_docx_root_whitespace(self):
        result = _normalize_private_docx_root("   ")
        assert result == ""


@pytest.mark.django_db
class TestDocumentTemplateAdminGetFieldsets:
    """测试 get_fieldsets"""

    def test_get_fieldsets_add_mode(self):
        admin = _make_admin()
        request = MagicMock()
        fieldsets = admin.get_fieldsets(request, obj=None)
        assert isinstance(fieldsets, list)
        assert len(fieldsets) > 0

    def test_get_fieldsets_edit_mode(self):
        admin = _make_admin()
        request = MagicMock()
        obj = MagicMock()
        fieldsets = admin.get_fieldsets(request, obj=obj)
        assert isinstance(fieldsets, list)
        # Edit mode should add "状态" fieldset
        fieldset_titles = [f[0] for f in fieldsets]
        assert "状态" in fieldset_titles
