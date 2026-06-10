"""Targeted tests for TokenAcquisitionHistoryAdminService."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.automation.models import TokenAcquisitionHistory, TokenAcquisitionStatus
from apps.automation.services.admin.token_acquisition_history_admin_service import TokenAcquisitionHistoryAdminService
from apps.core.exceptions import BusinessException, ValidationException


@pytest.fixture
def service():
    return TokenAcquisitionHistoryAdminService()


# Use unique site_name/account to isolate test data
TEST_SITE = "test_cleanup_site_xyz"
TEST_ACCOUNT = "test_cleanup_account_xyz"


@pytest.fixture
def success_record(db):
    return TokenAcquisitionHistory.objects.create(
        site_name=TEST_SITE,
        account=TEST_ACCOUNT,
        credential_id=1,
        status=TokenAcquisitionStatus.SUCCESS,
        trigger_reason="token_expired",
        attempt_count=1,
        total_duration=15.5,
        login_duration=10.2,
        captcha_attempts=1,
        network_retries=0,
    )


@pytest.fixture
def failed_record(db):
    return TokenAcquisitionHistory.objects.create(
        site_name=TEST_SITE,
        account=f"{TEST_ACCOUNT}_2",
        credential_id=2,
        status=TokenAcquisitionStatus.FAILED,
        trigger_reason="no_token",
        attempt_count=3,
        total_duration=30.0,
        captcha_attempts=3,
        network_retries=2,
        error_message="登录失败",
    )


@pytest.fixture
def old_record(db):
    now = timezone.now()
    record = TokenAcquisitionHistory.objects.create(
        site_name=TEST_SITE,
        account=f"{TEST_ACCOUNT}_old",
        status=TokenAcquisitionStatus.SUCCESS,
        trigger_reason="manual",
    )
    TokenAcquisitionHistory.objects.filter(pk=record.pk).update(created_at=now - timedelta(days=60))
    record.refresh_from_db()
    return record


# ── cleanup_old_records ───────────────────────────────────────────


@pytest.mark.django_db
class TestCleanupOldRecords:
    def test_invalid_days_raises(self, service):
        with pytest.raises(ValidationException, match="保留天数必须大于0"):
            service.cleanup_old_records(days=0)

    def test_negative_days_raises(self, service):
        with pytest.raises(ValidationException, match="保留天数必须大于0"):
            service.cleanup_old_records(days=-1)

    def test_deletes_old_records(self, service, old_record, success_record):
        # The cleanup method uses all records, so we just verify old_record gets deleted
        count_before = TokenAcquisitionHistory.objects.filter(site_name=TEST_SITE).count()
        assert count_before == 2
        # Cleanup all records older than 30 days
        total_cleaned = service.cleanup_old_records(days=30)
        # old_record should be deleted (60 days old), success_record should remain
        assert not TokenAcquisitionHistory.objects.filter(pk=old_record.pk).exists()
        assert TokenAcquisitionHistory.objects.filter(pk=success_record.pk).exists()

    def test_no_old_records(self, service, success_record):
        count = service.cleanup_old_records(days=30)
        # success_record was just created, so it shouldn't be cleaned up
        assert TokenAcquisitionHistory.objects.filter(pk=success_record.pk).exists()

    def test_custom_retention_days(self, service, old_record):
        count = service.cleanup_old_records(days=90)
        # 60-day-old record should survive with 90-day retention
        assert TokenAcquisitionHistory.objects.filter(pk=old_record.pk).exists()


# ── export_to_csv ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestExportToCsv:
    def test_empty_queryset_raises(self, service):
        with pytest.raises(ValidationException, match="没有选中任何记录"):
            service.export_to_csv(TokenAcquisitionHistory.objects.none())

    def test_exports_records(self, service, success_record, failed_record):
        qs = TokenAcquisitionHistory.objects.filter(site_name=TEST_SITE)
        response = service.export_to_csv(qs)
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        content = response.content.decode("utf-8-sig")
        lines = content.strip().split("\n")
        assert len(lines) >= 3  # header + 2 records (maybe more from other tests)
        assert "网站名称" in lines[0]

    def test_exports_single_record(self, service, success_record):
        qs = TokenAcquisitionHistory.objects.filter(id=success_record.id)
        response = service.export_to_csv(qs)
        content = response.content.decode("utf-8-sig")
        lines = content.strip().split("\n")
        assert len(lines) == 2


# ── reanalyze_performance ─────────────────────────────────────────


@pytest.mark.django_db
class TestReanalyzePerformance:
    def test_empty_queryset_raises(self, service):
        with pytest.raises(ValidationException, match="没有选中任何记录"):
            service.reanalyze_performance(TokenAcquisitionHistory.objects.none())

    def test_analyzes_records(self, service, success_record, failed_record):
        qs = TokenAcquisitionHistory.objects.filter(site_name=TEST_SITE)
        result = service.reanalyze_performance(qs)
        assert result["total_count"] == 2
        assert result["success_count"] == 1
        assert abs(result["success_rate"] - 50.0) < 0.1

    def test_avg_duration(self, service, success_record):
        qs = TokenAcquisitionHistory.objects.filter(pk=success_record.pk)
        result = service.reanalyze_performance(qs)
        assert result["avg_duration"] == 15.5

    def test_error_stats(self, service, failed_record):
        qs = TokenAcquisitionHistory.objects.filter(pk=failed_record.pk)
        result = service.reanalyze_performance(qs)
        assert len(result["error_stats"]) > 0

    def test_site_stats(self, service, success_record, failed_record):
        qs = TokenAcquisitionHistory.objects.filter(site_name=TEST_SITE)
        result = service.reanalyze_performance(qs)
        assert TEST_SITE in result["site_stats"]
        assert result["site_stats"][TEST_SITE]["total"] == 2
        assert result["site_stats"][TEST_SITE]["success"] == 1

    def test_account_stats(self, service, success_record, failed_record):
        qs = TokenAcquisitionHistory.objects.filter(site_name=TEST_SITE)
        result = service.reanalyze_performance(qs)
        assert TEST_ACCOUNT in result["account_stats"]
        assert f"{TEST_ACCOUNT}_2" in result["account_stats"]
        assert result["account_stats"][TEST_ACCOUNT]["success"] == 1
        assert result["account_stats"][f"{TEST_ACCOUNT}_2"]["success"] == 0


# ── get_dashboard_statistics ──────────────────────────────────────


@pytest.mark.django_db
class TestGetDashboardStatistics:
    def test_returns_valid_structure(self, service):
        result = service.get_dashboard_statistics()
        assert "total_records" in result
        assert "success_rate" in result
        assert "time_stats" in result
        assert "status_stats" in result
        assert "site_stats" in result
        assert "performance_stats" in result
        assert "trend_data" in result

    def test_time_stats_present(self, service, success_record):
        result = service.get_dashboard_statistics()
        assert "1h" in result["time_stats"]
        assert "24h" in result["time_stats"]
        assert "7d" in result["time_stats"]
        assert "30d" in result["time_stats"]

    def test_status_stats_present(self, service, success_record, failed_record):
        result = service.get_dashboard_statistics()
        assert isinstance(result["status_stats"], list)

    def test_site_stats_present(self, service, success_record):
        result = service.get_dashboard_statistics()
        assert isinstance(result["site_stats"], list)

    def test_trend_data_length(self, service, success_record):
        result = service.get_dashboard_statistics()
        assert len(result["trend_data"]) == 7
