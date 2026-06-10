"""
Tests for documents/storage.py - uncovered paths around private root config.
"""
from __future__ import annotations

import os
from pathlib import Path as RealPath
from unittest.mock import MagicMock, patch

import pytest

from apps.documents.storage import (
    USER_CUSTOM_TEMPLATE_DIR,
    DocumentTemplateStorage,
    get_configured_private_docx_templates_root,
    get_docx_templates_root,
    get_docx_templates_source,
    get_public_docx_templates_root,
    get_private_docx_templates_root,
    list_docx_templates_files,
    resolve_docx_template_path,
)


class TestGetPublicDocxTemplatesRoot:
    def test_returns_path_object(self):
        result = get_public_docx_templates_root()
        assert str(result).endswith("docx_templates")


class TestGetConfiguredPrivateDocxTemplatesRoot:
    @patch("apps.documents.storage.django_apps")
    @patch("apps.documents.storage.settings")
    def test_returns_setting_when_apps_not_ready(self, mock_settings, mock_apps):
        mock_apps.ready = False
        mock_settings.DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT = "/some/path"
        result = get_configured_private_docx_templates_root()
        assert result == "/some/path"

    @patch("apps.documents.storage.django_apps")
    @patch("apps.documents.storage.settings")
    def test_returns_runtime_config_when_available(self, mock_settings, mock_apps):
        mock_apps.ready = True
        mock_settings.DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT = ""
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = "/runtime/path"
        with patch("apps.core.interfaces.ServiceLocator") as mock_loc:
            mock_loc.get_system_config_service.return_value = mock_svc
            result = get_configured_private_docx_templates_root()
        assert result == "/runtime/path"

    @patch("apps.documents.storage.django_apps")
    @patch("apps.documents.storage.settings")
    def test_operational_error_falls_back(self, mock_settings, mock_apps):
        from django.db.utils import OperationalError

        mock_apps.ready = True
        mock_settings.DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT = "/fallback"
        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = OperationalError("table missing")
        with patch("apps.core.interfaces.ServiceLocator") as mock_loc:
            mock_loc.get_system_config_service.return_value = mock_svc
            result = get_configured_private_docx_templates_root()
        assert result == "/fallback"


class TestGetPrivateDocxTemplatesRoot:
    @patch("apps.documents.storage.get_configured_private_docx_templates_root", return_value="")
    def test_none_when_empty(self, _):
        assert get_private_docx_templates_root() is None

    @patch("apps.documents.storage.get_configured_private_docx_templates_root", return_value="/some/path")
    def test_returns_path_when_configured(self, _):
        result = get_private_docx_templates_root()
        assert result is not None


class TestGetDocxTemplatesSource:
    @patch("apps.documents.storage.get_private_docx_templates_root", return_value=None)
    def test_public(self, _):
        assert get_docx_templates_source() == "public"

    @patch("apps.documents.storage.get_private_docx_templates_root", return_value=RealPath("/private"))
    def test_private(self, _):
        assert get_docx_templates_source() == "private"


class TestResolveDocxTemplatePath:
    def test_absolute_path_returned_as_is(self):
        result = resolve_docx_template_path("/absolute/path/file.docx")
        assert str(result) == "/absolute/path/file.docx"

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_relative_within_root(self, mock_root, tmp_path):
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "test.docx").write_bytes(b"fake")
        mock_root.return_value = template_dir
        result = resolve_docx_template_path("test.docx")
        assert "test.docx" in str(result)

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_path_traversal_raises(self, mock_root, tmp_path):
        mock_root.return_value = tmp_path / "templates"
        with pytest.raises(ValueError, match="越界"):
            resolve_docx_template_path("../../etc/passwd")


class TestDocumentTemplateStorage:
    def test_url_returns_empty(self, tmp_path):
        with patch("apps.documents.storage.get_docx_templates_root", return_value=tmp_path):
            storage = DocumentTemplateStorage()
        assert storage.url("anything") == ""

    def test_path(self, tmp_path):
        with patch("apps.documents.storage.get_docx_templates_root", return_value=tmp_path):
            storage = DocumentTemplateStorage()
        assert "test.docx" in storage.path("test.docx")

    def test_exists_false(self, tmp_path):
        with patch("apps.documents.storage.get_docx_templates_root", return_value=tmp_path):
            storage = DocumentTemplateStorage()
        assert storage.exists("nonexistent.docx") is False

    def test_size(self, tmp_path):
        (tmp_path / "test.txt").write_bytes(b"hello")
        with patch("apps.documents.storage.get_docx_templates_root", return_value=tmp_path):
            storage = DocumentTemplateStorage()
        assert storage.size("test.txt") == 5

    def test_save_existing_prefix(self, tmp_path):
        (tmp_path / "sub" / "test.docx").mkdir(parents=True)
        (tmp_path / "sub" / "test.docx" / "test.docx").write_bytes(b"data")
        with patch("apps.documents.storage.get_docx_templates_root", return_value=tmp_path):
            storage = DocumentTemplateStorage()
            # Create the user custom dir
            (tmp_path / USER_CUSTOM_TEMPLATE_DIR).mkdir(exist_ok=True)
            result = storage.save("_EXISTING_:sub/test.docx/test.docx", None)
            assert result == "sub/test.docx/test.docx"


class TestListDocxTemplatesFiles:
    @patch("apps.documents.storage.get_docx_templates_root")
    def test_empty_when_root_not_exists(self, mock_root, tmp_path):
        mock_root.return_value = tmp_path / "nonexistent"
        assert list_docx_templates_files() == []

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_lists_docx_files(self, mock_root, tmp_path):
        (tmp_path / "dir1").mkdir()
        (tmp_path / "dir1" / "a.docx").write_bytes(b"fake")
        (tmp_path / "dir1" / "b.pdf").write_bytes(b"fake")
        # Add user custom dir file that should be skipped
        (tmp_path / USER_CUSTOM_TEMPLATE_DIR).mkdir()
        (tmp_path / USER_CUSTOM_TEMPLATE_DIR / "c.docx").write_bytes(b"fake")
        mock_root.return_value = tmp_path
        result = list_docx_templates_files()
        assert len(result) == 1
        assert result[0][0] == "dir1/a.docx"
