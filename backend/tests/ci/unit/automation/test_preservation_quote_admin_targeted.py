"""Targeted tests for PreservationQuoteAdminService covering stats, retry, create."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)

from django.utils import timezone

from apps.automation.models import InsuranceQuote, PreservationQuote, QuoteItemStatus, QuoteStatus
from apps.core.exceptions import BusinessException, NotFoundError, ValidationException
from plugins.court_automation.preservation_quote.admin_service import PreservationQuoteAdminService


@pytest.fixture
def service():
    return PreservationQuoteAdminService()


@pytest.fixture
def pending_quote(db):
    return PreservationQuote.objects.create(
        preserve_amount=Decimal("100000.00"),
        corp_id="2550",
        category_id="127000",
        status=QuoteStatus.PENDING,
    )


@pytest.fixture
def failed_quote(db):
    q = PreservationQuote.objects.create(
        preserve_amount=Decimal("500000.00"),
        corp_id="2550",
        category_id="127000",
        status=QuoteStatus.FAILED,
        error_message="失败原因",
        started_at=timezone.now() - timedelta(minutes=5),
        finished_at=timezone.now(),
        total_companies=5,
        success_count=0,
        failed_count=5,
    )
    # Create some old quotes
    InsuranceQuote.objects.create(
        preservation_quote=q,
        company_id="C001",
        company_code="CC001",
        company_name="保险公司A",
        status=QuoteItemStatus.FAILED,
        error_message="查询失败",
    )
    return q


@pytest.fixture
def success_quote(db):
    q = PreservationQuote.objects.create(
        preserve_amount=Decimal("200000.00"),
        corp_id="2550",
        category_id="127000",
        status=QuoteStatus.SUCCESS,
        started_at=timezone.now() - timedelta(minutes=3),
        finished_at=timezone.now(),
        total_companies=3,
        success_count=3,
        failed_count=0,
    )
    InsuranceQuote.objects.create(
        preservation_quote=q,
        company_id="C002",
        company_code="CC002",
        company_name="保险公司B",
        min_amount=Decimal("500.00"),
        status=QuoteItemStatus.SUCCESS,
    )
    return q


@pytest.fixture
def partial_quote(db):
    return PreservationQuote.objects.create(
        preserve_amount=Decimal("300000.00"),
        corp_id="2550",
        category_id="127000",
        status=QuoteStatus.PARTIAL_SUCCESS,
        started_at=timezone.now() - timedelta(minutes=2),
        finished_at=timezone.now(),
        total_companies=5,
        success_count=3,
        failed_count=2,
    )


# ── retry_failed_quotes ───────────────────────────────────────────


@pytest.mark.django_db
class TestRetryFailedQuotes:
    def test_no_failed_returns_zero(self, service, pending_quote):
        result = service.retry_failed_quotes()
        assert result["retried_count"] == 0

    def test_retries_failed(self, service, failed_quote):
        result = service.retry_failed_quotes()
        assert result["retried_count"] == 1
        failed_quote.refresh_from_db()
        assert failed_quote.status == QuoteStatus.PENDING
        assert failed_quote.error_message == ""
        assert failed_quote.started_at is None
        assert failed_quote.finished_at is None

    def test_deletes_old_quotes_on_retry(self, service, failed_quote):
        assert failed_quote.quotes.count() == 1
        service.retry_failed_quotes()
        assert failed_quote.quotes.count() == 0

    def test_retries_partial_success(self, service, partial_quote):
        result = service.retry_failed_quotes()
        assert result["retried_count"] == 1
        partial_quote.refresh_from_db()
        assert partial_quote.status == QuoteStatus.PENDING

    def test_retries_specific_ids(self, service, failed_quote, partial_quote):
        result = service.retry_failed_quotes(quote_ids=[failed_quote.id])
        assert result["retried_count"] == 1
        partial_quote.refresh_from_db()
        assert partial_quote.status == QuoteStatus.PARTIAL_SUCCESS


# ── get_quote_statistics ──────────────────────────────────────────


@pytest.mark.django_db
class TestGetQuoteStatistics:
    def test_empty(self, service):
        result = service.get_quote_statistics()
        assert result["total_quotes"] == 0
        assert result["success_rate"] == 0
        assert isinstance(result["amount_range_stats"], list)

    def test_with_quotes(self, service, pending_quote, failed_quote, success_quote):
        result = service.get_quote_statistics()
        assert result["total_quotes"] == 3
        assert result["status_stats"][QuoteStatus.PENDING]["count"] == 1
        assert result["status_stats"][QuoteStatus.FAILED]["count"] == 1
        assert result["status_stats"][QuoteStatus.SUCCESS]["count"] == 1

    def test_success_rate(self, service, success_quote, failed_quote):
        result = service.get_quote_statistics()
        assert abs(result["success_rate"] - 50.0) < 0.1

    def test_amount_range_stats(self, service, pending_quote, success_quote):
        result = service.get_quote_statistics()
        assert len(result["amount_range_stats"]) == 5

    def test_insurance_stats(self, service, success_quote):
        result = service.get_quote_statistics()
        assert isinstance(result["insurance_stats"], list)

    def test_date_stats(self, service, pending_quote):
        result = service.get_quote_statistics()
        assert len(result["date_stats"]) == 30

    def test_duration_stats(self, service, success_quote):
        result = service.get_quote_statistics()
        assert result["avg_duration"] >= 0

    def test_custom_queryset(self, service, pending_quote, success_quote):
        qs = PreservationQuote.objects.filter(status=QuoteStatus.SUCCESS)
        result = service.get_quote_statistics(queryset=qs)
        assert result["total_quotes"] == 1


# ── batch_create_quotes ───────────────────────────────────────────


@pytest.mark.django_db
class TestBatchCreateQuotes:
    def test_empty_raises(self, service):
        with pytest.raises(ValidationException, match="没有提供询价配置"):
            service.batch_create_quotes([])

    def test_creates_quotes(self, service):
        configs = [
            {"preserve_amount": 100000, "corp_id": "2550", "category_id": "127000"},
            {"preserve_amount": 200000},
        ]
        result = service.batch_create_quotes(configs)
        assert result["created_count"] == 2
        assert result["error_count"] == 0
        assert len(result["created_quote_ids"]) == 2

    def test_missing_amount_in_config(self, service):
        configs = [{"corp_id": "2550"}]
        result = service.batch_create_quotes(configs)
        assert result["created_count"] == 0
        assert result["error_count"] == 1

    def test_negative_amount(self, service):
        configs = [{"preserve_amount": -100}]
        result = service.batch_create_quotes(configs)
        assert result["created_count"] == 0
        assert result["error_count"] == 1

    def test_zero_amount(self, service):
        configs = [{"preserve_amount": 0}]
        result = service.batch_create_quotes(configs)
        assert result["created_count"] == 0
        assert result["error_count"] == 1

    def test_mixed_valid_and_invalid(self, service):
        configs = [
            {"preserve_amount": 50000},
            {"preserve_amount": -1},
            {"preserve_amount": 100000, "corp_id": "1234"},
        ]
        result = service.batch_create_quotes(configs)
        assert result["created_count"] == 2
        assert result["error_count"] == 1


# ── run_single_quote ──────────────────────────────────────────────


@pytest.mark.django_db
class TestRunSingleQuote:
    def test_not_found(self, service):
        from apps.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            service.run_single_quote(999999)

    def test_invalid_status(self, service, success_quote):
        with pytest.raises(ValidationException, match="无法执行"):
            service.run_single_quote(success_quote.id)

    @patch("apps.core.tasking.submit_task")
    def test_submits_pending(self, mock_submit, service, pending_quote):
        mock_submit.return_value = "task-123"
        result = service.run_single_quote(pending_quote.id)
        assert result["success"] is True

    @patch("apps.core.tasking.submit_task")
    def test_submits_failed(self, mock_submit, service, failed_quote):
        mock_submit.return_value = "task-456"
        result = service.run_single_quote(failed_quote.id)
        assert result["success"] is True


# ── get_quote_comparison ──────────────────────────────────────────


@pytest.mark.django_db
class TestGetQuoteComparison:
    """直接调用生产的 get_quote_comparison。

    S09-05（2026-11-23 二轮审计）：原实现用 `exec(code_text)` 跑一份手抄的源码，
    断言全落在这份拷贝上——生产方法改字段名/改统计口径/被删除都不会红；
    现在改为真调用 `PreservationQuoteAdminService.get_quote_comparison`。
    """

    def test_not_found(self, service):
        from apps.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            service.get_quote_comparison(999999)

    def test_no_successful_quotes(self, service, failed_quote):
        result = service.get_quote_comparison(failed_quote.id)
        assert result["comparison_data"] == []
        assert result["statistics"] == {}
        assert result["message"] == "暂无成功的报价数据"

    def test_with_successful_quotes(self, service, success_quote):
        # Add another successful quote
        InsuranceQuote.objects.create(
            preservation_quote=success_quote,
            company_id="C003",
            company_code="CC003",
            company_name="保险公司C",
            min_amount=Decimal("800.00"),
            max_apply_amount=Decimal("500000.00"),
            status=QuoteItemStatus.SUCCESS,
        )
        result = service.get_quote_comparison(success_quote.id)

        # 排名与排序：按 min_amount 升序，rank 从 1 递增，第一个即最优
        assert [row["rank"] for row in result["comparison_data"]] == [1, 2]
        assert [row["company_name"] for row in result["comparison_data"]] == ["保险公司B", "保险公司C"]
        assert [row["is_best"] for row in result["comparison_data"]] == [True, False]
        # 保费 500 / 保额 200000 → 费率 0.25%（口径：百分比）
        assert result["comparison_data"][0]["rate"] == pytest.approx(500.0 / 200000.0 * 100)
        assert result["comparison_data"][1]["max_apply_amount"] == 500000.0

        # 统计字段：两条成功报价 500 / 800
        statistics = result["statistics"]
        assert statistics["total_companies"] == 2
        assert statistics["min_premium"] == 500.0
        assert statistics["max_premium"] == 800.0
        assert statistics["avg_premium"] == 650.0
        assert statistics["price_range"] == 300.0
        assert statistics["savings_amount"] == 300.0
        assert statistics["savings_percentage"] == pytest.approx(300.0 / 800.0 * 100)
