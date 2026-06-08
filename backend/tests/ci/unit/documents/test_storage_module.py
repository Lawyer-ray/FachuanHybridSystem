"""Tests for documents storage module: DocumentTemplateStorage, path resolution, list_docx_templates_files."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.documents.storage import (
    DocumentTemplateStorage,
    USER_CUSTOM_TEMPLATE_DIR,
    get_docx_templates_root,
    get_docx_templates_source,
    get_private_docx_templates_root,
    get_public_docx_templates_root,
    list_docx_templates_files,
    resolve_docx_template_path,
)


class TestGetPublicDocxTemplatesRoot:
    @patch("apps.documents.storage.settings")
    def test_returns_path(self, mock_settings: MagicMock) -> None:
        mock_settings.BASE_DIR = "/app/backend"
        result = get_public_docx_templates_root()
        assert "docx_templates" in str(result)


class TestGetPrivateDocxTemplatesRoot:
    @patch("apps.documents.storage.get_configured_private_docx_templates_root", return_value="")
    def test_returns_none_when_empty(self, mock_config: MagicMock) -> None:
        result = get_private_docx_templates_root()
        assert result is None

    @patch("apps.documents.storage.get_configured_private_docx_templates_root", return_value="/private/templates")
    def test_returns_path_when_configured(self, mock_config: MagicMock) -> None:
        result = get_private_docx_templates_root()
        assert result is not None
        assert "templates" in str(result)


class TestGetDocxTemplatesSource:
    @patch("apps.documents.storage.get_private_docx_templates_root", return_value=None)
    def test_public(self, mock: MagicMock) -> None:
        assert get_docx_templates_source() == "public"

    @patch("apps.documents.storage.get_private_docx_templates_root", return_value=Path("/private"))
    def test_private(self, mock: MagicMock) -> None:
        assert get_docx_templates_source() == "private"


class TestGetDocxTemplatesRoot:
    @patch("apps.documents.storage.get_private_docx_templates_root", return_value=Path("/private"))
    def test_uses_private_when_available(self, mock: MagicMock) -> None:
        result = get_docx_templates_root()
        assert str(result) == "/private"

    @patch("apps.documents.storage.get_private_docx_templates_root", return_value=None)
    @patch("apps.documents.storage.get_public_docx_templates_root", return_value=Path("/public"))
    def test_falls_back_to_public(self, mock_pub: MagicMock, mock_priv: MagicMock) -> None:
        result = get_docx_templates_root()
        assert str(result) == "/public"


class TestResolveDocxTemplatePath:
    def test_absolute_path_returned_as_is(self) -> None:
        result = resolve_docx_template_path("/absolute/path/template.docx")
        assert str(result) == "/absolute/path/template.docx"

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_relative_path_resolved(self, mock_root: MagicMock) -> None:
        tmp = tempfile.mkdtemp()
        mock_root.return_value = Path(tmp)
        # Create the file so relative_to check works
        sub = Path(tmp) / "templates"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "test.docx").touch()
        result = resolve_docx_template_path("templates/test.docx")
        assert "test.docx" in str(result)

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_path_traversal_raises(self, mock_root: MagicMock) -> None:
        tmp = tempfile.mkdtemp()
        mock_root.return_value = Path(tmp)
        with pytest.raises(ValueError, match="越界"):
            resolve_docx_template_path("../../../etc/passwd")

    def test_strips_whitespace(self) -> None:
        result = resolve_docx_template_path("/absolute/path.docx  ")
        assert str(result) == "/absolute/path.docx"


class TestListDocxTemplatesFiles:
    @patch("apps.documents.storage.get_docx_templates_root")
    def test_nonexistent_root(self, mock_root: MagicMock) -> None:
        mock_root.return_value = Path("/nonexistent/path")
        assert list_docx_templates_files() == []

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_lists_docx_files(self, mock_root: MagicMock) -> None:
        tmp = tempfile.mkdtemp()
        root = Path(tmp)
        mock_root.return_value = root
        # Create some docx files
        (root / "contract.docx").touch()
        (root / "subdir").mkdir()
        (root / "subdir" / "nested.docx").touch()
        # Create a user custom dir file (should be excluded)
        custom = root / USER_CUSTOM_TEMPLATE_DIR
        custom.mkdir()
        (custom / "user_template.docx").touch()
        # Create non-docx file (should be excluded)
        (root / "readme.txt").touch()

        result = list_docx_templates_files()
        names = [r[0] for r in result]
        assert "contract.docx" in names
        assert any("nested.docx" in n for n in names)
        assert not any("user_template" in n for n in names)


class TestDocumentTemplateStorage:
    @patch("apps.documents.storage.get_docx_templates_root")
    def test_url_returns_empty(self, mock_root: MagicMock) -> None:
        mock_root.return_value = Path("/tmp/test_templates")
        storage = DocumentTemplateStorage()
        assert storage.url("anything") == ""

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_path(self, mock_root: MagicMock) -> None:
        mock_root.return_value = Path("/tmp/test_templates")
        storage = DocumentTemplateStorage()
        result = storage.path("sub/test.docx")
        assert "test.docx" in result

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_save_existing_prefix(self, mock_root: MagicMock) -> None:
        tmp = tempfile.mkdtemp()
        root = Path(tmp)
        mock_root.return_value = root
        (root / "existing.docx").touch()
        storage = DocumentTemplateStorage()
        result = storage.save("_EXISTING_:existing.docx", None)
        assert result == "existing.docx"

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_save_normal_file(self, mock_root: MagicMock) -> None:
        from django.core.files.base import ContentFile

        tmp = tempfile.mkdtemp()
        root = Path(tmp)
        mock_root.return_value = root
        storage = DocumentTemplateStorage()
        content = ContentFile(b"test content", name="new_template.docx")
        result = storage.save("new_template.docx", content)
        assert "new_template.docx" in result

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_exists(self, mock_root: MagicMock) -> None:
        tmp = tempfile.mkdtemp()
        root = Path(tmp)
        mock_root.return_value = root
        (root / "exists.docx").touch()
        storage = DocumentTemplateStorage()
        assert storage.exists("exists.docx") is True
        assert storage.exists("nope.docx") is False

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_size(self, mock_root: MagicMock) -> None:
        tmp = tempfile.mkdtemp()
        root = Path(tmp)
        mock_root.return_value = root
        p = root / "sized.docx"
        p.write_bytes(b"hello world")
        storage = DocumentTemplateStorage()
        assert storage.size("sized.docx") == 11

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_save_existing_prefix_file_not_found(self, mock_root: MagicMock) -> None:
        """When _EXISTING_ prefix is used but file doesn't exist, normal save proceeds."""
        from django.core.files.base import ContentFile

        tmp = tempfile.mkdtemp()
        root = Path(tmp)
        mock_root.return_value = root
        storage = DocumentTemplateStorage()
        content = ContentFile(b"data", name="nonexistent.docx")
        result = storage.save("_EXISTING_:nonexistent.docx", content)
        assert result  # some path returned

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_save_non_docx_warning(self, mock_root: MagicMock) -> None:
        from django.core.files.base import ContentFile

        tmp = tempfile.mkdtemp()
        root = Path(tmp)
        mock_root.return_value = root
        storage = DocumentTemplateStorage()
        content = ContentFile(b"data", name="file.txt")
        result = storage.save("file.txt", content)
        assert result  # still saves

    @patch("apps.documents.storage.get_docx_templates_root")
    def test_save_none_name(self, mock_root: MagicMock) -> None:
        from django.core.files.base import ContentFile

        tmp = tempfile.mkdtemp()
        root = Path(tmp)
        mock_root.return_value = root
        storage = DocumentTemplateStorage()
        content = ContentFile(b"data", name="unnamed.docx")
        result = storage.save(None, content)
        assert result  # uses "unnamed.docx"
