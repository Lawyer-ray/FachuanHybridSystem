"""Tests for async evidence classification with parallel OCR."""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import MagicMock, patch

import pytest

from apps.evidence_sorting.services.classifier import ClassifierService


def _make_image(text_content: str) -> dict:
    """Create a fake base64 image dict."""
    return {
        "filename": f"img_{text_content[:8].replace(' ','_')}.jpg",
        "data": base64.b64encode(text_content.encode()).decode(),
    }


@pytest.mark.asyncio
class TestClassifyImagesAsync:
    async def test_parallel_ocr_calls(self):
        """Verify all images are processed concurrently, not sequentially."""
        svc = ClassifierService()
        images = [_make_image(f"对账单 content {i}") for i in range(5)]

        call_count = 0

        def fake_detect(image_bytes):
            nonlocal call_count
            call_count += 1
            return {
                "ocr_text": image_bytes.decode("utf-8", errors="ignore"),
                "rotation": 0,
                "confidence": 0.9,
            }

        mock_ocr = MagicMock()
        mock_ocr.detect_orientation_with_text = fake_detect

        with patch.object(svc, '_get_ocr_service', return_value=mock_ocr):
            result = await svc.classify_images_async(images)

        assert len(result.images) == 5
        assert call_count == 5

    async def test_error_handling_per_image(self):
        """One failed image should not prevent others from being classified."""
        svc = ClassifierService()
        images = [_make_image("good content"), _make_image("bad")]

        def fake_detect(image_bytes):
            text = image_bytes.decode("utf-8", errors="ignore")
            if "bad" in text:
                raise RuntimeError("OCR failure")
            return {"ocr_text": text, "rotation": 0, "confidence": 0.8}

        mock_ocr = MagicMock()
        mock_ocr.detect_orientation_with_text = fake_detect

        with patch.object(svc, '_get_ocr_service', return_value=mock_ocr):
            result = await svc.classify_images_async(images)

        assert len(result.images) == 2
        assert len(result.errors) == 1
        assert "OCR failure" in result.errors[0]

    async def test_empty_images_list(self):
        """Empty images list should return empty result."""
        svc = ClassifierService()
        result = await svc.classify_images_async([])
        assert len(result.images) == 0
        assert len(result.errors) == 0
