"""Tests for evidence_sorting classifier service."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestClassifierClassifyByKeywords:
    def _make_service(self):
        from apps.evidence_sorting.services.classifier import ClassifierService
        return ClassifierService()

    def test_statement_detected(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("对账单 月度汇总", "img.jpg") == "statement"

    def test_delivery_detected(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("出库单 发货单", "img.jpg") == "delivery"

    def test_receipt_detected(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("收款 转账 银行回单", "img.jpg") == "receipt"

    def test_empty_text_png_defaults_statement(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("", "screenshot.png") == "statement"

    def test_empty_text_jpg_defaults_other(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("", "photo.jpg") == "other"

    def test_no_keywords_other(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("hello world", "img.jpg") == "other"


class TestClassifierExtractDate:
    def _make_service(self):
        from apps.evidence_sorting.services.classifier import ClassifierService
        return ClassifierService()

    def test_chinese_date(self):
        svc = self._make_service()
        assert svc._extract_date("2026年1月15日") == "20260115"

    def test_iso_date(self):
        svc = self._make_service()
        assert svc._extract_date("2026-01-15") == "20260115"

    def test_slash_date(self):
        svc = self._make_service()
        assert svc._extract_date("2026/01/15") == "20260115"

    def test_no_date(self):
        svc = self._make_service()
        assert svc._extract_date("no date here") is None


class TestClassifierExtractAmount:
    def _make_service(self):
        from apps.evidence_sorting.services.classifier import ClassifierService
        return ClassifierService()

    def test_yuan_symbol(self):
        svc = self._make_service()
        assert svc._extract_amount("¥12345.67") == "12345.67"

    def test_chinese_yuan(self):
        svc = self._make_service()
        assert svc._extract_amount("12345.67元") == "12345.67"

    def test_colon_prefix(self):
        svc = self._make_service()
        assert svc._extract_amount("金额：12345") == "12345"

    def test_no_amount(self):
        svc = self._make_service()
        assert svc._extract_amount("hello world") is None

    def test_multiple_returns_max(self):
        svc = self._make_service()
        assert svc._extract_amount("¥100 ¥200") == "200"


class TestClassifierDetectSigned:
    def _make_service(self):
        from apps.evidence_sorting.services.classifier import ClassifierService
        return ClassifierService()

    def test_signed(self):
        svc = self._make_service()
        assert svc._detect_signed("已签名确认") is True

    def test_unsigned(self):
        svc = self._make_service()
        assert svc._detect_signed("普通文本") is False


class TestClassifierClassifyImages:
    def _make_service(self):
        from apps.evidence_sorting.services.classifier import ClassifierService
        return ClassifierService()

    def test_classify_single_image(self):
        svc = self._make_service()
        mock_ocr = MagicMock()
        mock_ocr.detect_orientation_with_text.return_value = {
            "ocr_text": "对账单",
            "rotation": 0,
            "confidence": 0.9,
        }
        svc._ocr_service = mock_ocr
        import base64
        data = base64.b64encode(b"fake_image").decode()
        result = svc.classify_images([{"filename": "test.jpg", "data": data}])
        assert len(result.images) == 1
        assert result.images[0].category == "statement"

    def test_classify_error_handling(self):
        svc = self._make_service()
        mock_ocr = MagicMock()
        mock_ocr.detect_orientation_with_text.side_effect = Exception("OCR failed")
        svc._ocr_service = mock_ocr
        result = svc.classify_images([{"filename": "bad.jpg", "data": "invalid"}])
        assert len(result.images) == 1
        assert result.images[0].category == "other"
        assert len(result.errors) == 1
