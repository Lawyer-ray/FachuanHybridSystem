"""
Tests for apps.express_query.services — 快递查询服务
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from apps.express_query.services.tracking_extraction_service import TrackingExtractionService


class TestTrackingExtractionService:
    """TrackingExtractionService 测试"""

    def _make_service(self, ocr_service=None):
        return TrackingExtractionService(ocr_service=ocr_service or MagicMock())

    def test_pick_tracking_number_sf(self) -> None:
        svc = self._make_service()
        result = svc._pick_tracking_number("运单号: SF1234567890123")
        assert result is not None
        assert result["carrier"] == "sf"
        assert "SF1234567890123" in result["tracking_number"]

    def test_pick_tracking_number_ems(self) -> None:
        svc = self._make_service()
        result = svc._pick_tracking_number("EMS单号: 1234567890123")
        assert result is not None
        assert result["carrier"] == "ems"

    def test_pick_tracking_number_empty(self) -> None:
        svc = self._make_service()
        assert svc._pick_tracking_number("") is None

    def test_pick_tracking_number_none(self) -> None:
        svc = self._make_service()
        assert svc._pick_tracking_number(None) is None

    def test_pick_tracking_number_no_match(self) -> None:
        svc = self._make_service()
        assert svc._pick_tracking_number("没有运单号的文本") is None

    def test_pick_tracking_number_sf_over_ems(self) -> None:
        """SF should be picked over EMS when both present."""
        svc = self._make_service()
        result = svc._pick_tracking_number("SF1234567890123 EMS 1234567890124")
        assert result is not None
        # SF appears first
        assert result["carrier"] == "sf"

    def test_pick_tracking_number_pipe_normalization(self) -> None:
        svc = self._make_service()
        # Pipe is removed (not replaced with space), so "SF|1234567890123"
        # becomes "SF1234567890123" and SF pattern matches
        result = svc._pick_tracking_number("SF|1234567890123")
        assert result is not None
        assert result["tracking_number"] == "SF1234567890123"

    def test_sf_pattern_valid(self) -> None:
        svc = self._make_service()
        assert svc._sf_pattern.search("SF1234567890123") is not None

    def test_sf_pattern_short(self) -> None:
        svc = self._make_service()
        assert svc._sf_pattern.search("SF123") is None  # too short

    def test_ems_pattern_valid(self) -> None:
        svc = self._make_service()
        match = svc._ems_pattern.search("1234567890123")
        assert match is not None

    def test_ems_pattern_short(self) -> None:
        svc = self._make_service()
        match = svc._ems_pattern.search("1234567890")
        assert match is None  # not 13 digits

    def test_truncate_pdf_to_first_page_non_pdf(self, tmp_path) -> None:
        svc = self._make_service()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        assert svc.truncate_pdf_to_first_page(test_file) is False

    def test_extract_with_mock_ocr(self) -> None:
        mock_ocr = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "SF1234567890123"
        mock_ocr.extract_text.return_value = mock_result
        svc = self._make_service(ocr_service=mock_ocr)

        test_path = MagicMock()
        test_path.suffix = ".jpg"
        test_path.read_bytes.return_value = b"image_bytes"

        result = svc.extract(test_path)
        assert result.tracking_number == "SF1234567890123"
        assert result.carrier_type == "sf"

    def test_extract_no_tracking_number(self) -> None:
        mock_ocr = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "没有运单号"
        mock_ocr.extract_text.return_value = mock_result
        svc = self._make_service(ocr_service=mock_ocr)

        test_path = MagicMock()
        test_path.suffix = ".jpg"
        test_path.read_bytes.return_value = b"image_bytes"

        result = svc.extract(test_path)
        assert result.tracking_number == ""

# ---------------------------------------------------------------------------
# EMS auth handler extended tests
# ---------------------------------------------------------------------------
