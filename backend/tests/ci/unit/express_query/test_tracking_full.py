"""Tests for express_query: tracking extraction and models."""
from __future__ import annotations

import pytest

from apps.express_query.models import (
    ExpressCarrierType,
    ExpressQueryTaskStatus,
)
from apps.express_query.services.tracking_extraction_service import (
    TrackingExtractionResult,
    TrackingExtractionService,
)


# ---------------------------------------------------------------------------
# Models choices
# ---------------------------------------------------------------------------


class TestExpressCarrierType:
    def test_values(self) -> None:
        assert ExpressCarrierType.UNKNOWN == "unknown"
        assert ExpressCarrierType.EMS == "ems"
        assert ExpressCarrierType.SF == "sf"

    def test_labels(self) -> None:
        assert ExpressCarrierType("ems").label == "EMS"
        assert ExpressCarrierType("sf").label == "顺丰"


class TestExpressQueryTaskStatus:
    def test_all_statuses(self) -> None:
        assert ExpressQueryTaskStatus.PENDING == "pending"
        assert ExpressQueryTaskStatus.OCR_PARSING == "ocr_parsing"
        assert ExpressQueryTaskStatus.WAITING_LOGIN == "waiting_login"
        assert ExpressQueryTaskStatus.QUERYING == "querying"
        assert ExpressQueryTaskStatus.SUCCESS == "success"
        assert ExpressQueryTaskStatus.FAILED == "failed"


# ---------------------------------------------------------------------------
# TrackingExtractionResult
# ---------------------------------------------------------------------------


class TestTrackingExtractionResult:
    def test_creation(self) -> None:
        r = TrackingExtractionResult(
            carrier_type="sf",
            tracking_number="SF1234567890",
            ocr_text="some text",
        )
        assert r.carrier_type == "sf"
        assert r.tracking_number == "SF1234567890"


# ---------------------------------------------------------------------------
# TrackingExtractionService._pick_tracking_number
# ---------------------------------------------------------------------------


class TestPickTrackingNumber:
    """Tests for TrackingExtractionService._pick_tracking_number."""

    def _svc(self) -> TrackingExtractionService:
        return TrackingExtractionService(ocr_service=None)

    def test_sf_tracking(self) -> None:
        svc = self._svc()
        result = svc._pick_tracking_number("运单号 SF1234567890123 请查收")
        assert result is not None
        assert result["carrier"] == ExpressCarrierType.SF
        assert "SF1234567890123" in result["tracking_number"]

    def test_ems_tracking(self) -> None:
        svc = self._svc()
        result = svc._pick_tracking_number("EMS单号：1234567890123")
        assert result is not None
        assert result["carrier"] == ExpressCarrierType.EMS

    def test_empty_text(self) -> None:
        svc = self._svc()
        assert svc._pick_tracking_number("") is None

    def test_no_tracking_found(self) -> None:
        svc = self._svc()
        assert svc._pick_tracking_number("no tracking here") is None

    def test_sf_overlapping_ems_skipped(self) -> None:
        """When SF number contains 13 digits, the EMS pattern should not match."""
        svc = self._svc()
        # SF1234567890123 - the digits 1234567890123 (13 digits) should not be picked as EMS
        result = svc._pick_tracking_number("SF1234567890123")
        assert result is not None
        assert result["carrier"] == ExpressCarrierType.SF

    def test_pipe_normalization(self) -> None:
        """Pipes should be removed before pattern matching."""
        svc = self._svc()
        result = svc._pick_tracking_number("|SF1234567890|")
        assert result is not None
        assert result["carrier"] == ExpressCarrierType.SF

    def test_multiple_sf_uses_first(self) -> None:
        """If multiple SF numbers found, use the first one by position."""
        svc = self._svc()
        result = svc._pick_tracking_number("SF1111111111111 和 SF2222222222222")
        assert result is not None
        assert "1111111111111" in result["tracking_number"]


class TestTruncatePdfToFirstPage:
    def test_static_method_exists(self) -> None:
        assert hasattr(TrackingExtractionService, 'truncate_pdf_to_first_page')
        assert callable(TrackingExtractionService.truncate_pdf_to_first_page)
