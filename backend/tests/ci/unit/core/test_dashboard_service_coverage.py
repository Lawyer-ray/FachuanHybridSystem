"""apps/workbench/services/dashboard_service.py 单元测试。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.workbench.services.dashboard_service import (
    DashboardService,
    _case_type_stats,
    _client_count,
    _contract_count,
    _fee_stats,
    _reminder_counts,
)


class TestDashboardServiceGetStats:
    """测试 DashboardService.get_stats。"""

    def _patch_helpers(self, **overrides):
        """为 get_stats 中调用的辅助方法构建默认 patch。"""
        defaults = {
            "_client_count": 5,
            "_contract_count": 3,
            "_case_type_stats": ([{"type": "CIVIL", "label": "民事", "count": 2}], 2),
            "_case_trend": [],
            "_case_status_distribution": {"ACTIVE": 2},
            "_fee_stats": (Decimal("1000"), []),
            "_contract_trend": [],
            "_reminder_counts": {"overdue_count": 0, "today_count": 0},
            "_upcoming_reminders": [],
        }
        defaults.update(overrides)
        return defaults

    def test_get_stats_returns_expected_keys(self) -> None:
        """get_stats 返回包含所有预期 key 的字典。"""
        svc = DashboardService()
        patches = self._patch_helpers()

        with (
            patch("apps.workbench.services.dashboard_service._client_count", return_value=patches["_client_count"]),
            patch("apps.workbench.services.dashboard_service._contract_count", return_value=patches["_contract_count"]),
            patch(
                "apps.workbench.services.dashboard_service._case_type_stats", return_value=patches["_case_type_stats"]
            ),
            patch("apps.workbench.services.dashboard_service._case_trend", return_value=patches["_case_trend"]),
            patch(
                "apps.workbench.services.dashboard_service._case_status_distribution",
                return_value=patches["_case_status_distribution"],
            ),
            patch("apps.workbench.services.dashboard_service._fee_stats", return_value=patches["_fee_stats"]),
            patch("apps.workbench.services.dashboard_service._contract_trend", return_value=patches["_contract_trend"]),
            patch(
                "apps.workbench.services.dashboard_service._reminder_counts", return_value=patches["_reminder_counts"]
            ),
            patch(
                "apps.workbench.services.dashboard_service._upcoming_reminders",
                return_value=patches["_upcoming_reminders"],
            ),
        ):
            result = svc.get_stats()

        expected_keys = {
            "client_count",
            "contract_count",
            "case_count",
            "monthly_fee",
            "case_trend",
            "contract_trend",
            "fee_trend",
            "case_type_distribution",
            "case_status_distribution",
            "upcoming_reminders",
            "overdue_count",
            "today_count",
        }
        assert set(result.keys()) == expected_keys

    def test_get_stats_monthly_fee_value(self) -> None:
        """monthly_fee 值应正确传递。"""
        svc = DashboardService()
        patches = self._patch_helpers(
            _fee_stats=(Decimal("9999.50"), [{"month": "2026-06", "amount": "9999.50"}]),
        )

        with (
            patch("apps.workbench.services.dashboard_service._client_count", return_value=patches["_client_count"]),
            patch("apps.workbench.services.dashboard_service._contract_count", return_value=patches["_contract_count"]),
            patch(
                "apps.workbench.services.dashboard_service._case_type_stats", return_value=patches["_case_type_stats"]
            ),
            patch("apps.workbench.services.dashboard_service._case_trend", return_value=patches["_case_trend"]),
            patch(
                "apps.workbench.services.dashboard_service._case_status_distribution",
                return_value=patches["_case_status_distribution"],
            ),
            patch("apps.workbench.services.dashboard_service._fee_stats", return_value=patches["_fee_stats"]),
            patch("apps.workbench.services.dashboard_service._contract_trend", return_value=patches["_contract_trend"]),
            patch(
                "apps.workbench.services.dashboard_service._reminder_counts", return_value=patches["_reminder_counts"]
            ),
            patch(
                "apps.workbench.services.dashboard_service._upcoming_reminders",
                return_value=patches["_upcoming_reminders"],
            ),
        ):
            result = svc.get_stats()

        assert result["monthly_fee"] == Decimal("9999.50")

    def test_get_stats_case_count_from_type_stats(self) -> None:
        """case_count 应从 _case_type_stats 返回的 total 中提取。"""
        svc = DashboardService()
        patches = self._patch_helpers(
            _case_type_stats=(
                [{"type": "CIVIL", "label": "民事", "count": 3}, {"type": "CRIMINAL", "label": "刑事", "count": 2}],
                5,
            ),
        )

        with (
            patch("apps.workbench.services.dashboard_service._client_count", return_value=patches["_client_count"]),
            patch("apps.workbench.services.dashboard_service._contract_count", return_value=patches["_contract_count"]),
            patch(
                "apps.workbench.services.dashboard_service._case_type_stats", return_value=patches["_case_type_stats"]
            ),
            patch("apps.workbench.services.dashboard_service._case_trend", return_value=patches["_case_trend"]),
            patch(
                "apps.workbench.services.dashboard_service._case_status_distribution",
                return_value=patches["_case_status_distribution"],
            ),
            patch("apps.workbench.services.dashboard_service._fee_stats", return_value=patches["_fee_stats"]),
            patch("apps.workbench.services.dashboard_service._contract_trend", return_value=patches["_contract_trend"]),
            patch(
                "apps.workbench.services.dashboard_service._reminder_counts", return_value=patches["_reminder_counts"]
            ),
            patch(
                "apps.workbench.services.dashboard_service._upcoming_reminders",
                return_value=patches["_upcoming_reminders"],
            ),
        ):
            result = svc.get_stats()

        assert result["case_count"] == 5

    def test_get_stats_reminder_counts(self) -> None:
        """overdue_count 和 today_count 应从 _reminder_counts 中提取。"""
        svc = DashboardService()
        patches = self._patch_helpers(
            _reminder_counts={"overdue_count": 3, "today_count": 7},
        )

        with (
            patch("apps.workbench.services.dashboard_service._client_count", return_value=patches["_client_count"]),
            patch("apps.workbench.services.dashboard_service._contract_count", return_value=patches["_contract_count"]),
            patch(
                "apps.workbench.services.dashboard_service._case_type_stats", return_value=patches["_case_type_stats"]
            ),
            patch("apps.workbench.services.dashboard_service._case_trend", return_value=patches["_case_trend"]),
            patch(
                "apps.workbench.services.dashboard_service._case_status_distribution",
                return_value=patches["_case_status_distribution"],
            ),
            patch("apps.workbench.services.dashboard_service._fee_stats", return_value=patches["_fee_stats"]),
            patch("apps.workbench.services.dashboard_service._contract_trend", return_value=patches["_contract_trend"]),
            patch(
                "apps.workbench.services.dashboard_service._reminder_counts", return_value=patches["_reminder_counts"]
            ),
            patch(
                "apps.workbench.services.dashboard_service._upcoming_reminders",
                return_value=patches["_upcoming_reminders"],
            ),
        ):
            result = svc.get_stats()

        assert result["overdue_count"] == 3
        assert result["today_count"] == 7


class TestClientCount:
    """测试 _client_count。"""

    def test_returns_count(self) -> None:
        mock_model = MagicMock()
        mock_model.objects.count.return_value = 42
        with patch("apps.client.models.Client", mock_model):
            assert _client_count() == 42


class TestContractCount:
    """测试 _contract_count。"""

    def test_returns_count(self) -> None:
        mock_model = MagicMock()
        mock_model.objects.count.return_value = 10
        with patch("apps.workbench.services.dashboard_service.Contract", mock_model):
            assert _contract_count() == 10


class TestCaseTypeStats:
    """测试 _case_type_stats。"""

    def test_returns_distribution_and_total(self) -> None:
        mock_qs = MagicMock()
        mock_qs.__iter__ = MagicMock(
            return_value=iter(
                [
                    {"case_type": "CIVIL", "count": 5},
                    {"case_type": "CRIMINAL", "count": 3},
                ]
            )
        )
        mock_qs.order_by.return_value = mock_qs
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.values.return_value.annotate.return_value = mock_qs
        with patch("apps.workbench.services.dashboard_service.Case", mock_model):
            dist, total = _case_type_stats()
        assert total == 8
        assert len(dist) == 2

    def test_empty_case_types(self) -> None:
        mock_qs = MagicMock()
        mock_qs.__iter__ = MagicMock(return_value=iter([]))
        mock_qs.order_by.return_value = mock_qs
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.values.return_value.annotate.return_value = mock_qs
        with patch("apps.workbench.services.dashboard_service.Case", mock_model):
            dist, total = _case_type_stats()
        assert total == 0
        assert dist == []


class TestFeeStats:
    """测试 _fee_stats。"""

    def test_returns_monthly_fee_and_trend(self) -> None:
        monthly_agg = MagicMock()
        monthly_agg.aggregate.return_value = {"total": Decimal("5000")}

        trend_row_1 = MagicMock()
        trend_row_1.__getitem__ = lambda self, key: {"month": date(2026, 6, 1), "amount": Decimal("5000")}[key]
        trend_row_2 = MagicMock()
        trend_row_2.__getitem__ = lambda self, key: {"month": date(2026, 5, 1), "amount": Decimal("3000")}[key]

        trend_qs = MagicMock()
        trend_qs.__iter__ = MagicMock(return_value=iter([trend_row_1, trend_row_2]))
        trend_qs.annotate.return_value.values.return_value.annotate.return_value.order_by.return_value = trend_qs

        # First .filter() for trend scope, then the monthly one
        mock_model = MagicMock()
        mock_model.objects.filter.return_value = trend_qs
        # When .filter() is called again (monthly), return the monthly_agg
        trend_qs.filter.return_value = monthly_agg

        with patch("apps.workbench.services.dashboard_service.ContractPayment", mock_model):
            monthly_fee, fee_trend = _fee_stats(date(2026, 6, 1), date(2026, 6, 19), date(2025, 6, 19))
        assert monthly_fee == Decimal("5000")
        assert len(fee_trend) == 2

    def test_returns_zero_when_no_payments(self) -> None:
        monthly_agg = MagicMock()
        monthly_agg.aggregate.return_value = {"total": None}

        trend_qs = MagicMock()
        trend_qs.__iter__ = MagicMock(return_value=iter([]))
        trend_qs.annotate.return_value.values.return_value.annotate.return_value.order_by.return_value = trend_qs

        mock_model = MagicMock()
        mock_model.objects.filter.return_value = trend_qs
        trend_qs.filter.return_value = monthly_agg

        with patch("apps.workbench.services.dashboard_service.ContractPayment", mock_model):
            monthly_fee, fee_trend = _fee_stats(date(2026, 6, 1), date(2026, 6, 19), date(2025, 6, 19))
        assert monthly_fee == Decimal("0")
        assert fee_trend == []


class TestReminderCounts:
    """测试 _reminder_counts。"""

    def test_returns_overdue_and_today(self) -> None:
        mock_result = {"overdue_count": 3, "today_count": 2}
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.aggregate.return_value = mock_result
        now = datetime(2026, 6, 8, 12, 0, 0)
        with patch("apps.workbench.services.dashboard_service.Reminder", mock_model):
            result = _reminder_counts(now)
        assert result == {"overdue_count": 3, "today_count": 2}
        mock_model.objects.filter.assert_called_once()
        mock_model.objects.filter.return_value.aggregate.assert_called_once()

    def test_returns_zeros_when_no_reminders(self) -> None:
        mock_result = {"overdue_count": 0, "today_count": 0}
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.aggregate.return_value = mock_result
        now = datetime(2026, 6, 8, 12, 0, 0)
        with patch("apps.workbench.services.dashboard_service.Reminder", mock_model):
            result = _reminder_counts(now)
        assert result == {"overdue_count": 0, "today_count": 0}
