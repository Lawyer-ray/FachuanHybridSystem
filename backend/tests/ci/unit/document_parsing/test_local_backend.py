"""LocalBackend 测试（mock fitz）"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.document_parsing.protocols.document_parser_protocol import (
    ParsedDocument,
    TextExtractionResult,
)
from apps.document_parsing.services.backends.local_backend import LocalBackend

_PATCH_PREFIX = "apps.document_parsing.services.backends.local_backend"


class TestGetSupportedFormats:
    def test_returns_expected_formats(self) -> None:
        backend = LocalBackend()
        fmts = backend.get_supported_formats()
        assert "pdf" in fmts
        assert "jpg" in fmts
        assert "png" in fmts
        assert "bmp" in fmts
        assert "tiff" in fmts


class TestParseDocument:
    def test_file_not_found(self) -> None:
        backend = LocalBackend()
        with pytest.raises(FileNotFoundError):
            backend.parse_document("/nonexistent/file.pdf")

    def test_unsupported_type_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "test.xyz"
        f.write_bytes(b"data")
        backend = LocalBackend()
        with pytest.raises(ValueError, match="不支持的文件类型"):
            backend.parse_document(str(f), file_type="xyz")

    def test_pdf_delegates_to_parse_pdf(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = LocalBackend()
        expected = ParsedDocument(text="parsed", parse_method="pymupdf")

        with patch.object(backend, "_parse_pdf", return_value=expected) as mock_pdf:
            result = backend.parse_document(str(pdf), file_type="pdf", extract_images=True)

        mock_pdf.assert_called_once_with(str(pdf), extract_images=True)
        assert result.text == "parsed"

    def test_image_delegates_to_parse_image(self, tmp_path: Path) -> None:
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0")

        backend = LocalBackend()
        expected = ParsedDocument(text="ocr text", parse_method="rapidocr")

        with patch.object(backend, "_parse_image", return_value=expected) as mock_img:
            result = backend.parse_document(str(img), file_type="jpg")

        mock_img.assert_called_once_with(str(img))
        assert result.text == "ocr text"

    def test_png_delegates_to_parse_image(self, tmp_path: Path) -> None:
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG")

        backend = LocalBackend()
        expected = ParsedDocument(text="ocr", parse_method="rapidocr")

        with patch.object(backend, "_parse_image", return_value=expected) as mock_img:
            result = backend.parse_document(str(img), file_type="png")

        mock_img.assert_called_once_with(str(img))


class TestParsePdf:
    def test_with_fitz(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        # Mock fitz — it's imported locally inside _parse_pdf via `import fitz`
        mock_page = MagicMock()
        mock_page.get_text.return_value = "page text"

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        import sys
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc
        sys.modules["fitz"] = mock_fitz

        try:
            backend = LocalBackend()
            result = backend._parse_pdf(str(pdf))

            assert isinstance(result, ParsedDocument)
            assert "page text" in result.text
            assert result.parse_method == "pymupdf"
        finally:
            sys.modules.pop("fitz", None)

    def test_import_error(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        import sys
        # Remove fitz from sys.modules and make it fail to import
        saved = sys.modules.pop("fitz", None)
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "fitz":
                raise ImportError("no fitz")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = mock_import
        try:
            backend = LocalBackend()
            with pytest.raises(RuntimeError, match="未安装 PyMuPDF"):
                backend._parse_pdf(str(pdf))
        finally:
            builtins.__import__ = original_import
            if saved is not None:
                sys.modules["fitz"] = saved


class TestParseImage:
    def test_ocr_service_unavailable(self, tmp_path: Path) -> None:
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0")

        backend = LocalBackend()
        backend._ocr_service = None

        with patch.object(backend, "_get_ocr_service", return_value=None):
            with pytest.raises(RuntimeError, match="OCR 服务不可用"):
                backend._parse_image(str(img))

    def test_ocr_success(self, tmp_path: Path) -> None:
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0")

        mock_ocr = MagicMock()
        mock_ocr.recognize.return_value = "line1\nline2"

        backend = LocalBackend()
        with patch.object(backend, "_get_ocr_service", return_value=mock_ocr):
            result = backend._parse_image(str(img))

        assert "line1" in result.text
        assert "line2" in result.text
        assert result.parse_method == "rapidocr"

    def test_ocr_empty_result(self, tmp_path: Path) -> None:
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0")

        mock_ocr = MagicMock()
        mock_ocr.recognize.return_value = None

        backend = LocalBackend()
        with patch.object(backend, "_get_ocr_service", return_value=mock_ocr):
            result = backend._parse_image(str(img))

        assert result.text == ""


class TestExtractText:
    def test_success(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = LocalBackend()
        mock_result = ParsedDocument(text="extracted text", parse_method="pymupdf")

        with patch.object(backend, "parse_document", return_value=mock_result):
            result = backend.extract_text(str(pdf))

        assert isinstance(result, TextExtractionResult)
        assert result.success is True
        assert result.text == "extracted text"
        assert result.method == "pymupdf"

    def test_max_length(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = LocalBackend()
        mock_result = ParsedDocument(text="a" * 500, parse_method="pymupdf")

        with patch.object(backend, "parse_document", return_value=mock_result):
            result = backend.extract_text(str(pdf), max_length=10)

        assert len(result.text) == 10

    def test_failure(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = LocalBackend()
        with patch.object(backend, "parse_document", side_effect=Exception("bad")):
            result = backend.extract_text(str(pdf))

        assert result.success is False
        assert "bad" in result.metadata["error"]
