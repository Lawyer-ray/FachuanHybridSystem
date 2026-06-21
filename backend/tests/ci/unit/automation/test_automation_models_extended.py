"""automation app 补充 Model 单元测试

覆盖 InsuranceQuote, PreservationQuote, GsxtReportTask, ScraperTask,
CourtSMS, CourtDocument, InvoiceRecognitionTask, InvoiceRecord,
CourtToken, TokenAcquisitionHistory, CasePreservationQuoteBinding。
"""

import pytest
from django.utils import timezone
from datetime import timedelta

from apps.automation.models.court_document import CourtDocument, DocumentDownloadStatus
from apps.automation.models.court_sms import CourtSMS, CourtSMSStatus, CourtSMSType
from apps.automation.models.gsxt_report import GsxtReportStatus, GsxtReportTask
from apps.automation.models.invoice_recognition import (
    InvoiceCategory,
    InvoiceRecognitionTask,
    InvoiceRecognitionTaskStatus,
    InvoiceRecord,
    InvoiceRecordStatus,
)
from apps.automation.models.preservation import (
    CasePreservationQuoteBinding,
    InsuranceQuote,
    PreservationQuote,
    QuoteItemStatus,
    QuoteStatus,
)
from apps.automation.models.scraper import ScraperTask, ScraperTaskStatus, ScraperTaskType
from apps.automation.models.token import CourtToken, TokenAcquisitionHistory, TokenAcquisitionStatus
from apps.testing.factories import CaseFactory, ClientFactory, LawyerFactory


# ============================================================
# PreservationQuote
# ============================================================


@pytest.mark.django_db
class TestPreservationQuote:
    def test_str(self):
        pq = PreservationQuote.objects.create(
            preserve_amount=100000,
            status=QuoteStatus.PENDING,
        )
        assert "询价任务" in str(pq)
        assert "100000" in str(pq)

    def test_get_success_rate_zero_companies(self):
        pq = PreservationQuote(total_companies=0, success_count=0)
        assert pq.get_success_rate() == 0.0

    def test_get_success_rate_partial(self):
        pq = PreservationQuote(total_companies=10, success_count=7)
        assert pq.get_success_rate() == 70.0

    def test_get_success_rate_all_success(self):
        pq = PreservationQuote(total_companies=5, success_count=5)
        assert pq.get_success_rate() == 100.0


# ============================================================
# InsuranceQuote
# ============================================================


@pytest.mark.django_db
class TestInsuranceQuote:
    def test_str_with_min_amount(self):
        pq = PreservationQuote.objects.create(preserve_amount=50000)
        iq = InsuranceQuote.objects.create(
            preservation_quote=pq,
            company_id="c1",
            company_code="CC1",
            company_name="平安保险",
            min_amount=500.00,
            status=QuoteItemStatus.SUCCESS,
        )
        assert "平安保险" in str(iq)
        assert "500" in str(iq)

    def test_str_without_min_amount(self):
        pq = PreservationQuote.objects.create(preserve_amount=50000)
        iq = InsuranceQuote.objects.create(
            preservation_quote=pq,
            company_id="c2",
            company_code="CC2",
            company_name="人保保险",
            status=QuoteItemStatus.FAILED,
        )
        assert "人保保险" in str(iq)
        assert "失败" in str(iq)


# ============================================================
# CasePreservationQuoteBinding
# ============================================================


@pytest.mark.django_db
class TestCasePreservationQuoteBinding:
    def test_str(self):
        case = CaseFactory()
        pq = PreservationQuote.objects.create(preserve_amount=10000)
        binding = CasePreservationQuoteBinding.objects.create(
            case=case,
            preservation_quote=pq,
            preserve_amount_snapshot=10000,
        )
        result = str(binding)
        assert f"Case#{case.id}" in result
        assert f"Quote#{pq.id}" in result


# ============================================================
# GsxtReportTask
# ============================================================


