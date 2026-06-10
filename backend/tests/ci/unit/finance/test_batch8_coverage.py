"""Batch8 coverage tests for apps.finance."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ── Finance services ──────────────────────────────────────────────────────


class TestFinanceServices:
    """Test finance service imports."""

    def test_lpr_sync_service_import(self) -> None:
        from apps.finance.services.lpr.sync_service import LPRSyncService

        assert LPRSyncService is not None


# ── Finance APIs ──────────────────────────────────────────────────────────


class TestFinanceAPIs:
    """Test finance API imports."""

    def test_api_import(self) -> None:
        from apps.finance.api import lpr_api

        assert lpr_api is not None


# ── Finance models ────────────────────────────────────────────────────────


class TestFinanceModels:
    """Test finance model imports."""

    def test_models_import(self) -> None:
        from apps.finance import models

        assert models is not None


# ── Invoice recognition services ──────────────────────────────────────────


class TestInvoiceRecognitionServices:
    """Test invoice recognition service imports."""

    def test_recognition_service_import(self) -> None:
        from apps.invoice_recognition.services.invoice_recognition_service import InvoiceRecognitionService

        assert InvoiceRecognitionService is not None


# ── Fee notice services ───────────────────────────────────────────────────


class TestFeeNoticeServices:
    """Test fee notice service imports."""

    def test_extraction_service_import(self) -> None:
        from apps.fee_notice.services.extraction.extraction_service import FeeNoticeExtractionService

        assert FeeNoticeExtractionService is not None

    def test_check_service_import(self) -> None:
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService

        assert FeeNoticeCheckService is not None

    def test_comparison_service_import(self) -> None:
        from apps.fee_notice.services.comparison.comparison_service import FeeComparisonService

        assert FeeComparisonService is not None
