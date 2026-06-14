"""补充覆盖测试: finance/services/lpr/sync_service.py (35 missing)

覆盖: _parse_date, _parse_rate, sync_latest (成功/失败), get_sync_status.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import BusinessException
from apps.finance.services.lpr.sync_service import LPRData, LPRSyncService


# ── _parse_date ───────────────────────────────────────────────────


class TestParseDate:
    def test_chinese_date_format(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_date("2024年3月20日")
        assert result == date(2024, 3, 20)

    def test_dash_date_format(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_date("2024-3-20")
        assert result == date(2024, 3, 20)

    def test_slash_date_format(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_date("2024/03/20")
        assert result == date(2024, 3, 20)

    def test_invalid_date_returns_none(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_date("2024-13-40")
        assert result is None

    def test_no_pattern_match(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_date("no date here")
        assert result is None

    def test_empty_string(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_date("")
        assert result is None


# ── _parse_rate ───────────────────────────────────────────────────


class TestParseRate:
    def test_rate_with_percent(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_rate("3.45%")
        assert result == Decimal("3.45")

    def test_rate_without_percent(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_rate("3.45")
        assert result == Decimal("3.45")

    def test_rate_over_10_divided_by_100(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_rate("345")
        assert result == Decimal("3.45")

    def test_invalid_rate_returns_none(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_rate("abc")
        assert result is None

    def test_empty_rate(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_rate("")
        assert result is None

    def test_rate_exactly_10(self) -> None:
        svc = LPRSyncService()
        result = svc._parse_rate("10%")
        assert result == Decimal("10")


# ── sync_latest ───────────────────────────────────────────────────


class TestSyncLatest:
    def test_sync_success(self) -> None:
        svc = LPRSyncService()
        lpr_data = [LPRData(effective_date=date(2025, 1, 20), rate_1y=Decimal("3.1"), rate_5y=Decimal("3.6"))]

        with patch.object(svc, "_fetch_with_playwright", return_value=lpr_data), \
             patch.object(svc, "_save_lpr_data", return_value={"created": 1, "updated": 0, "skipped": 0, "total": 1}) as mock_save:
            result = svc.sync_latest()
            assert result["created"] == 1
            mock_save.assert_called_once_with(lpr_data)

    def test_sync_fetch_fails(self) -> None:
        svc = LPRSyncService()
        with patch.object(svc, "_fetch_with_playwright", side_effect=Exception("network error")):
            with pytest.raises(BusinessException, match="获取LPR数据失败"):
                svc.sync_latest()

    def test_sync_empty_data(self) -> None:
        svc = LPRSyncService()
        with patch.object(svc, "_fetch_with_playwright", return_value=[]):
            with pytest.raises(BusinessException, match="无法从央行官网获取LPR数据"):
                svc.sync_latest()


# ── get_sync_status ───────────────────────────────────────────────


class TestGetSyncStatus:
    def test_no_data(self) -> None:
        svc = LPRSyncService()
        with patch("apps.finance.models.lpr_rate.LPRRate") as MockRate:
            MockRate.objects.first.return_value = None
            MockRate.objects.filter.return_value.count.return_value = 0
            MockRate.objects.count.return_value = 0
            result = svc.get_sync_status()
            assert result["latest_rate_date"] is None
            assert result["total_records"] == 0

    def test_with_data(self) -> None:
        svc = LPRSyncService()
        mock_rate = MagicMock()
        mock_rate.effective_date = date(2025, 1, 20)
        with patch("apps.finance.models.lpr_rate.LPRRate") as MockRate:
            MockRate.objects.first.return_value = mock_rate
            MockRate.objects.filter.return_value.count.return_value = 8
            MockRate.objects.count.return_value = 10
            result = svc.get_sync_status()
            assert result["latest_rate_date"] == date(2025, 1, 20)
            assert result["total_records"] == 10
            assert result["auto_synced_records"] == 8
            assert result["manual_records"] == 2
