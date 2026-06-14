"""Coverage tests for finance/services/lpr/rate_service.py."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.finance.services.lpr.rate_service import LPRRateService, PrincipalPeriod, RateSegment


class TestPrincipalPeriod:
    def test_creation(self) -> None:
        pp = PrincipalPeriod(start_date=date(2024, 1, 1), end_date=date(2024, 6, 30), principal=Decimal("100000"))
        assert pp.start_date == date(2024, 1, 1)
        assert pp.principal == Decimal("100000")


class TestLPRRateService:
    def setup_method(self) -> None:
        self.service = LPRRateService()

    def test_get_rate_at_found(self) -> None:
        mock_rate = MagicMock()
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value.first.return_value = mock_rate
            result = self.service.get_rate_at(date(2024, 6, 15))
            assert result is mock_rate

    def test_get_rate_at_not_found(self) -> None:
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value.first.return_value = None
            with pytest.raises(ValidationException) as exc_info:
                self.service.get_rate_at(date(2024, 1, 1))
            assert "LPR_RATE_NOT_FOUND" in exc_info.value.code

    def test_get_rate_by_date_range_1y(self) -> None:
        mock_rate = MagicMock()
        mock_rate.rate_1y = Decimal("3.45")
        mock_rate.rate_5y = Decimal("4.20")
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value.first.return_value = mock_rate
            result = self.service.get_rate_by_date_range(date(2024, 1, 1), date(2024, 12, 31), rate_type="1y")
            assert result == Decimal("3.45")

    def test_get_rate_by_date_range_5y(self) -> None:
        mock_rate = MagicMock()
        mock_rate.rate_5y = Decimal("4.20")
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value.first.return_value = mock_rate
            result = self.service.get_rate_by_date_range(date(2024, 1, 1), date(2024, 12, 31), rate_type="5y")
            assert result == Decimal("4.20")

    def test_get_rate_segments_basic(self) -> None:
        mock_rate1 = MagicMock()
        mock_rate1.effective_date = date(2024, 1, 1)
        mock_rate1.rate_1y = Decimal("3.45")
        mock_rate1.rate_5y = Decimal("4.20")

        mock_rate2 = MagicMock()
        mock_rate2.effective_date = date(2024, 7, 1)
        mock_rate2.rate_1y = Decimal("3.40")
        mock_rate2.rate_5y = Decimal("4.15")

        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value.__iter__ = lambda self: iter([mock_rate1, mock_rate2])
            mock_model.objects.filter.return_value.order_by.return_value.__bool__ = lambda self: True
            mock_model.objects.filter.return_value.order_by.return_value.__len__ = lambda self: 2
            result = self.service.get_rate_segments(date(2024, 1, 1), date(2024, 12, 31))
            assert len(result) >= 1
            assert all(isinstance(seg, RateSegment) for seg in result)

    def test_get_rate_segments_no_data(self) -> None:
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value.__iter__ = lambda self: iter([])
            mock_model.objects.filter.return_value.order_by.return_value.__bool__ = lambda self: False
            with pytest.raises(ValidationException) as exc_info:
                self.service.get_rate_segments(date(2024, 1, 1), date(2024, 12, 31))
            assert "LPR_RATE_NOT_FOUND" in exc_info.value.code

    def test_get_rate_segments_empty_after_filter(self) -> None:
        """When all segments are filtered out (seg_start > seg_end), raises ValidationException."""
        mock_rate = MagicMock()
        mock_rate.effective_date = date(2099, 1, 1)
        mock_rate.rate_1y = Decimal("3.45")
        mock_rate.rate_5y = Decimal("4.20")

        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value.__iter__ = lambda self: iter([mock_rate])
            mock_model.objects.filter.return_value.order_by.return_value.__bool__ = lambda self: True
            mock_model.objects.filter.return_value.order_by.return_value.__len__ = lambda self: 1
            with pytest.raises(ValidationException) as exc_info:
                self.service.get_rate_segments(date(2024, 1, 1), date(2024, 12, 31))
            assert "LPR_RATE_NOT_FOUND" in exc_info.value.code

    def test_get_latest_rate_found(self) -> None:
        mock_rate = MagicMock()
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.first.return_value = mock_rate
            result = self.service.get_latest_rate()
            assert result is mock_rate

    def test_get_latest_rate_not_found(self) -> None:
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.first.return_value = None
            with pytest.raises(ValidationException) as exc_info:
                self.service.get_latest_rate()
            assert "LPR_RATE_NOT_FOUND" in exc_info.value.code


class TestIsDataCurrent:
    def setup_method(self) -> None:
        self.service = LPRRateService()

    def test_current_same_month(self) -> None:
        mock_rate = MagicMock()
        mock_rate.effective_date = date(2025, 6, 1)
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.first.return_value = mock_rate
            with patch("apps.finance.services.lpr.rate_service.date") as mock_date:
                mock_date.today.return_value = date(2025, 6, 15)
                assert self.service.is_data_current() is True

    def test_not_current_future_month(self) -> None:
        mock_rate = MagicMock()
        mock_rate.effective_date = date(2025, 3, 1)
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.first.return_value = mock_rate
            with patch("apps.finance.services.lpr.rate_service.date") as mock_date:
                mock_date.today.return_value = date(2025, 6, 15)
                assert self.service.is_data_current() is False

    def test_current_last_month_before_20th(self) -> None:
        mock_rate = MagicMock()
        mock_rate.effective_date = date(2025, 5, 1)
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.first.return_value = mock_rate
            with patch("apps.finance.services.lpr.rate_service.date") as mock_date:
                mock_date.today.return_value = date(2025, 6, 10)
                assert self.service.is_data_current() is True

    def test_current_december_to_january(self) -> None:
        mock_rate = MagicMock()
        mock_rate.effective_date = date(2024, 12, 1)
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.first.return_value = mock_rate
            with patch("apps.finance.services.lpr.rate_service.date") as mock_date:
                mock_date.today.return_value = date(2025, 1, 10)
                assert self.service.is_data_current() is True

    def test_no_data_returns_false(self) -> None:
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.first.return_value = None
            assert self.service.is_data_current() is False

    def test_not_current_on_25th_last_month(self) -> None:
        mock_rate = MagicMock()
        mock_rate.effective_date = date(2025, 5, 1)
        with patch("apps.finance.models.lpr_rate.LPRRate") as mock_model:
            mock_model.objects.first.return_value = mock_rate
            with patch("apps.finance.services.lpr.rate_service.date") as mock_date:
                mock_date.today.return_value = date(2025, 6, 25)
                assert self.service.is_data_current() is False
