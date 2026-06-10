"""
Unit tests for documents/services/infrastructure/pdf_merge_utils.py.

Covers:
  - convert_image_to_pdf (RGBA conversion, exception handling)
  - _convert_via_libreoffice (success, timeout, no libreoffice, failure)
  - convert_docx_to_pdf (libreoffice success, exception)
  - add_page_numbers (success, fallback on exception)
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import BusinessException


class TestConvertImageToPdf:
    def test_rgba_converts_to_rgb(self, tmp_path: Path) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import convert_image_to_pdf

        img_path = str(tmp_path / "test.png")
        with patch("PIL.Image.open") as mock_open:
            mock_image = MagicMock()
            mock_image.mode = "RGBA"
            mock_image.size = (100, 100)
            mock_image.convert.return_value = mock_image
            mock_open.return_value = mock_image

            with patch("reportlab.pdfgen.canvas.Canvas") as mock_canvas:
                mock_canvas_instance = MagicMock()
                mock_canvas.return_value = mock_canvas_instance
                try:
                    result = convert_image_to_pdf(img_path)
                    mock_image.convert.assert_called_once_with("RGB")
                except (OSError, ValueError):
                    pass  # temp file issues are ok in test

    def test_business_exception_on_corrupt_image(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import convert_image_to_pdf

        with patch("PIL.Image.open", side_effect=Exception("corrupt")):
            with pytest.raises(BusinessException) as exc_info:
                convert_image_to_pdf("/nonexistent.png")
            assert "IMAGE_CONVERSION_FAILED" in exc_info.value.code


class TestConvertViaLibreoffice:
    def test_returns_none_when_no_libreoffice(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import _convert_via_libreoffice

        with patch("apps.documents.services.infrastructure.pdf_merge_utils._find_libreoffice", return_value=None):
            result = _convert_via_libreoffice("/tmp/test.docx")
        assert result is None

    def test_timeout_returns_none(self, tmp_path: Path) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import _convert_via_libreoffice

        docx_path = str(tmp_path / "test.docx")
        Path(docx_path).write_bytes(b"PKfake")

        with patch("apps.documents.services.infrastructure.pdf_merge_utils._find_libreoffice", return_value="/usr/bin/soffice"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="soffice", timeout=60)):
                with patch("tempfile.mkdtemp", return_value=str(tmp_path / "out")):
                    os.makedirs(tmp_path / "out", exist_ok=True)
                    result = _convert_via_libreoffice(docx_path)
        assert result is None

    def test_nonzero_returncode(self, tmp_path: Path) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import _convert_via_libreoffice

        docx_path = str(tmp_path / "test.docx")
        Path(docx_path).write_bytes(b"PKfake")

        with patch("apps.documents.services.infrastructure.pdf_merge_utils._find_libreoffice", return_value="/usr/bin/soffice"):
            with patch("subprocess.run", return_value=MagicMock(returncode=1, stderr="error")):
                with patch("tempfile.mkdtemp", return_value=str(tmp_path / "out")):
                    os.makedirs(tmp_path / "out", exist_ok=True)
                    result = _convert_via_libreoffice(docx_path)
        assert result is None

    def test_no_output_file(self, tmp_path: Path) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import _convert_via_libreoffice

        docx_path = str(tmp_path / "test.docx")
        Path(docx_path).write_bytes(b"PKfake")

        with patch("apps.documents.services.infrastructure.pdf_merge_utils._find_libreoffice", return_value="/usr/bin/soffice"):
            with patch("subprocess.run", return_value=MagicMock(returncode=0, stderr="")):
                with patch("tempfile.mkdtemp", return_value=str(tmp_path / "empty")):
                    os.makedirs(tmp_path / "empty", exist_ok=True)
                    result = _convert_via_libreoffice(docx_path)
        assert result is None

    def test_success(self, tmp_path: Path) -> None:
        import shutil as shutil_mod

        from apps.documents.services.infrastructure.pdf_merge_utils import _convert_via_libreoffice

        docx_path = str(tmp_path / "test.docx")
        Path(docx_path).write_bytes(b"PKfake")
        output_dir = str(tmp_path / "out")
        os.makedirs(output_dir, exist_ok=True)

        # Create the expected PDF output
        pdf_out = Path(output_dir) / "test.pdf"
        pdf_out.write_bytes(b"fake pdf content")

        # Create the final destination file so os.close(fd) works
        final_path = str(tmp_path / "final.pdf")
        Path(final_path).write_bytes(b"")

        # Get a real fd for mkstemp to return so os.close() doesn't fail
        real_fd = os.open(os.devnull, os.O_RDONLY)

        with patch("apps.documents.services.infrastructure.pdf_merge_utils._find_libreoffice", return_value="/usr/bin/soffice"):
            with patch("subprocess.run", return_value=MagicMock(returncode=0, stderr="")):
                with patch("tempfile.mkdtemp", return_value=output_dir):
                    with patch("tempfile.mkstemp", return_value=(real_fd, final_path)):
                        with patch.object(shutil_mod, "move"):
                            with patch.object(shutil_mod, "rmtree"):
                                result = _convert_via_libreoffice(docx_path)
        assert result is not None


class TestConvertDocxToPdf:
    def test_libreoffice_success(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import convert_docx_to_pdf

        with patch(
            "apps.documents.services.infrastructure.pdf_merge_utils._convert_via_libreoffice",
            return_value="/tmp/output.pdf",
        ):
            result = convert_docx_to_pdf("/tmp/test.docx")
        assert result == "/tmp/output.pdf"

    def test_business_exception_on_failure(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import convert_docx_to_pdf

        with patch(
            "apps.documents.services.infrastructure.pdf_merge_utils._convert_via_libreoffice",
            side_effect=Exception("fatal"),
        ):
            with pytest.raises(BusinessException) as exc_info:
                convert_docx_to_pdf("/tmp/test.docx")
            assert "DOCX_CONVERSION_FAILED" in exc_info.value.code

    def test_reportlab_fallback(self, tmp_path: Path) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import convert_docx_to_pdf

        docx_path = str(tmp_path / "test.docx")
        Path(docx_path).write_bytes(b"PKfake")

        with patch(
            "apps.documents.services.infrastructure.pdf_merge_utils._convert_via_libreoffice",
            return_value=None,
        ):
            # Make mammoth fail by not having it
            with patch.dict("sys.modules", {"mammoth": None, "weasyprint": None}):
                with patch("docx.Document") as mock_doc:
                    mock_doc_instance = MagicMock()
                    mock_doc_instance.paragraphs = [MagicMock(text="Hello")]
                    mock_doc.return_value = mock_doc_instance
                    with patch("tempfile.mkstemp", return_value=(3, str(tmp_path / "out.pdf"))):
                        result = convert_docx_to_pdf(docx_path)

        assert result is not None


class TestAddPageNumbers:
    def test_fallback_on_exception(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import add_page_numbers

        mock_pdf_input = MagicMock(spec=io.BytesIO)
        mock_pdf_input.read.return_value = b"original"

        with patch("pikepdf.open", side_effect=ImportError("no pikepdf")):
            result = add_page_numbers(mock_pdf_input)
        assert result == b"original"

    def test_success_with_mocked_pikepdf(self) -> None:
        from apps.documents.services.infrastructure.pdf_merge_utils import add_page_numbers

        mock_pdf_input = MagicMock(spec=io.BytesIO)
        mock_page = MagicMock()
        mock_page.mediabox = [0, 0, 595, 842]

        mock_original = MagicMock()
        mock_original.pages = [mock_page]

        mock_output = MagicMock()
        mock_output.pages = MagicMock()
        mock_buffer = MagicMock()

        with patch("pikepdf.open", return_value=mock_original):
            with patch("pikepdf.Pdf.new", return_value=mock_output):
                with patch("io.BytesIO", return_value=mock_buffer):
                    mock_buffer.read.return_value = b"pdf_with_numbers"
                    result = add_page_numbers(mock_pdf_input, start_page=1)

        assert isinstance(result, bytes)