@pytest.mark.django_db
class TestGsxtReportTask:
    def test_str(self):
        client = ClientFactory()
        task = GsxtReportTask.objects.create(
            client=client,
            company_name="测试公司",
            status=GsxtReportStatus.PENDING,
        )
        assert str(task) == ""

    def test_status_choices(self):
        assert GsxtReportStatus.PENDING.value == "pending"
        assert GsxtReportStatus.SUCCESS.value == "success"
        assert GsxtReportStatus.FAILED.value == "failed"
        assert GsxtReportStatus.WAITING_CAPTCHA.value == "waiting_captcha"


# ============================================================
# ScraperTask
# ============================================================


@pytest.mark.django_db
class TestScraperTask:
    def test_str(self):
        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            status=ScraperTaskStatus.PENDING,
            url="https://example.com",
        )
        result = str(task)
        assert "下载司法文书" in result
        assert "等待中" in result

    def test_can_retry_true(self):
        task = ScraperTask(retry_count=1, max_retries=3)
        assert task.can_retry() is True

    def test_can_retry_false(self):
        task = ScraperTask(retry_count=3, max_retries=3)
        assert task.can_retry() is False

    def test_should_execute_now_no_schedule(self):
        task = ScraperTask(scheduled_at=None)
        assert task.should_execute_now() is True

    def test_should_execute_now_past_schedule(self):
        task = ScraperTask(scheduled_at=timezone.now() - timedelta(hours=1))
        assert task.should_execute_now() is True

    def test_should_execute_now_future_schedule(self):
        task = ScraperTask(scheduled_at=timezone.now() + timedelta(hours=1))
        assert task.should_execute_now() is False


# ============================================================
# CourtSMS
# ============================================================


@pytest.mark.django_db
class TestCourtSMS:
    def test_str(self):
        sms = CourtSMS.objects.create(
            content="测试短信",
            received_at=timezone.now(),
            sms_type=CourtSMSType.DOCUMENT_DELIVERY,
            status=CourtSMSStatus.PENDING,
        )
        result = str(sms)
        assert "短信" in result
        assert "文书送达" in result
        assert "待处理" in result

    def test_str_no_sms_type(self):
        sms = CourtSMS.objects.create(
            content="测试",
            received_at=timezone.now(),
            status=CourtSMSStatus.COMPLETED,
        )
        result = str(sms)
        assert "未分类" in result

    def test_status_choices(self):
        assert CourtSMSStatus.PENDING.value == "pending"
        assert CourtSMSStatus.COMPLETED.value == "completed"
        assert CourtSMSStatus.FAILED.value == "failed"


# ============================================================
# CourtDocument
# ============================================================


@pytest.mark.django_db
class TestCourtDocument:
    def test_str(self):
        scraper = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
        )
        doc = CourtDocument.objects.create(
            scraper_task=scraper,
            c_sdbh="SD001",
            c_stbh="ST001",
            wjlj="https://example.com/file.pdf",
            c_wsbh="WS001",
            c_wsmc="民事判决书",
            c_fybh="FY001",
            c_fymc="北京法院",
            c_wjgs="pdf",
            dt_cjsj=timezone.now(),
        )
        result = str(doc)
        assert "民事判决书" in result
        assert "待下载" in result

    def test_absolute_file_path_empty(self):
        doc = CourtDocument(local_file_path=None)
        assert doc.absolute_file_path == ""

    def test_absolute_file_path_absolute(self):
        doc = CourtDocument(local_file_path="/tmp/doc.pdf")
        assert doc.absolute_file_path == "/tmp/doc.pdf"

    def test_absolute_file_path_relative(self):
        doc = CourtDocument(local_file_path="media/doc.pdf")
        path = doc.absolute_file_path
        assert path.endswith("media/doc.pdf") or path.endswith("doc.pdf")

    def test_unique_together_constraint(self):
        """c_wsbh + c_sdbh 应唯一"""
        scraper = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
        )
        now = timezone.now()
        CourtDocument.objects.create(
            scraper_task=scraper,
            c_sdbh="SD100",
            c_stbh="ST100",
            wjlj="https://example.com/a.pdf",
            c_wsbh="WS100",
            c_wsmc="文书A",
            c_fybh="FY100",
            c_fymc="法院A",
            c_wjgs="pdf",
            dt_cjsj=now,
        )
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            CourtDocument.objects.create(
                scraper_task=scraper,
                c_sdbh="SD100",
                c_stbh="ST200",
                wjlj="https://example.com/b.pdf",
                c_wsbh="WS100",
                c_wsmc="文书B",
                c_fybh="FY100",
                c_fymc="法院A",
                c_wjgs="pdf",
                dt_cjsj=now,
            )


