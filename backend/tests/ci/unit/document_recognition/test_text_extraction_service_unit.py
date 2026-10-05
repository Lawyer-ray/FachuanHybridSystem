"""TextExtractionService 单元测试 — 提取阶梯路由与校验。

PDF/图片的底层引擎（PyMuPDF、VLM、本地 OCR）全部 mock，只验证：
- 文件存在性/格式校验与策略路由
- pdf_direct → vlm → ocr 降级链
- 空格清理与字数限制
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.document_recognition.services.text_extraction_service import (
    SUPPORTED_EXTENSIONS,
    TextExtractionResult,
    TextExtractionService,
    _remove_all_spaces,
    get_supported_extensions,
)


def _make_file(tmp_path: Path, name: str) -> str:
    f = tmp_path / name
    f.write_bytes(b"data")
    return str(f)


class TestRemoveAllSpaces:
    def test_removes_all_whitespace(self) -> None:
        assert _remove_all_spaces(" 传 票\t号\n码\r\n2026 ") == "传票号码2026"

    def test_empty_and_none_safe(self) -> None:
        assert _remove_all_spaces("") == ""
        assert _remove_all_spaces("   ") == ""


class TestSupportedFormats:
    def test_supported_extensions_constant(self) -> None:
        assert {".pdf", ".jpg", ".jpeg", ".png"} == SUPPORTED_EXTENSIONS

    def test_is_supported_format(self) -> None:
        svc = TextExtractionService()
        assert svc.is_supported_format("/tmp/a.pdf") is True
        assert svc.is_supported_format("/tmp/a.JPG") is True
        assert svc.is_supported_format("/tmp/a.docx") is False
        assert svc.is_supported_format(".png") is True
        assert svc.is_supported_format(".txt") is False

    def test_get_supported_extensions(self) -> None:
        svc = TextExtractionService()
        assert set(svc.get_supported_extensions()) == SUPPORTED_EXTENSIONS
        assert set(get_supported_extensions()) == SUPPORTED_EXTENSIONS


class TestExtractTextValidation:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationException) as exc_info:
            TextExtractionService().extract_text(str(tmp_path / "missing.pdf"))
        assert exc_info.value.code == "FILE_NOT_FOUND"

    def test_unsupported_format_raises(self, tmp_path: Path) -> None:
        path = _make_file(tmp_path, "a.docx")
        with pytest.raises(ValidationException) as exc_info:
            TextExtractionService().extract_text(path)
        assert exc_info.value.code == "UNSUPPORTED_FILE_FORMAT"

    def test_routes_pdf_to_pdf_extractor(self, tmp_path: Path) -> None:
        svc = TextExtractionService()
        path = _make_file(tmp_path, "a.pdf")
        with patch.object(svc, "_extract_from_pdf", return_value=TextExtractionResult("t", "pdf_direct", True)) as m:
            result = svc.extract_text(path)
        assert result.success is True
        m.assert_called_once_with(path, max_pages=None)

    def test_routes_image_to_image_extractor(self, tmp_path: Path) -> None:
        svc = TextExtractionService()
        path = _make_file(tmp_path, "a.png")
        with patch.object(svc, "_extract_from_image", return_value=TextExtractionResult("t", "ocr", True)) as m:
            result = svc.extract_text(path)
        assert result.success is True
        m.assert_called_once_with(path)

    def test_constructor_max_pages_used_when_arg_none(self, tmp_path: Path) -> None:
        svc = TextExtractionService(max_pages=3)
        path = _make_file(tmp_path, "a.pdf")
        with patch.object(svc, "_extract_from_pdf") as m:
            svc.extract_text(path)
        m.assert_called_once_with(path, max_pages=3)

    def test_call_max_pages_overrides_constructor(self, tmp_path: Path) -> None:
        svc = TextExtractionService(max_pages=3)
        path = _make_file(tmp_path, "a.pdf")
        with patch.object(svc, "_extract_from_pdf") as m:
            svc.extract_text(path, max_pages=7)
        m.assert_called_once_with(path, max_pages=7)


class TestExtractFromPdf:
    def _svc(self, **kwargs: Any) -> TextExtractionService:
        return TextExtractionService(**kwargs)

    def test_direct_success_strips_spaces(self) -> None:
        svc = self._svc()
        with patch.object(svc, "_extract_pdf_text_direct", return_value="（2026）粤 0604\n民初 1号"):
            result = svc._extract_from_pdf("/tmp/a.pdf")
        assert result == TextExtractionResult("（2026）粤0604民初1号", "pdf_direct", True)

    def test_direct_empty_falls_to_vlm(self) -> None:
        svc = self._svc()
        vlm = TextExtractionResult("视觉转写文本", "vlm", True)
        with (
            patch.object(svc, "_extract_pdf_text_direct", return_value=""),
            patch.object(svc, "_extract_pdf_with_vlm", return_value=vlm) as m_vlm,
            patch.object(svc, "_extract_pdf_with_ocr") as m_ocr,
        ):
            result = svc._extract_from_pdf("/tmp/a.pdf")
        assert result.extraction_method == "vlm"
        assert result.text == "视觉转写文本"
        m_ocr.assert_not_called()

    def test_vlm_failure_falls_to_local_ocr(self) -> None:
        svc = self._svc()
        with (
            patch.object(svc, "_extract_pdf_text_direct", return_value="   "),
            patch.object(svc, "_extract_pdf_with_vlm", return_value=TextExtractionResult("", "vlm", False)),
            patch.object(
                svc, "_extract_pdf_with_ocr", return_value=TextExtractionResult("本地OCR", "ocr", True)
            ) as m_ocr,
        ):
            result = svc._extract_from_pdf("/tmp/a.pdf")
        assert result.extraction_method == "ocr"
        assert result.success is True
        m_ocr.assert_called_once()


class TestExtractPdfTextDirect:
    def test_returns_extracted_text(self) -> None:
        svc = TextExtractionService(text_limit=100)
        with patch("apps.automation.services.document.document_processing.extract_pdf_text", return_value="内容") as m:
            assert svc._extract_pdf_text_direct("/tmp/a.pdf", max_pages=5) == "内容"
        m.assert_called_once_with("/tmp/a.pdf", limit=100, max_pages=5)

    def test_exception_returns_empty(self) -> None:
        svc = TextExtractionService()
        with patch(
            "apps.automation.services.document.document_processing.extract_pdf_text",
            side_effect=RuntimeError("fitz 挂了"),
        ):
            assert svc._extract_pdf_text_direct("/tmp/a.pdf") == ""


class TestExtractPdfWithVlm:
    _VLM = "apps.document_recognition.services.vlm_ocr_service.VLMTranscriptionService"

    def test_unavailable_returns_failure(self) -> None:
        svc = TextExtractionService()
        with patch(self._VLM) as vlm_cls:
            vlm_cls.is_available.return_value = False
            result = svc._extract_pdf_with_vlm("/tmp/a.pdf")
        assert result == TextExtractionResult("", "vlm", False)
        vlm_cls.assert_not_called()

    def test_success_applies_text_limit(self) -> None:
        svc = TextExtractionService(text_limit=5)
        with patch(self._VLM) as vlm_cls:
            vlm_cls.is_available.return_value = True
            vlm_cls.return_value.transcribe_pdf.return_value = "0123456789"
            result = svc._extract_pdf_with_vlm("/tmp/a.pdf", max_pages=2)
        assert result.success is True
        assert result.text == "01234"
        vlm_cls.return_value.transcribe_pdf.assert_called_once_with("/tmp/a.pdf", max_pages=2)

    def test_blank_transcription_returns_failure(self) -> None:
        svc = TextExtractionService()
        with patch(self._VLM) as vlm_cls:
            vlm_cls.is_available.return_value = True
            vlm_cls.return_value.transcribe_pdf.return_value = "   "
            result = svc._extract_pdf_with_vlm("/tmp/a.pdf")
        assert result.success is False

    def test_transcribe_exception_returns_failure(self) -> None:
        svc = TextExtractionService()
        with patch(self._VLM) as vlm_cls:
            vlm_cls.is_available.return_value = True
            vlm_cls.return_value.transcribe_pdf.side_effect = RuntimeError("vision down")
            result = svc._extract_pdf_with_vlm("/tmp/a.pdf")
        assert result.success is False


class TestExtractPdfWithOcr:
    def test_success_applies_limit(self) -> None:
        svc = TextExtractionService(text_limit=4)
        with patch.object(svc, "_ocr_pdf_pages", return_value="字 字 字 字 字"):
            result = svc._extract_pdf_with_ocr("/tmp/a.pdf")
        assert result == TextExtractionResult("字字字字", "ocr", True)

    def test_empty_text_returns_failure(self) -> None:
        svc = TextExtractionService()
        with patch.object(svc, "_ocr_pdf_pages", return_value=""):
            result = svc._extract_pdf_with_ocr("/tmp/a.pdf")
        assert result == TextExtractionResult("", "ocr", False)

    def test_exception_returns_failure(self) -> None:
        svc = TextExtractionService()
        with patch.object(svc, "_ocr_pdf_pages", side_effect=RuntimeError("渲染失败")):
            result = svc._extract_pdf_with_ocr("/tmp/a.pdf")
        assert result == TextExtractionResult("", "ocr", False)


class TestExtractFromImage:
    _VLM = "apps.document_recognition.services.vlm_ocr_service.VLMTranscriptionService"

    def test_vlm_success(self) -> None:
        svc = TextExtractionService()
        with patch(self._VLM) as vlm_cls:
            vlm_cls.is_available.return_value = True
            vlm_cls.return_value.transcribe_image.return_value = "图 片 文 本"
            result = svc._extract_from_image("/tmp/a.png")
        assert result == TextExtractionResult("图片文本", "vlm", True)

    def test_vlm_blank_falls_back_to_local_ocr(self) -> None:
        svc = TextExtractionService()
        with patch(self._VLM) as vlm_cls:
            vlm_cls.is_available.return_value = True
            vlm_cls.return_value.transcribe_image.return_value = " "
            with patch.object(svc, "_recognize_local", return_value="本地文本"):
                result = svc._extract_from_image("/tmp/a.png")
        assert result == TextExtractionResult("本地文本", "ocr", True)

    def test_vlm_unavailable_uses_local_ocr(self) -> None:
        svc = TextExtractionService()
        with patch(self._VLM) as vlm_cls:
            vlm_cls.is_available.return_value = False
            with patch.object(svc, "_recognize_local", return_value="OCR 文本") as m_local:
                result = svc._extract_from_image("/tmp/a.jpg")
        assert result.text == "OCR文本"
        assert result.extraction_method == "ocr"
        m_local.assert_called_once_with("/tmp/a.jpg")

    def test_local_ocr_empty_returns_failure(self) -> None:
        svc = TextExtractionService()
        with patch(self._VLM) as vlm_cls:
            vlm_cls.is_available.return_value = False
            with patch.object(svc, "_recognize_local", return_value=""):
                result = svc._extract_from_image("/tmp/a.jpg")
        assert result == TextExtractionResult("", "ocr", False)

    def test_local_ocr_exception_returns_failure(self) -> None:
        svc = TextExtractionService()
        with patch(self._VLM) as vlm_cls:
            vlm_cls.is_available.return_value = False
            with patch.object(svc, "_recognize_local", side_effect=RuntimeError("ocr crash")):
                result = svc._extract_from_image("/tmp/a.jpg")
        assert result == TextExtractionResult("", "ocr", False)
