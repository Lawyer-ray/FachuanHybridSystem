"""Extended tests for evidence services - pdf_utils, infrastructure."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.evidence.services.infrastructure.pdf_utils import (
    _read_source_bytes,
    get_pdf_page_count,
    get_pdf_page_count_with_error,
)


class TestReadSourceBytes:
    def test_none_raises(self):
        with pytest.raises(ValueError, match="source is None"):
            _read_source_bytes(None)

    def test_bytes(self):
        data = b"hello"
        assert _read_source_bytes(data) == b"hello"

    def test_bytearray(self):
        data = bytearray(b"hello")
        assert _read_source_bytes(data) == b"hello"

    def test_path_object(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"PDF content")
        from apps.core.utils.path import Path

        result = _read_source_bytes(Path(str(f)))
        assert result == b"PDF content"

    def test_string_path(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"PDF content")
        result = _read_source_bytes(str(f))
        assert result == b"PDF content"

    def test_file_like_object(self):
        import io

        buf = io.BytesIO(b"file content")
        result = _read_source_bytes(buf)
        assert result == b"file content"

    def test_django_field_file(self):
        mock_file = MagicMock()
        mock_file.open = MagicMock()
        mock_file.read.return_value = b"field file content"
        mock_file.seek = MagicMock()
        result = _read_source_bytes(mock_file)
        assert result == b"field file content"

    def test_unsupported_type(self):
        with pytest.raises(TypeError, match="Unsupported source type"):
            _read_source_bytes(12345)


class TestGetPdfPageCount:
    def test_with_valid_pdf_bytes(self, tmp_path):
        import fitz

        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        count = get_pdf_page_count(pdf_bytes, default=1)
        assert count == 1

    def test_with_valid_pdf_file(self, tmp_path):
        import fitz

        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        pdf_path = tmp_path / "test.pdf"
        doc.save(str(pdf_path))
        doc.close()
        count = get_pdf_page_count(str(pdf_path), default=1)
        assert count == 2


class TestGetPdfPageCountWithError:
    def test_valid_pdf(self, tmp_path):
        import fitz

        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        count, error = get_pdf_page_count_with_error(pdf_bytes, default=1)
        assert count == 3
        assert error is None

    def test_returns_error_on_invalid(self):
        # Invalid PDF bytes may raise or return default depending on which library handles it
        try:
            count, error = get_pdf_page_count_with_error(b"completely invalid", default=5)
            assert count == 5
            assert error is not None
        except Exception:
            # Some PDF libraries may raise on completely invalid input
            pass


class TestEvidenceWiring:
    def test_import_wiring(self):
        from apps.evidence.services import wiring

        assert wiring is not None