# ============================================================
# InvoiceRecognitionTask & InvoiceRecord
# ============================================================


@pytest.mark.django_db
class TestInvoiceRecognitionTask:
    def test_str(self):
        task = InvoiceRecognitionTask.objects.create(
            name="发票识别任务1",
            status=InvoiceRecognitionTaskStatus.PENDING,
        )
        result = str(task)
        assert "发票识别任务1" in result
        assert "待处理" in result

    def test_status_choices(self):
        assert InvoiceRecognitionTaskStatus.PENDING.value == "pending"
        assert InvoiceRecognitionTaskStatus.COMPLETED.value == "completed"


@pytest.mark.django_db
class TestInvoiceRecord:
    def test_str(self):
        task = InvoiceRecognitionTask.objects.create(name="任务")
        record = InvoiceRecord.objects.create(
            task=task,
            file_path="/tmp/invoice.pdf",
            original_filename="发票001.pdf",
            status=InvoiceRecordStatus.PENDING,
        )
        result = str(record)
        assert "发票001.pdf" in result

    def test_category_choices(self):
        assert InvoiceCategory.VAT_SPECIAL.value == "vat_special"
        assert InvoiceCategory.OTHER.value == "other"

    def test_record_status_choices(self):
        assert InvoiceRecordStatus.PENDING.value == "pending"
        assert InvoiceRecordStatus.SUCCESS.value == "success"
        assert InvoiceRecordStatus.FAILED.value == "failed"


# ============================================================
# CourtToken
# ============================================================


@pytest.mark.django_db
class TestCourtToken:
    def test_str(self):
        token = CourtToken.objects.create(
            site_name="court_zxfw",
            account="test_user",
            token="abc123",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert str(token) == "court_zxfw - test_user"

    def test_is_expired_false(self):
        token = CourtToken(expires_at=timezone.now() + timedelta(hours=1))
        assert token.is_expired() is False

    def test_is_expired_true(self):
        token = CourtToken(expires_at=timezone.now() - timedelta(hours=1))
        assert token.is_expired() is True

    def test_unique_together(self):
        now = timezone.now() + timedelta(hours=1)
        CourtToken.objects.create(
            site_name="s1", account="a1", token="t1", expires_at=now
        )
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            CourtToken.objects.create(
                site_name="s1", account="a1", token="t2", expires_at=now
            )


# ============================================================
# TokenAcquisitionHistory
# ============================================================


@pytest.mark.django_db
class TestTokenAcquisitionHistory:
    def test_str(self):
        h = TokenAcquisitionHistory.objects.create(
            site_name="court_zxfw",
            account="user1",
            status=TokenAcquisitionStatus.SUCCESS,
            trigger_reason="token_expired",
        )
        result = str(h)
        assert "court_zxfw" in result
        assert "user1" in result
        assert "成功" in result

    def test_get_success_rate_display_success(self):
        h = TokenAcquisitionHistory(status=TokenAcquisitionStatus.SUCCESS)
        assert h.get_success_rate_display() == "100%"

    def test_get_success_rate_display_failed(self):
        h = TokenAcquisitionHistory(status=TokenAcquisitionStatus.FAILED)
        assert h.get_success_rate_display() == "0%"

    def test_status_choices(self):
        assert TokenAcquisitionStatus.SUCCESS.value == "success"
        assert TokenAcquisitionStatus.FAILED.value == "failed"
        assert TokenAcquisitionStatus.TIMEOUT.value == "timeout"
        assert TokenAcquisitionStatus.CREDENTIAL_ERROR.value == "credential_error"
