"""Tests for apps.image_rotation.services.rename_ocr.channel."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from apps.image_rotation.services.rename_ocr.channel import (
    RETRY_CONFIDENCE_THRESHOLD,
    OCRResult,
    RenameOCRChannel,
)


def _make_image_bytes(width: int = 200, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), (128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestOCRResult:
    def test_fields(self) -> None:
        r = OCRResult(text="hello", text_blocks=["hello"], scores=[0.95], overall_confidence=0.95)
        assert r.text == "hello"
        assert r.text_blocks == ["hello"]
        assert r.scores == [0.95]
        assert r.overall_confidence == 0.95


class TestRenameOCRChannel:
    def test_recognize_returns_none_when_ocr_init_fails(self) -> None:
        channel = RenameOCRChannel()
        channel._init_failed = True
        result = channel.recognize(b"fake-image-data")
        assert result is None

    def test_recognize_returns_none_on_exception(self) -> None:
        channel = RenameOCRChannel()
        channel._ocr = MagicMock()
        with patch.object(channel, "_rotate_image", side_effect=Exception("bad image")):
            result = channel.recognize(b"bad-data", rotation=0)
        assert result is None

    def test_rotate_image_zero_rotation(self) -> None:
        """Rotation 0 returns original data unchanged."""
        channel = RenameOCRChannel()
        data = _make_image_bytes()
        result = channel._rotate_image(data, 0)
        assert result == data

    def test_rotate_image_90_degrees(self) -> None:
        """Rotating 90 degrees changes image dimensions."""
        channel = RenameOCRChannel()
        data = _make_image_bytes(200, 100)
        result = channel._rotate_image(data, 90)
        img = Image.open(io.BytesIO(result))
        # After 90-degree rotation, width and height swap
        assert img.width == 100
        assert img.height == 200

    def test_rotate_image_jpeg_format(self) -> None:
        """JPEG images are rotated and saved correctly."""
        channel = RenameOCRChannel()
        img = Image.new("RGB", (200, 100), (128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        data = buf.getvalue()
        result = channel._rotate_image(data, 180)
        result_img = Image.open(io.BytesIO(result))
        # After 180 degrees, dimensions stay the same
        assert result_img.width == 200

    def test_recognize_with_low_confidence_triggers_retry(self) -> None:
        """When first OCR result has low confidence, retry with enhanced config."""
        channel = RenameOCRChannel()
        channel._ocr = MagicMock()

        low_conf_result = OCRResult(text="low", text_blocks=["low"], scores=[0.3], overall_confidence=0.3)
        high_conf_result = OCRResult(text="high", text_blocks=["high"], scores=[0.9], overall_confidence=0.9)

        with (
            patch.object(channel, "_rotate_image", return_value=_make_image_bytes()),
            patch.object(channel, "_do_ocr", side_effect=[low_conf_result, high_conf_result]),
        ):
            result = channel.recognize(_make_image_bytes(), rotation=0)
        assert result is not None
        assert result.overall_confidence == 0.9

    def test_recognize_with_high_confidence_no_retry(self) -> None:
        """When first OCR result has high confidence, no retry."""
        channel = RenameOCRChannel()
        channel._ocr = MagicMock()

        high_conf_result = OCRResult(text="good", text_blocks=["good"], scores=[0.95], overall_confidence=0.95)

        with (
            patch.object(channel, "_rotate_image", return_value=_make_image_bytes()),
            patch.object(channel, "_do_ocr", return_value=high_conf_result) as mock_do_ocr,
        ):
            result = channel.recognize(_make_image_bytes(), rotation=0)
        assert result is not None
        # Only called once (no retry)
        mock_do_ocr.assert_called_once()


class TestRetryConfidenceThreshold:
    def test_threshold_value(self) -> None:
        assert RETRY_CONFIDENCE_THRESHOLD == 0.6


class TestDoOcr:
    def test_do_ocr_local_engine_empty_result(self) -> None:
        """Local engine returning empty result."""
        channel = RenameOCRChannel()
        mock_ocr_service = MagicMock()
        mock_ocr_service.provider = "local"
        mock_engine = MagicMock()
        mock_engine.return_value = SimpleNamespace(txts=None, scores=None)
        mock_ocr_service.ocr = mock_engine

        with patch.object(channel._preprocessor, "preprocess", return_value=b"data"):
            result = channel._do_ocr(mock_ocr_service, b"data")
        assert result.text == ""
        assert result.text_blocks == []
        assert result.overall_confidence == 0.0

    def test_do_ocr_api_provider(self) -> None:
        """PaddleOCR API path."""
        channel = RenameOCRChannel()
        mock_ocr_service = MagicMock()
        mock_ocr_service.provider = "paddleocr_api"
        mock_ocr_service.paddleocr_engine.recognize_bytes.return_value = SimpleNamespace(
            raw_texts=["hello", "world"]
        )

        with patch.object(channel._preprocessor, "preprocess", return_value=b"data"):
            result = channel._do_ocr(mock_ocr_service, b"data")
        assert result.text_blocks == ["hello", "world"]
        assert result.overall_confidence > 0

    def test_do_ocr_api_failure_returns_empty(self) -> None:
        """PaddleOCR API failure returns empty result."""
        channel = RenameOCRChannel()
        mock_ocr_service = MagicMock()
        mock_ocr_service.provider = "paddleocr_api"
        mock_ocr_service.paddleocr_engine.recognize_bytes.side_effect = RuntimeError("API down")

        with patch.object(channel._preprocessor, "preprocess", return_value=b"data"):
            result = channel._do_ocr_via_api(mock_ocr_service, b"data")
        assert result.text == ""
        assert result.overall_confidence == 0.0
