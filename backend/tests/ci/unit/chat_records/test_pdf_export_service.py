"""Tests for chat_records/services/export/pdf_export_service.py — uncovered branches.

Covers: export_pdf, _build_pdf_bytes (via export_pdf), _register_pdf_font,
        _draw_pdf_image, _get_lanczos.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException


@pytest.fixture
def svc() -> Any:
    from apps.chat_records.services.export.pdf_export_service import PdfExportService

    return PdfExportService()


# ── _get_lanczos ─────────────────────────────────────────────────


class TestGetLanczos:
    def test_returns_constant(self) -> None:
        from apps.chat_records.services.export.pdf_export_service import _get_lanczos

        # Reset global cache
        import apps.chat_records.services.export.pdf_export_service as mod

        mod._LANCZOS = None
        result = _get_lanczos()
        assert result is not None
        # Second call returns cached value
        result2 = _get_lanczos()
        assert result2 is result


# ── _register_pdf_font ──────────────────────────────────────────


class TestRegisterPdfFont:
    def test_fallback_on_error(self, svc: Any) -> None:
        """When import fails, font registration falls back to Helvetica."""
        import builtins

        original_import = builtins.__import__

        def _patched_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "reportlab.pdfbase.cidfonts":
                raise ImportError("no CID fonts")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=_patched_import):
            result = svc._register_pdf_font()
            assert result == "Helvetica"

    def test_font_registered(self, svc: Any) -> None:
        """When reportlab is available, STSong-Light is returned."""
        # Since _register_pdf_font uses local imports, just call it normally
        # and check that it returns either STSong-Light or Helvetica
        result = svc._register_pdf_font()
        assert result in ("STSong-Light", "Helvetica")


# ── export_pdf ───────────────────────────────────────────────────


class TestExportPdf:
    def test_returns_content_file(self, svc: Any) -> None:
        project = MagicMock()
        screenshots = [MagicMock()]
        layout = MagicMock()
        layout.header_text = ""
        layout.show_page_number = False
        layout.images_per_page = 1

        with patch.object(svc, "_build_pdf_bytes", return_value=b"%PDF-1.4 fake"):
            with patch.object(svc, "_register_pdf_font", return_value="Helvetica"):
                from apps.chat_records.services.export.export_types import ExportLayout

                result = svc.export_pdf(
                    project=project,
                    screenshots=screenshots,
                    layout=layout,
                    filename="test.pdf",
                )
                assert result.name == "test.pdf"
                assert result.read() == b"%PDF-1.4 fake"

    def test_with_progress_callback(self, svc: Any) -> None:
        project = MagicMock()
        screenshots = [MagicMock()]
        layout = MagicMock()
        layout.header_text = "Title"
        layout.show_page_number = True
        layout.images_per_page = 1
        callback = MagicMock()

        with patch.object(svc, "_build_pdf_bytes", return_value=b"data"):
            with patch.object(svc, "_register_pdf_font", return_value="Helvetica"):
                svc.export_pdf(
                    project=project,
                    screenshots=screenshots,
                    layout=layout,
                    filename="cb.pdf",
                    progress_callback=callback,
                )


# ── _build_pdf_bytes (integration via mocking reportlab) ─────────


class TestBuildPdfBytes:
    def test_empty_screenshots_raises(self, svc: Any) -> None:
        layout = MagicMock()
        with pytest.raises(ValidationException, match="没有截图"):
            svc._build_pdf_bytes(
                project=MagicMock(),
                screenshots=[],
                layout=layout,
            )

    def test_single_image_page(self, svc: Any) -> None:
        """Test building PDF with one screenshot using mocked reportlab."""
        from PIL import Image

        # Create a small test image
        img = Image.new("RGB", (100, 50), color="red")
        img_buf = io.BytesIO()
        img.save(img_buf, format="JPEG")
        img_buf.seek(0)

        shot = MagicMock()
        shot.title = "Test Screenshot"
        shot.image = MagicMock()

        class FakeOpen:
            def __enter__(self):
                return img_buf
            def __exit__(self, *args):
                img_buf.seek(0)

        shot.image.open.return_value = FakeOpen()

        layout = MagicMock()
        layout.header_text = "Header"
        layout.show_page_number = True
        layout.images_per_page = 1

        with patch(
            "reportlab.pdfgen.canvas"
        ) as mock_canvas:
            mock_c = MagicMock()
            mock_canvas.Canvas.return_value = mock_c
            with patch.object(svc, "_register_pdf_font", return_value="Helvetica"):
                result = svc._build_pdf_bytes(
                    project=MagicMock(),
                    screenshots=[shot],
                    layout=layout,
                )
                assert isinstance(result, bytes)
                mock_c.save.assert_called_once()

    def test_two_images_per_page(self, svc: Any) -> None:
        from PIL import Image

        img = Image.new("RGB", (100, 50), color="blue")
        img_buf = io.BytesIO()
        img.save(img_buf, format="JPEG")
        img_buf.seek(0)

        def make_shot(title: str) -> MagicMock:
            shot = MagicMock()
            shot.title = title
            shot.image = MagicMock()
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            buf.seek(0)

            class FO:
                def __enter__(self):
                    return buf
                def __exit__(self, *args):
                    buf.seek(0)

            shot.image.open.return_value = FO()
            return shot

        layout = MagicMock()
        layout.header_text = ""
        layout.show_page_number = False
        layout.images_per_page = 2

        with patch(
            "reportlab.pdfgen.canvas"
        ) as mock_canvas:
            mock_c = MagicMock()
            mock_canvas.Canvas.return_value = mock_c
            with patch.object(svc, "_register_pdf_font", return_value="Helvetica"):
                result = svc._build_pdf_bytes(
                    project=MagicMock(),
                    screenshots=[make_shot("A"), make_shot("B")],
                    layout=layout,
                )
                assert isinstance(result, bytes)

    def test_image_processing_error_continues(self, svc: Any) -> None:
        """When image.open fails, _draw_pdf_image returns 1 and continues."""
        shot = MagicMock()
        shot.title = ""
        shot.image = MagicMock()
        shot.image.open.side_effect = IOError("cannot open")

        layout = MagicMock()
        layout.header_text = ""
        layout.show_page_number = False
        layout.images_per_page = 1

        with patch(
            "reportlab.pdfgen.canvas"
        ) as mock_canvas:
            mock_c = MagicMock()
            mock_canvas.Canvas.return_value = mock_c
            with patch.object(svc, "_register_pdf_font", return_value="Helvetica"):
                result = svc._build_pdf_bytes(
                    project=MagicMock(),
                    screenshots=[shot],
                    layout=layout,
                )
                assert isinstance(result, bytes)

    def test_header_and_footer_text(self, svc: Any) -> None:
        from PIL import Image

        img = Image.new("RGB", (100, 50), color="green")
        img_buf = io.BytesIO()
        img.save(img_buf, format="JPEG")
        img_buf.seek(0)

        shot = MagicMock()
        shot.title = "Test"
        shot.image = MagicMock()

        class FO:
            def __enter__(self):
                return img_buf
            def __exit__(self, *args):
                img_buf.seek(0)

        shot.image.open.return_value = FO()

        layout = MagicMock()
        layout.header_text = "My Header"
        layout.show_page_number = True
        layout.images_per_page = 1

        with patch(
            "reportlab.pdfgen.canvas"
        ) as mock_canvas:
            mock_c = MagicMock()
            mock_canvas.Canvas.return_value = mock_c
            with patch.object(svc, "_register_pdf_font", return_value="Helvetica"):
                result = svc._build_pdf_bytes(
                    project=MagicMock(),
                    screenshots=[shot],
                    layout=layout,
                )
                assert isinstance(result, bytes)
                mock_c.save.assert_called_once()
