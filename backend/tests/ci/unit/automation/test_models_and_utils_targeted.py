"""Targeted tests for models (str, methods, properties) and utils."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.automation.models import (
    CourtDocument,
    CourtSMS,
    CourtSMSStatus,
    CourtSMSType,
    CourtToken,
    DocumentDownloadStatus,
    InsuranceQuote,
    PreservationQuote,
    QuoteItemStatus,
    QuoteStatus,
    ScraperTask,
    ScraperTaskStatus,
    ScraperTaskType,
    TokenAcquisitionHistory,
    TokenAcquisitionStatus,
)


# ── CourtToken ────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCourtToken:
    def test_str(self):
        token = CourtToken.objects.create(
            site_name="court_zxfw",
            account="test_account",
            token="test_token_value",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert "court_zxfw" in str(token)
        assert "test_account" in str(token)

    def test_is_expired_true(self):
        token = CourtToken.objects.create(
            site_name="court_zxfw",
            account="expired_account",
            token="expired_token",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        assert token.is_expired() is True

    def test_is_expired_false(self):
        token = CourtToken.objects.create(
            site_name="court_zxfw",
            account="valid_account",
            token="valid_token",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert token.is_expired() is False


# ── TokenAcquisitionHistory ───────────────────────────────────────


@pytest.mark.django_db
class TestTokenAcquisitionHistory:
    def test_str(self):
        record = TokenAcquisitionHistory.objects.create(
            site_name="court_zxfw",
            account="test_account",
            status=TokenAcquisitionStatus.SUCCESS,
            trigger_reason="token_expired",
        )
        result = str(record)
        assert "court_zxfw" in result
        assert "test_account" in result

    def test_get_success_rate_display_success(self):
        record = TokenAcquisitionHistory.objects.create(
            site_name="court_zxfw",
            account="test_account",
            status=TokenAcquisitionStatus.SUCCESS,
            trigger_reason="manual",
        )
        assert record.get_success_rate_display() == "100%"

    def test_get_success_rate_display_failure(self):
        record = TokenAcquisitionHistory.objects.create(
            site_name="court_zxfw",
            account="test_account",
            status=TokenAcquisitionStatus.FAILED,
            trigger_reason="manual",
        )
        assert record.get_success_rate_display() == "0%"


# ── ScraperTask ───────────────────────────────────────────────────


@pytest.mark.django_db
class TestScraperTask:
    def test_str(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
        )
        result = str(task)
        assert "下载司法文书" in result

    def test_can_retry_true(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            retry_count=1,
            max_retries=3,
        )
        assert task.can_retry() is True

    def test_can_retry_false(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            retry_count=3,
            max_retries=3,
        )
        assert task.can_retry() is False

    def test_should_execute_now_no_schedule(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            scheduled_at=None,
        )
        assert task.should_execute_now() is True

    def test_should_execute_now_past_schedule(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            scheduled_at=timezone.now() - timedelta(minutes=5),
        )
        assert task.should_execute_now() is True

    def test_should_execute_now_future_schedule(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            scheduled_at=timezone.now() + timedelta(hours=1),
        )
        assert task.should_execute_now() is False


# ── PreservationQuote ─────────────────────────────────────────────


@pytest.mark.django_db
class TestPreservationQuoteModel:
    def test_str(self):
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000.00"),
            corp_id="2550",
            category_id="127000",
        )
        result = str(quote)
        assert "100000" in result

    def test_get_success_rate_zero(self):
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000"),
            corp_id="2550",
            category_id="127000",
            total_companies=0,
        )
        assert quote.get_success_rate() == 0.0

    def test_get_success_rate_partial(self):
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000"),
            corp_id="2550",
            category_id="127000",
            total_companies=10,
            success_count=7,
        )
        assert quote.get_success_rate() == 70.0


# ── InsuranceQuote ────────────────────────────────────────────────


@pytest.mark.django_db
class TestInsuranceQuoteModel:
    def test_str_with_amount(self):
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000"),
            corp_id="2550",
            category_id="127000",
        )
        iq = InsuranceQuote.objects.create(
            preservation_quote=quote,
            company_id="C001",
            company_code="CC001",
            company_name="测试保险公司",
            min_amount=Decimal("500.00"),
            status=QuoteItemStatus.SUCCESS,
        )
        assert "测试保险公司" in str(iq)
        assert "500" in str(iq)

    def test_str_without_amount(self):
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000"),
            corp_id="2550",
            category_id="127000",
        )
        iq = InsuranceQuote.objects.create(
            preservation_quote=quote,
            company_id="C001",
            company_code="CC001",
            company_name="测试保险公司",
            status=QuoteItemStatus.FAILED,
        )
        assert "失败" in str(iq)


# ── CourtDocument ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestCourtDocumentModel:
    def test_str(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
        )
        doc = CourtDocument.objects.create(
            scraper_task=task,
            c_sdbh="SD001",
            c_stbh="ST001",
            wjlj="https://example.com/doc.pdf",
            c_wsbh="WS001",
            c_wsmc="判决书",
            c_fybh="FY001",
            c_fymc="北京法院",
            c_wjgs="pdf",
            dt_cjsj=timezone.now(),
        )
        assert "判决书" in str(doc)

    def test_absolute_file_path_relative(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
        )
        doc = CourtDocument.objects.create(
            scraper_task=task,
            c_sdbh="SD002",
            c_stbh="ST002",
            wjlj="https://example.com/doc.pdf",
            c_wsbh="WS002",
            c_wsmc="调解书",
            c_fybh="FY001",
            c_fymc="北京法院",
            c_wjgs="pdf",
            dt_cjsj=timezone.now(),
            local_file_path="court_documents/test.pdf",
        )
        path = doc.absolute_file_path
        assert "court_documents" in path

    def test_absolute_file_path_empty(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
        )
        doc = CourtDocument.objects.create(
            scraper_task=task,
            c_sdbh="SD003",
            c_stbh="ST003",
            wjlj="https://example.com/doc.pdf",
            c_wsbh="WS003",
            c_wsmc="裁定书",
            c_fybh="FY001",
            c_fymc="北京法院",
            c_wjgs="pdf",
            dt_cjsj=timezone.now(),
            local_file_path=None,
        )
        assert doc.absolute_file_path == ""

    def test_absolute_file_path_absolute(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
        )
        doc = CourtDocument.objects.create(
            scraper_task=task,
            c_sdbh="SD004",
            c_stbh="ST004",
            wjlj="https://example.com/doc.pdf",
            c_wsbh="WS004",
            c_wsmc="通知",
            c_fybh="FY001",
            c_fymc="北京法院",
            c_wjgs="pdf",
            dt_cjsj=timezone.now(),
            local_file_path="/absolute/path/doc.pdf",
        )
        assert doc.absolute_file_path == "/absolute/path/doc.pdf"


# ── CourtSMS ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCourtSMSModel:
    def test_str(self):
        sms = CourtSMS.objects.create(
            content="测试短信",
            received_at=timezone.now(),
            sms_type=CourtSMSType.DOCUMENT_DELIVERY,
            status=CourtSMSStatus.PENDING,
        )
        result = str(sms)
        assert "文书送达" in result


# ── text_utils ────────────────────────────────────────────────────


class TestTextUtils:
    def test_extract_case_numbers(self):
        from apps.automation.utils.text_utils import TextUtils

        text = "（2024）京0101民初1234号案件通知"
        result = TextUtils.extract_case_numbers(text)
        assert isinstance(result, list)

    def test_extract_case_numbers_no_match(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.extract_case_numbers("这是一条普通短信")
        assert isinstance(result, list)
