"""Targeted tests for finance module to push coverage to 80%+."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# schemas/lpr_schemas.py (0% coverage)
# ---------------------------------------------------------------------------


class TestLPRSchemas:
    def test_lpr_rate_schema(self):
        from apps.finance.schemas.lpr_schemas import LPRRateSchema

        schema = LPRRateSchema(
            id=1, effective_date=date(2024, 1, 1),
            rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"),
            source="PBOC", is_auto_synced=True,
            created_at="2024-01-01", updated_at="2024-01-01",
        )
        assert schema.id == 1

    def test_lpr_rate_list_response(self):
        from apps.finance.schemas.lpr_schemas import LPRRateListResponse, LPRRateSchema

        rate = LPRRateSchema(
            id=1, effective_date=date(2024, 1, 1),
            rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"),
            source="", is_auto_synced=False,
            created_at="2024-01-01", updated_at="2024-01-01",
        )
        resp = LPRRateListResponse(items=[rate], total=1)
        assert len(resp.items) == 1

    def test_lpr_sync_request(self):
        from apps.finance.schemas.lpr_schemas import LPRSyncRequest

        assert LPRSyncRequest(force=True).force is True
        assert LPRSyncRequest().force is False

    def test_lpr_sync_response(self):
        from apps.finance.schemas.lpr_schemas import LPRSyncResponse

        resp = LPRSyncResponse(success=True, message="OK", created=5, updated=2, skipped=1)
        assert resp.created == 5

    def test_lpr_sync_status_response(self):
        from apps.finance.schemas.lpr_schemas import LPRSyncStatusResponse

        resp = LPRSyncStatusResponse(
            latest_rate_date=date(2024, 6, 20),
            total_records=50, auto_synced_records=48, manual_records=2,
        )
        assert resp.total_records == 50

    def test_principal_change_schema(self):
        from apps.finance.schemas.lpr_schemas import PrincipalChangeSchema

        schema = PrincipalChangeSchema(
            start_date=date(2024, 1, 1), end_date=date(2024, 6, 30),
            principal=Decimal("100000"),
        )
        assert schema.principal == Decimal("100000")

    def test_interest_calculate_request_lpr(self):
        from apps.finance.schemas.lpr_schemas import InterestCalculateRequest

        req = InterestCalculateRequest(
            start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
            principal=Decimal("50000"), rate_mode="lpr", rate_type="1y",
        )
        assert req.rate_mode == "lpr"
        assert req.multiplier == Decimal("1")
        assert req.year_days == 360

    def test_interest_calculate_request_custom(self):
        from apps.finance.schemas.lpr_schemas import InterestCalculateRequest

        req = InterestCalculateRequest(
            rate_mode="custom", custom_rate_unit="permille",
            custom_rate_value=Decimal("5"),
        )
        assert req.custom_rate_unit == "permille"

    def test_interest_calculate_request_with_changes(self):
        from apps.finance.schemas.lpr_schemas import InterestCalculateRequest, PrincipalChangeSchema

        changes = [PrincipalChangeSchema(
            start_date=date(2024, 1, 1), end_date=date(2024, 6, 30),
            principal=Decimal("100000"),
        )]
        req = InterestCalculateRequest(principal_changes=changes)
        assert len(req.principal_changes) == 1

    def test_calculation_period_schema(self):
        from apps.finance.schemas.lpr_schemas import CalculationPeriodSchema

        schema = CalculationPeriodSchema(
            start_date=date(2024, 1, 1), end_date=date(2024, 6, 30),
            principal=Decimal("100000"), rate=Decimal("3.45"),
            rate_unit="percent", days=181, year_days=365,
            interest=Decimal("1710.41"),
        )
        assert schema.days == 181

    def test_interest_calculate_response(self):
        from apps.finance.schemas.lpr_schemas import InterestCalculateResponse

        resp = InterestCalculateResponse(
            success=True, total_interest=Decimal("5000"),
            total_principal=Decimal("100000"), total_days=365,
        )
        assert resp.success is True
        assert resp.code is None
        assert resp.sync_info is None


# ---------------------------------------------------------------------------
# services/lpr/rate_service.py (32% coverage)
# ---------------------------------------------------------------------------


class TestLPRRateService:
    def test_rate_segment(self):
        from apps.finance.services.lpr.rate_service import RateSegment

        seg = RateSegment(
            start=date(2024, 1, 1), end=date(2024, 6, 30),
            rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"),
        )
        assert seg.start == date(2024, 1, 1)

    def test_principal_period(self):
        from apps.finance.services.lpr.rate_service import PrincipalPeriod

        period = PrincipalPeriod(
            start_date=date(2024, 1, 1), end_date=date(2024, 6, 30),
            principal=Decimal("100000"),
        )
        assert period.principal == Decimal("100000")

    @patch("apps.finance.models.lpr_rate.LPRRate")
    def test_get_rate_at_not_found(self, mock_model):
        from apps.finance.services.lpr.rate_service import LPRRateService

        mock_model.objects.filter.return_value.order_by.return_value.first.return_value = None
        service = LPRRateService()
        with pytest.raises(Exception):
            service.get_rate_at(date(2024, 1, 1))

    @patch("apps.finance.models.lpr_rate.LPRRate")
    def test_get_rate_at_found(self, mock_model):
        from apps.finance.services.lpr.rate_service import LPRRateService

        mock_rate = SimpleNamespace(rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"))
        mock_model.objects.filter.return_value.order_by.return_value.first.return_value = mock_rate
        service = LPRRateService()
        result = service.get_rate_at(date(2024, 6, 20))
        assert result.rate_1y == Decimal("3.45")

    @patch("apps.finance.models.lpr_rate.LPRRate")
    def test_get_rate_by_date_range_1y(self, mock_model):
        from apps.finance.services.lpr.rate_service import LPRRateService

        mock_rate = SimpleNamespace(rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"))
        mock_model.objects.filter.return_value.order_by.return_value.first.return_value = mock_rate
        service = LPRRateService()
        assert service.get_rate_by_date_range(date(2024, 1, 1), date(2024, 12, 31), "1y") == Decimal("3.45")

    @patch("apps.finance.models.lpr_rate.LPRRate")
    def test_get_rate_by_date_range_5y(self, mock_model):
        from apps.finance.services.lpr.rate_service import LPRRateService

        mock_rate = SimpleNamespace(rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"))
        mock_model.objects.filter.return_value.order_by.return_value.first.return_value = mock_rate
        service = LPRRateService()
        assert service.get_rate_by_date_range(date(2024, 1, 1), date(2024, 12, 31), "5y") == Decimal("3.95")

    @patch("apps.finance.models.lpr_rate.LPRRate")
    def test_get_rate_segments_empty(self, mock_model):
        from apps.finance.services.lpr.rate_service import LPRRateService

        mock_model.objects.filter.return_value.order_by.return_value = []
        service = LPRRateService()
        with pytest.raises(Exception):
            service.get_rate_segments(date(2024, 1, 1), date(2024, 12, 31))

    @patch("apps.finance.models.lpr_rate.LPRRate")
    def test_get_latest_rate_not_found(self, mock_model):
        from apps.finance.services.lpr.rate_service import LPRRateService

        mock_model.objects.first.return_value = None
        service = LPRRateService()
        with pytest.raises(Exception):
            service.get_latest_rate()

    @patch("apps.finance.models.lpr_rate.LPRRate")
    def test_get_latest_rate_found(self, mock_model):
        from apps.finance.services.lpr.rate_service import LPRRateService

        mock_rate = SimpleNamespace(
            rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"),
            effective_date=date(2024, 6, 20),
        )
        mock_model.objects.first.return_value = mock_rate
        service = LPRRateService()
        assert service.get_latest_rate().rate_1y == Decimal("3.45")

    @patch("apps.finance.services.lpr.rate_service.LPRRateService.get_latest_rate")
    def test_is_data_current_same_month(self, mock_get_latest):
        from apps.finance.services.lpr.rate_service import LPRRateService

        mock_get_latest.return_value = SimpleNamespace(effective_date=date.today().replace(day=20))
        service = LPRRateService()
        assert service.is_data_current() is True

    @patch("apps.finance.services.lpr.rate_service.LPRRateService.get_latest_rate")
    def test_is_data_current_no_data(self, mock_get_latest):
        from apps.core.exceptions import ValidationException
        from apps.finance.services.lpr.rate_service import LPRRateService

        mock_get_latest.side_effect = ValidationException(message="no data", code="NO_DATA")
        service = LPRRateService()
        assert service.is_data_current() is False

    @patch("apps.finance.models.lpr_rate.LPRRate")
    def test_get_rate_history(self, mock_model):
        from apps.finance.services.lpr.rate_service import LPRRateService

        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_model.objects.all.return_value = mock_qs
        service = LPRRateService()
        result = service.get_rate_history(start_date=date(2020, 1, 1), end_date=date(2024, 12, 31))
        assert isinstance(result, list)

    @patch("apps.finance.models.lpr_rate.LPRRate")
    def test_get_rate_history_with_limit(self, mock_model):
        from apps.finance.services.lpr.rate_service import LPRRateService

        mock_qs = MagicMock()
        mock_qs.__getitem__ = MagicMock(return_value=[])
        mock_model.objects.all.return_value = mock_qs
        service = LPRRateService()
        result = service.get_rate_history(limit=10)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# admin/lpr_admin.py (43% coverage)
# ---------------------------------------------------------------------------


class TestLPRAdmin:
    def test_admin_import(self):
        from apps.finance.admin import lpr_admin

        assert lpr_admin is not None


# ---------------------------------------------------------------------------
# api/__init__.py, schemas/__init__.py (0% coverage)
# ---------------------------------------------------------------------------


class TestFinanceInit:
    def test_api_init(self):
        from apps.finance.api import __init__ as api_init

        assert api_init is not None

    def test_schemas_init(self):
        from apps.finance.schemas import __init__ as schemas_init

        assert schemas_init is not None
