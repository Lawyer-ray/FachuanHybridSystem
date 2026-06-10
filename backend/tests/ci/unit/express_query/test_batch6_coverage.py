"""Batch 6 coverage tests for express_query module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestTrackingExtractionService:
    def _make_service(self):
        from apps.express_query.services.tracking_extraction_service import (
            TrackingExtractionService,
        )

        mock_ocr = MagicMock()
        return TrackingExtractionService(ocr_service=mock_ocr)

    def test_pick_tracking_number_sf(self):
        svc = self._make_service()
        result = svc._pick_tracking_number("运单号: SF1234567890123")
        assert result is not None
        assert result["carrier"] == "sf"
        assert "SF1234567890123" in result["tracking_number"]

    def test_pick_tracking_number_ems(self):
        svc = self._make_service()
        result = svc._pick_tracking_number("EMS单号: 1234567890123")
        assert result is not None
        assert result["carrier"] == "ems"

    def test_pick_tracking_number_none_empty(self):
        svc = self._make_service()
        assert svc._pick_tracking_number("") is None
        assert svc._pick_tracking_number(None) is None

    def test_pick_tracking_number_no_match(self):
        svc = self._make_service()
        assert svc._pick_tracking_number("没有任何单号的文本") is None

    def test_pick_tracking_number_sf_takes_priority(self):
        svc = self._make_service()
        result = svc._pick_tracking_number("SF1234567890123")
        assert result is not None
        assert result["carrier"] == "sf"

    def test_pick_tracking_number_pipe_replacement(self):
        svc = self._make_service()
        result = svc._pick_tracking_number("SF|123456|7890123")
        assert result is not None

    def test_pick_tracking_number_ems_overlapping_sf(self):
        svc = self._make_service()
        # SF number contains 13 digits that EMS could match, but should be skipped
        result = svc._pick_tracking_number("SF1234567890123")
        assert result is not None
        assert result["carrier"] == "sf"

    def test_tracking_extraction_result_dataclass(self):
        from apps.express_query.services.tracking_extraction_service import (
            TrackingExtractionResult,
        )

        result = TrackingExtractionResult(
            carrier_type="sf", tracking_number="SF1234567890123", ocr_text="text"
        )
        assert result.carrier_type == "sf"
        assert result.tracking_number == "SF1234567890123"

    def test_truncate_pdf_non_pdf(self):
        from apps.express_query.services.tracking_extraction_service import (
            TrackingExtractionService,
        )

        with patch("pathlib.Path.suffix", ".docx"):
            result = TrackingExtractionService.truncate_pdf_to_first_page(
                MagicMock(suffix=".docx")
            )
            assert result is False
