"""视觉转写管线测试：VLM 服务、提取阶梯（vlm → macvision → rapidocr）、文本清洗。

全部无 DB（MagicMock 风格，与现有单测一致）。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from apps.automation.services.ocr import is_mac_vision_available
from apps.document_recognition.services.text_extraction_service import TextExtractionService
from apps.document_recognition.services.vlm_ocr_service import VLMTranscriptionService, _clean_transcription

# ---------------------------------------------------------------------------
# _clean_transcription
# ---------------------------------------------------------------------------


def test_clean_transcription_strips_code_fence() -> None:
    assert _clean_transcription("```text\n判决书正文\n```") == "判决书正文"
    assert _clean_transcription("  正文  \n") == "正文"
    assert _clean_transcription("") == ""


# ---------------------------------------------------------------------------
# VLMTranscriptionService
# ---------------------------------------------------------------------------


def _mock_llm_service(content: str) -> MagicMock:
    svc = MagicMock()
    svc.chat.return_value = MagicMock(content=content, model="kimi-2.6")
    return svc


def test_vlm_transcribe_image_bytes_builds_multimodal_message() -> None:
    llm = _mock_llm_service("```text\n正文内容\n```")
    with patch(
        "apps.core.llm.config.LLMConfig.get_vision_model", return_value="kimi-2.6"
    ):
        service = VLMTranscriptionService(llm_service=llm)
        text = service._transcribe_image_bytes(b"fake-image", "image/png", 0)

    assert text == "正文内容"
    kwargs: dict[str, Any] = llm.chat.call_args.kwargs
    assert kwargs["model"] == "kimi-2.6"
    assert kwargs["fallback"] is False
    content = kwargs["messages"][0]["content"]
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[1]["type"] == "text"


def test_vlm_is_available_reads_provider_config() -> None:
    with patch("apps.core.llm.config.LLMConfig.get_vision_model", return_value=""):
        assert VLMTranscriptionService.is_available() is False
    with patch("apps.core.llm.config.LLMConfig.get_vision_model", return_value="kimi-2.6"):
        assert VLMTranscriptionService.is_available() is True


# ---------------------------------------------------------------------------
# 提取阶梯：vision_model 未配置 / VLM 异常 → 降级本地 OCR
# ---------------------------------------------------------------------------


def test_extract_pdf_with_vlm_disabled_when_no_vision_model(tmp_path: Any) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with patch(
        "apps.document_recognition.services.vlm_ocr_service.VLMTranscriptionService.is_available",
        return_value=False,
    ):
        result = TextExtractionService()._extract_pdf_with_vlm(str(pdf))
    assert result.success is False
    assert result.extraction_method == "vlm"


def test_extract_pdf_with_vlm_swallows_exception() -> None:
    transcriber = MagicMock()
    transcriber.is_available = MagicMock(return_value=True)
    transcriber.transcribe_pdf.side_effect = RuntimeError("gateway down")
    with patch(
        "apps.document_recognition.services.vlm_ocr_service.VLMTranscriptionService",
        return_value=transcriber,
    ):
        result = TextExtractionService()._extract_pdf_with_vlm("/fake/a.pdf")
    assert result.success is False  # 异常被折叠，由调用方降级本地 OCR


def test_extract_pdf_with_vlm_success_strips_spaces() -> None:
    transcriber = MagicMock()
    transcriber.is_available = MagicMock(return_value=True)
    transcriber.transcribe_pdf.return_value = "（2024）粤 0605执保 4550 号"
    with patch(
        "apps.document_recognition.services.vlm_ocr_service.VLMTranscriptionService",
        return_value=transcriber,
    ):
        result = TextExtractionService()._extract_pdf_with_vlm("/fake/a.pdf")
    assert result.success is True
    assert result.text == "（2024）粤0605执保4550号"
    assert result.extraction_method == "vlm"


# ---------------------------------------------------------------------------
# 本地 OCR 阶梯：macOS Vision 可用优先，否则 RapidOCR
# ---------------------------------------------------------------------------


def test_recognize_local_prefers_mac_vision() -> None:
    with (
        patch(
            "apps.automation.services.ocr.is_mac_vision_available", return_value=True
        ) as avail,
        patch("apps.automation.services.ocr.MacVisionOCREngine") as engine_cls,
    ):
        engine_cls.return_value.recognize.return_value = "vision 文本"
        text = TextExtractionService()._recognize_local("/tmp/x.png")
    assert text == "vision 文本"
    avail.assert_called_once()
    engine_cls.return_value.recognize.assert_called_once_with("/tmp/x.png")


def test_recognize_local_falls_back_to_rapidocr() -> None:
    ocr_service = MagicMock()
    ocr_service.recognize.return_value = "rapid 文本"
    locator = MagicMock()
    locator.get_ocr_service.return_value = ocr_service
    with (
        patch("apps.automation.services.ocr.is_mac_vision_available", return_value=False),
        patch("apps.core.interfaces.ServiceLocator", locator),
    ):
        text = TextExtractionService()._recognize_local("/tmp/x.png")
    assert text == "rapid 文本"


def test_recognize_local_falls_back_when_vision_raises() -> None:
    ocr_service = MagicMock()
    ocr_service.recognize.return_value = "rapid 文本"
    locator = MagicMock()
    locator.get_ocr_service.return_value = ocr_service
    with (
        patch("apps.automation.services.ocr.is_mac_vision_available", return_value=True),
        patch(
            "apps.automation.services.ocr.MacVisionOCREngine",
            **{"return_value.recognize.side_effect": RuntimeError("vision boom")},
        ),
        patch("apps.core.interfaces.ServiceLocator", locator),
    ):
        text = TextExtractionService()._recognize_local("/tmp/x.png")
    assert text == "rapid 文本"


def test_is_mac_vision_available_returns_bool() -> None:
    assert isinstance(is_mac_vision_available(), bool)
