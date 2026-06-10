"""Tests for apps.automation.admin.document.auto_namer_admin."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django import forms
from django.test import RequestFactory

from apps.automation.admin.document.auto_namer_admin import AutoNamerToolAdmin, AutoNamerToolForm


class TestAutoNamerToolForm:
    def test_form_fields_present(self) -> None:
        form = AutoNamerToolForm()
        assert "upload" in form.fields
        assert "prompt" in form.fields
        assert "model" in form.fields
        assert "limit" in form.fields
        assert "preview_page" in form.fields

    def test_form_valid_with_minimal_data(self) -> None:
        form = AutoNamerToolForm(
            data={"prompt": "test prompt", "model": "qwen3:0.6b"},
            files={"upload": MagicMock()},
        )
        assert form.is_valid()

    def test_form_invalid_without_upload(self) -> None:
        form = AutoNamerToolForm(data={"prompt": "test", "model": "m"})
        assert not form.is_valid()
        assert "upload" in form.errors

    def test_form_invalid_without_prompt(self) -> None:
        form = AutoNamerToolForm(
            data={"model": "m"},
            files={"upload": MagicMock()},
        )
        assert not form.is_valid()
        assert "prompt" in form.errors

    def test_model_field_required(self) -> None:
        form = AutoNamerToolForm(
            data={"prompt": "test"},
            files={"upload": MagicMock()},
        )
        assert not form.is_valid()
        assert "model" in form.errors


class TestAutoNamerToolAdmin:
    def test_has_add_permission_false(self) -> None:
        admin_instance = AutoNamerToolAdmin.__new__(AutoNamerToolAdmin)
        assert admin_instance.has_add_permission(MagicMock()) is False

    def test_has_delete_permission_false(self) -> None:
        admin_instance = AutoNamerToolAdmin.__new__(AutoNamerToolAdmin)
        assert admin_instance.has_delete_permission(MagicMock()) is False

    def test_has_change_permission_true(self) -> None:
        admin_instance = AutoNamerToolAdmin.__new__(AutoNamerToolAdmin)
        assert admin_instance.has_change_permission(MagicMock()) is True

    def test_has_view_permission_true(self) -> None:
        admin_instance = AutoNamerToolAdmin.__new__(AutoNamerToolAdmin)
        assert admin_instance.has_view_permission(MagicMock()) is True

    def test_process_view_get_renders_form(self) -> None:
        """GET request renders the form page."""
        factory = RequestFactory()
        request = factory.get("/admin/automation/namertool/process/")
        request.META["SERVER_NAME"] = "localhost"
        request.META["SERVER_PORT"] = "8000"

        admin_instance = AutoNamerToolAdmin.__new__(AutoNamerToolAdmin)
        admin_instance.model = SimpleNamespace(
            _meta=SimpleNamespace(app_label="automation", model_name="namertool")
        )

        response = admin_instance.process_view(request)
        assert response.status_code == 200
        content = response.content.decode()
        assert "自动命名工具" in content

    def test_redirect_to_process(self) -> None:
        admin_instance = AutoNamerToolAdmin.__new__(AutoNamerToolAdmin)
        admin_instance.model = SimpleNamespace(
            _meta=SimpleNamespace(app_label="automation", model_name="namertool")
        )
        factory = RequestFactory()
        request = factory.get("/admin/automation/namertool/")
        request.META["SERVER_NAME"] = "localhost"
        request.META["SERVER_PORT"] = "8000"

        response = admin_instance.redirect_to_process(request)
        assert response.status_code == 302

    def test_render_no_text_error_for_image(self) -> None:
        admin_instance = AutoNamerToolAdmin.__new__(AutoNamerToolAdmin)
        extraction = SimpleNamespace(kind="image", file_path="/tmp/test.png", image_url="http://example.com/img.png")
        response = admin_instance._render_no_text_error(extraction, "/admin/process/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "图片文件" in content

    def test_render_no_text_error_for_pdf(self) -> None:
        admin_instance = AutoNamerToolAdmin.__new__(AutoNamerToolAdmin)
        extraction = SimpleNamespace(kind="pdf", file_path="/tmp/test.pdf", image_url=None)
        response = admin_instance._render_no_text_error(extraction, "/admin/process/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "PDF" in content
