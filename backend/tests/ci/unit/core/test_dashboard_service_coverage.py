"""apps/workbench/services/dashboard_service.py 单元测试。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.workbench.services.dashboard_service import DashboardService


class TestDashboardServiceGetStats:
    """测试 DashboardService.get_stats。"""

    def test_get_stats_returns_expected_keys(self) -> None:
        """get_stats 返回包含所有预期 key 的字典。"""
        svc = DashboardService()

        with (
            patch.object(DashboardService, "_client_count", return_value=5),
            patch.object(DashboardService, "_contract_count", return_value=3),
            patch.object(DashboardService, "_active_case_count", return_value=2),
            patch.object(DashboardService, "_monthly_fee", return_value=Decimal("1000")),
            patch.object(DashboardService, "_case_trend", return_value=[]),
            patch.object(DashboardService, "_contract_trend", return_value=[]),
            patch.object(DashboardService, "_fee_trend", return_value=[]),
            patch.object(DashboardService, "_case_type_distribution", return_value=[]),
            patch.object(DashboardService, "_case_status_distribution", return_value={}),
            patch.object(DashboardService, "_upcoming_reminders", return_value=[]),
            patch.object(DashboardService, "_overdue_count", return_value=0),
            patch.object(DashboardService, "_today_count", return_value=0),
        ):
            result = svc.get_stats()

        expected_keys = {
            "client_count", "contract_count", "case_count", "monthly_fee",
            "case_trend", "contract_trend", "fee_trend",
            "case_type_distribution", "case_status_distribution",
            "upcoming_reminders", "overdue_count", "today_count",
        }
        assert set(result.keys()) == expected_keys

    def test_get_stats_monthly_fee_value(self) -> None:
        """monthly_fee 值应正确传递。"""
        svc = DashboardService()

        with (
            patch.object(DashboardService, "_client_count", return_value=0),
            patch.object(DashboardService, "_contract_count", return_value=0),
            patch.object(DashboardService, "_active_case_count", return_value=0),
            patch.object(DashboardService, "_monthly_fee", return_value=Decimal("9999.50")),
            patch.object(DashboardService, "_case_trend", return_value=[]),
            patch.object(DashboardService, "_contract_trend", return_value=[]),
            patch.object(DashboardService, "_fee_trend", return_value=[]),
            patch.object(DashboardService, "_case_type_distribution", return_value=[]),
            patch.object(DashboardService, "_case_status_distribution", return_value={}),
            patch.object(DashboardService, "_upcoming_reminders", return_value=[]),
            patch.object(DashboardService, "_overdue_count", return_value=0),
            patch.object(DashboardService, "_today_count", return_value=0),
        ):
            result = svc.get_stats()

        assert result["monthly_fee"] == Decimal("9999.50")


class TestClientCount:
    """测试 _client_count。"""

    def test_returns_count(self) -> None:
        mock_model = MagicMock()
        mock_model.objects.count.return_value = 42
        with patch("apps.client.models.Client", mock_model):
            assert DashboardService._client_count() == 42


class TestContractCount:
    """测试 _contract_count。"""

    def test_returns_count(self) -> None:
        mock_model = MagicMock()
        mock_model.objects.count.return_value = 10
        with patch("apps.workbench.services.dashboard_service.Contract", mock_model):
            assert DashboardService._contract_count() == 10


class TestActiveCaseCount:
    """测试 _active_case_count。"""

    def test_filters_by_active_status(self) -> None:
        mock_qs = MagicMock()
        mock_qs.count.return_value = 7
        mock_model = MagicMock()
        mock_model.objects.filter.return_value = mock_qs
        with patch("apps.workbench.services.dashboard_service.Case", mock_model):
            result = DashboardService._active_case_count()
            assert result == 7
            mock_model.objects.filter.assert_called_once()


class TestMonthlyFee:
    """测试 _monthly_fee。"""

    def test_returns_aggregated_total(self) -> None:
        mock_qs = MagicMock()
        mock_qs.aggregate.return_value = {"total": Decimal("5000")}
        mock_model = MagicMock()
        mock_model.objects.filter.return_value = mock_qs
        with patch("apps.workbench.services.dashboard_service.ContractPayment", mock_model):
            result = DashboardService._monthly_fee(date(2026, 1, 1), date(2026, 1, 31))
            assert result == Decimal("5000")

    def test_returns_zero_when_no_payments(self) -> None:
        mock_qs = MagicMock()
        mock_qs.aggregate.return_value = {"total": None}
        mock_model = MagicMock()
        mock_model.objects.filter.return_value = mock_qs
        with patch("apps.workbench.services.dashboard_service.ContractPayment", mock_model):
            result = DashboardService._monthly_fee(date(2026, 1, 1), date(2026, 1, 31))
            assert result == Decimal("0")


class TestOverdueCount:
    """测试 _overdue_count。"""

    def test_returns_count(self) -> None:
        mock_qs = MagicMock()
        mock_qs.count.return_value = 3
        mock_model = MagicMock()
        mock_model.objects.filter.return_value = mock_qs
        now = datetime(2026, 6, 8, 12, 0, 0)
        with patch("apps.workbench.services.dashboard_service.Reminder", mock_model):
            result = DashboardService._overdue_count(now)
            assert result == 3


class TestTodayCount:
    """测试 _today_count。"""

    def test_returns_count(self) -> None:
        mock_qs = MagicMock()
        mock_qs.count.return_value = 2
        mock_model = MagicMock()
        mock_model.objects.filter.return_value = mock_qs
        now = datetime(2026, 6, 8, 12, 0, 0)
        with patch("apps.workbench.services.dashboard_service.Reminder", mock_model):
            result = DashboardService._today_count(now)
            assert result == 2
