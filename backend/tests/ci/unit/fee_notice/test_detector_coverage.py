"""Coverage tests for fee_notice.services.detection.detector."""
from __future__ import annotations

import pytest


class TestFeeNoticeDetector:
    def test_detect_empty_text(self):
        from apps.fee_notice.services.detection.detector import FeeNoticeDetector
        detector = FeeNoticeDetector()
        result = detector.detect("", 1)
        assert result.is_fee_notice is False
        assert result.confidence == 0.0

    def test_detect_with_keyword(self):
        from apps.fee_notice.services.detection.detector import FeeNoticeDetector
        detector = FeeNoticeDetector()
        result = detector.detect("这是一份交费通知书，请缴费", 1)
        assert result.is_fee_notice is True
        assert result.confidence >= 0.5
        assert "交费通知书" in result.matched_keywords

    def test_detect_no_keyword(self):
        from apps.fee_notice.services.detection.detector import FeeNoticeDetector
        detector = FeeNoticeDetector()
        result = detector.detect("今天天气不错，适合散步", 1)
        assert result.is_fee_notice is False
        assert result.matched_keywords == []

    def test_detect_multiple_keywords(self):
        from apps.fee_notice.services.detection.detector import FeeNoticeDetector
        detector = FeeNoticeDetector()
        result = detector.detect("交费通知书 案件受理费 诉讼费用交纳通知", 1)
        assert result.is_fee_notice is True
        assert len(result.matched_keywords) >= 2

    def test_detect_pages(self):
        from apps.fee_notice.services.detection.detector import FeeNoticeDetector
        detector = FeeNoticeDetector()
        pages = [(1, "普通文本"), (2, "交费通知书内容"), (3, "案件受理费通知")]
        results = detector.detect_pages(pages)
        assert len(results) == 3
        assert results[0].is_fee_notice is False
        assert results[1].is_fee_notice is True

    def test_calculate_confidence_empty(self):
        from apps.fee_notice.services.detection.detector import FeeNoticeDetector
        detector = FeeNoticeDetector()
        assert detector._calculate_confidence([]) == 0.0

    def test_calculate_confidence_single(self):
        from apps.fee_notice.services.detection.detector import FeeNoticeDetector
        detector = FeeNoticeDetector()
        conf = detector._calculate_confidence(["交费通知书"])
        assert conf == 1.0
