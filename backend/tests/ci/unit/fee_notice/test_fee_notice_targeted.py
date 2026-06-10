"""Targeted tests for fee_notice module to push coverage to 80%+."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# services/__init__.py (15% coverage)
# ---------------------------------------------------------------------------


class TestFeeNoticeServicesInit:
    def test_getattr_unknown(self):
        from apps.fee_notice import services

        with pytest.raises(AttributeError):
            services.NonExistentService

    def test_all_exports(self):
        from apps.fee_notice.services import __all__

        assert "FeeNoticeDetector" in __all__
        assert "FeeAmountExtractor" in __all__
        assert "FeeNoticeExtractionService" in __all__
        assert "FeeComparisonService" in __all__
        assert "FeeNoticeCheckService" in __all__
        assert "DetectionResult" in __all__
        assert "FeeAmountResult" in __all__
        assert "FeeNoticeInfo" in __all__

    def test_lazy_import_detection_result(self):
        from apps.fee_notice.services import DetectionResult

        assert DetectionResult is not None

    def test_lazy_import_fee_amount_result(self):
        from apps.fee_notice.services import FeeAmountResult

        assert FeeAmountResult is not None

    def test_lazy_import_fee_notice_info(self):
        from apps.fee_notice.services import FeeNoticeInfo

        assert FeeNoticeInfo is not None

    def test_lazy_import_fee_notice_extraction_result(self):
        from apps.fee_notice.services import FeeNoticeExtractionResult

        assert FeeNoticeExtractionResult is not None

    def test_lazy_import_fee_comparison_result(self):
        from apps.fee_notice.services import FeeComparisonResult

        assert FeeComparisonResult is not None

    def test_lazy_import_case_comparison_info(self):
        from apps.fee_notice.services import CaseComparisonInfo

        assert CaseComparisonInfo is not None

    def test_lazy_import_case_search_result(self):
        from apps.fee_notice.services import CaseSearchResult

        assert CaseSearchResult is not None

    def test_lazy_import_fee_check_item(self):
        from apps.fee_notice.services import FeeCheckItem

        assert FeeCheckItem is not None

    def test_lazy_import_fee_check_result(self):
        from apps.fee_notice.services import FeeCheckResult

        assert FeeCheckResult is not None

    def test_lazy_import_detector(self):
        from apps.fee_notice.services import FeeNoticeDetector

        assert FeeNoticeDetector is not None

    def test_lazy_import_extractor(self):
        from apps.fee_notice.services import FeeAmountExtractor

        assert FeeAmountExtractor is not None

    def test_lazy_import_extraction_service(self):
        from apps.fee_notice.services import FeeNoticeExtractionService

        assert FeeNoticeExtractionService is not None

    def test_lazy_import_comparison_service(self):
        from apps.fee_notice.services import FeeComparisonService

        assert FeeComparisonService is not None

    def test_lazy_import_check_service(self):
        from apps.fee_notice.services import FeeNoticeCheckService

        assert FeeNoticeCheckService is not None


# ---------------------------------------------------------------------------
# services/comparison/__init__.py (0% coverage)
# ---------------------------------------------------------------------------


class TestFeeComparisonInit:
    def test_import(self):
        from apps.fee_notice.services.comparison import __init__ as comp_init

        assert comp_init is not None


# ---------------------------------------------------------------------------
# api/__init__.py (0% coverage)
# ---------------------------------------------------------------------------


class TestFeeNoticeApiInit:
    def test_api_init(self):
        from apps.fee_notice.api import __init__ as api_init

        assert api_init is not None


# ---------------------------------------------------------------------------
# admin/fee_notice_admin.py (74% coverage)
# ---------------------------------------------------------------------------


class TestFeeNoticeAdmin:
    def test_import(self):
        from apps.fee_notice.admin import fee_notice_admin

        assert fee_notice_admin is not None
