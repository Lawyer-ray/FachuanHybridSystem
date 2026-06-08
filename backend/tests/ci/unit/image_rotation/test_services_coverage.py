"""Coverage tests for image_rotation services: transform, export, storage, rename_ocr."""
from __future__ import annotations

import io
import pytest
from unittest.mock import MagicMock, patch


class TestPdfTransform:
    def test_apply_rotation_0_jpeg(self):
        from apps.image_rotation.services.transform.pdf_transform import apply_rotation_for_pdf
        from PIL import Image
        img = Image.new("RGB", (100, 100), "red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        result = apply_rotation_for_pdf(buf.getvalue(), 0)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_apply_rotation_90(self):
        from apps.image_rotation.services.transform.pdf_transform import apply_rotation_for_pdf
        from PIL import Image
        img = Image.new("RGB", (100, 100), "blue")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        result = apply_rotation_for_pdf(buf.getvalue(), 90)
        assert isinstance(result, bytes)

    def test_apply_rotation_180(self):
        from apps.image_rotation.services.transform.pdf_transform import apply_rotation_for_pdf
        from PIL import Image
        img = Image.new("RGB", (100, 100), "green")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        result = apply_rotation_for_pdf(buf.getvalue(), 180)
        assert isinstance(result, bytes)

    def test_apply_rotation_invalid(self):
        from apps.image_rotation.services.transform.pdf_transform import apply_rotation_for_pdf
        from PIL import Image
        img = Image.new("RGB", (100, 100), "white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        result = apply_rotation_for_pdf(buf.getvalue(), 45)
        assert isinstance(result, bytes)

    def test_ensure_rgb_rgba(self):
        from apps.image_rotation.services.transform.pdf_transform import _ensure_rgb
        from PIL import Image
        img = Image.new("RGBA", (50, 50), (255, 0, 0, 128))
        result = _ensure_rgb(img)
        assert result.mode == "RGB"


class TestZipExporter:
    def test_get_unique_filename_no_conflict(self):
        from apps.image_rotation.services.export.zip_exporter import _get_unique_filename
        used = {}
        result = _get_unique_filename("test.jpg", used)
        assert result == "test.jpg"

    def test_get_unique_filename_with_conflict(self):
        from apps.image_rotation.services.export.zip_exporter import _get_unique_filename
        used = {"test.jpg": 1}
        result = _get_unique_filename("test.jpg", used)
        assert result == "test_1.jpg"

    def test_get_unique_filename_empty(self):
        from apps.image_rotation.services.export.zip_exporter import _get_unique_filename
        used = {}
        result = _get_unique_filename("", used)
        assert result.endswith(".jpg")

    def test_get_unique_filename_no_ext(self):
        from apps.image_rotation.services.export.zip_exporter import _get_unique_filename
        used = {"file": 1}
        result = _get_unique_filename("file", used)
        assert result == "file_1"
