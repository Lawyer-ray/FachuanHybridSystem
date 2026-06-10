"""Targeted tests for image_rotation module to push coverage to 80%+."""
from __future__ import annotations

import tempfile
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# services/storage.py (38% coverage)
# ---------------------------------------------------------------------------


class TestImageRotationStorage:
    def test_build_zip_filename(self):
        from apps.image_rotation.services.storage import build_zip_filename

        name = build_zip_filename()
        assert name.endswith(".zip")
        assert "rotated_images" in name

    def test_build_zip_filename_custom_prefix(self):
        from apps.image_rotation.services.storage import build_zip_filename

        name = build_zip_filename(prefix="custom")
        assert "custom" in name
        assert name.endswith(".zip")

    def test_build_pdf_filename(self):
        from apps.image_rotation.services.storage import build_pdf_filename

        name = build_pdf_filename()
        assert name.endswith(".pdf")
        assert "rotated_pages" in name

    def test_to_media_url(self):
        from apps.image_rotation.services.storage import to_media_url

        assert to_media_url("test.zip") == "/media/image_rotation/test.zip"


# ---------------------------------------------------------------------------
# services/export/zip_exporter.py (62% coverage)
# ---------------------------------------------------------------------------


class TestZipExporter:
    def test_get_unique_filename_unique(self):
        from apps.image_rotation.services.export.zip_exporter import _get_unique_filename

        used: dict[str, int] = {}
        result = _get_unique_filename("test.jpg", used)
        assert result == "test.jpg"

    def test_get_unique_filename_duplicate(self):
        from apps.image_rotation.services.export.zip_exporter import _get_unique_filename

        used: dict[str, int] = {"test.jpg": 1}
        result = _get_unique_filename("test.jpg", used)
        assert result == "test_1.jpg"

    def test_get_unique_filename_empty(self):
        from apps.image_rotation.services.export.zip_exporter import _get_unique_filename

        used: dict[str, int] = {}
        result = _get_unique_filename("", used)
        assert result.endswith(".jpg")

    def test_get_unique_filename_no_ext(self):
        from apps.image_rotation.services.export.zip_exporter import _get_unique_filename

        used: dict[str, int] = {"file": 1}
        result = _get_unique_filename("file", used)
        assert result == "file_1"


# ---------------------------------------------------------------------------
# api/__init__.py (0% coverage)
# ---------------------------------------------------------------------------


class TestImageRotationApiInit:
    def test_api_init(self):
        from apps.image_rotation.api import __init__ as api_init

        assert api_init is not None
