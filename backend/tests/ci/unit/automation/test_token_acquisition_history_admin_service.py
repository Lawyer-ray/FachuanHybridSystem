"""Unit tests for TokenAcquisitionHistoryAdminService."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")

from django.utils import timezone

from apps.automation.models import TokenAcquisitionHistory, TokenAcquisitionStatus
from apps.automation.services.admin.token_acquisition_history_admin_service import (
    TokenAcquisitionHistoryAdminService,
)
from apps.core.exceptions import BusinessException, ValidationException


@pytest.fixture
def svc() -> TokenAcquisitionHistoryAdminService:
    return TokenAcquisitionHistoryAdminService()


@pytest.fixture
def _history_factory(db):
    """Return a factory that creates TokenAcquisitionHistory rows."""

    def _create(**kwargs):
        defaults = {
            "site_name": "court_zxfw",
            "account": "test_account",
            "status": TokenAcquisitionStatus.SUCCESS,
            "trigger_reason": "manual_trigger",
            "attempt_count": 1,
        }
        defaults.update(kwargs)
        return TokenAcquisitionHistory.objects.create(**defaults)

    return _create


class TestCleanupOldRecords:
    def test_invalid_days_raises(self, svc, db):
        with pytest.raises(ValidationException, match="大于0"):
            svc.cleanup_old_records(days=0)

    def test_negative_days_raises(self, svc, db):
        with pytest.raises(ValidationException):
            svc.cleanup_old_records(days=-5)

    def test_no_old_records(self, svc, _history_factory):
        _history_factory()  # just created → not old enough
        result = svc.cleanup_old_records(days=30)
        assert result == 0
        assert TokenAcquisitionHistory.objects.count() == 1

    def test_old_records_deleted(self, svc, _history_factory):
        old = _history_factory()
        TokenAcquisitionHistory.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=60)
        )
        result = svc.cleanup_old_records(days=30)
        assert result == 1
        assert TokenAcquisitionHistory.objects.count() == 0

    def test_keeps_recent_records(self, svc, _history_factory):
        _history_factory()  # fresh
        old = _history_factory(account="old_acc")
        TokenAcquisitionHistory.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=60)
        )
        result = svc.cleanup_old_records(days=30)
        assert result == 1
        assert TokenAcquisitionHistory.objects.count() == 1

    @patch("plugins.court_automation.token_admin.token_acquisition_history_admin_service.TokenAcquisitionHistory")
    def test_exception_wraps_in_business_exception(self, mock_model, svc, db):
        mock_model.objects.filter.return_value.count.side_effect = RuntimeError("db error")
        with pytest.raises(BusinessException):
            svc.cleanup_old_records(days=30)


class TestExportToCsv:
    def test_empty_queryset_raises(self, svc):
        qs = TokenAcquisitionHistory.objects.none()
        with pytest.raises(ValidationException, match="没有选中"):
            svc.export_to_csv(qs)

    def test_exports_records(self, svc, _history_factory):
        _history_factory()
        qs = TokenAcquisitionHistory.objects.all()
        response = svc.export_to_csv(qs)
        content = response.content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        # Header + 1 data row
        assert len(rows) == 2
        assert rows[0][1] == "网站名称"
        assert "attachment" in response["Content-Disposition"]

    def test_multiple_records(self, svc, _history_factory):
        _history_factory(account="acc1")
        _history_factory(account="acc2")
        qs = TokenAcquisitionHistory.objects.all()
        response = svc.export_to_csv(qs)
        content = response.content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 3  # header + 2 data

    def test_csv_contains_bom(self, svc, _history_factory):
        _history_factory()
        qs = TokenAcquisitionHistory.objects.all()
        response = svc.export_to_csv(qs)
        raw = response.content
        assert raw[:3] == b"\xef\xbb\xbf"


class TestReanalyzePerformance:
    def test_empty_queryset_raises(self, svc, db):
        with pytest.raises(ValidationException, match="没有选中"):
            svc.reanalyze_performance(TokenAcquisitionHistory.objects.none())

    def test_all_success(self, svc, _history_factory):
        _history_factory(status=TokenAcquisitionStatus.SUCCESS, total_duration=2.0)
        _history_factory(status=TokenAcquisitionStatus.SUCCESS, total_duration=4.0, account="a2")
        qs = TokenAcquisitionHistory.objects.all()
        result = svc.reanalyze_performance(qs)
        assert result["total_count"] == 2
        assert result["success_count"] == 2
        assert result["success_rate"] == 100.0
        assert result["avg_duration"] == 3.0

    def test_mixed_results(self, svc, _history_factory):
        _history_factory(status=TokenAcquisitionStatus.SUCCESS, total_duration=2.0)
        _history_factory(status=TokenAcquisitionStatus.FAILED, account="fail_acc")
        qs = TokenAcquisitionHistory.objects.all()
        result = svc.reanalyze_performance(qs)
        assert result["total_count"] == 2
        assert result["success_count"] == 1
        assert result["success_rate"] == 50.0

    def test_error_stats_populated(self, svc, _history_factory):
        _history_factory(status=TokenAcquisitionStatus.CAPTCHA_ERROR)
        qs = TokenAcquisitionHistory.objects.all()
        result = svc.reanalyze_performance(qs)
        assert len(result["error_stats"]) >= 1

    def test_site_stats(self, svc, _history_factory):
        _history_factory(site_name="site_a")
        _history_factory(site_name="site_a", account="a2")
        qs = TokenAcquisitionHistory.objects.all()
        result = svc.reanalyze_performance(qs)
        assert "site_a" in result["site_stats"]

    def test_account_stats(self, svc, _history_factory):
        _history_factory(account="user1", total_duration=1.5)
        qs = TokenAcquisitionHistory.objects.all()
        result = svc.reanalyze_performance(qs)
        assert "user1" in result["account_stats"]


class TestGetDashboardStatistics:
    def test_empty_db(self, svc, db):
        result = svc.get_dashboard_statistics()
        assert result["total_records"] == 0
        assert result["success_records"] == 0
        assert result["success_rate"] == 0
        assert len(result["trend_data"]) == 7

    def test_with_records(self, svc, db, _history_factory):
        _history_factory(status=TokenAcquisitionStatus.SUCCESS)
        _history_factory(status=TokenAcquisitionStatus.FAILED, account="fail")
        result = svc.get_dashboard_statistics()
        assert result["total_records"] == 2
        assert result["success_records"] == 1
        assert result["success_rate"] == 50.0
        assert len(result["site_stats"]) >= 1
        assert len(result["status_stats"]) >= 1

    def test_trend_data_structure(self, svc, db):
        result = svc.get_dashboard_statistics()
        assert len(result["trend_data"]) == 7
        for day in result["trend_data"]:
            assert "date" in day
            assert "total" in day
            assert "success" in day
            assert "rate" in day
