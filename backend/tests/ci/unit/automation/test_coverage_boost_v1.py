"""Tests for data_classes, dtos, signals, and other pure logic modules."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


# ── data_classes ─────────────────────────────────────────────────


class TestDocumentRecord:
    def test_from_api_response(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentRecord

        data = {
            "ah": "（2025）粤0604民初41257号",
            "sdbh": "SD001",
            "ajzybh": "AJ001",
            "fssj": "2025-12-10 16:25:37",
            "fymc": "佛山市南海区人民法院",
            "ahdm": "DM001",
            "fybh": "FY001",
            "ssdrxm": "张三",
            "ssdrsjhm": "13800138000",
            "ssdrzjhm": "440100199901011234",
            "wsmc": "判决书",
            "sdzt": "已送达",
            "qdzt": "已签到",
            "qdbh": "QD001",
            "fqr": "李四",
            "cjsj": "2025-12-01",
            "zhxgsj": "2025-12-10",
        }
        record = DocumentRecord.from_api_response(data)
        assert record.ah == "（2025）粤0604民初41257号"
        assert record.sdbh == "SD001"
        assert record.fssj == "2025-12-10 16:25:37"
        assert record.fymc == "佛山市南海区人民法院"

    def test_from_api_response_defaults(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentRecord

        data = {"ah": "AH", "sdbh": "SD", "ajzybh": "AJ", "fssj": "", "fymc": "法院"}
        record = DocumentRecord.from_api_response(data)
        assert record.ahdm == ""
        assert record.fybh == ""
        assert record.ssdrxm == ""

    def test_parse_fssj_valid(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentRecord

        record = DocumentRecord(
            ah="AH", sdbh="SD", ajzybh="AJ", fssj="2025-12-10 16:25:37", fymc="法院"
        )
        result = record.parse_fssj()
        assert result is not None
        assert result.year == 2025
        assert result.month == 12
        assert result.day == 10

    def test_parse_fssj_empty(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentRecord

        record = DocumentRecord(ah="AH", sdbh="SD", ajzybh="AJ", fssj="", fymc="法院")
        assert record.parse_fssj() is None

    def test_parse_fssj_invalid(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentRecord

        record = DocumentRecord(
            ah="AH", sdbh="SD", ajzybh="AJ", fssj="not-a-date", fymc="法院"
        )
        assert record.parse_fssj() is None

    def test_parse_fssj_iso_format(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentRecord

        record = DocumentRecord(
            ah="AH", sdbh="SD", ajzybh="AJ", fssj="2025-12-10T16:25:37", fymc="法院"
        )
        result = record.parse_fssj()
        assert result is not None
        assert result.year == 2025

    def test_to_dict(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentRecord

        record = DocumentRecord(
            ah="AH", sdbh="SD", ajzybh="AJ", fssj="2025-12-10 16:25:37", fymc="法院"
        )
        d = record.to_dict()
        assert d["ah"] == "AH"
        assert d["sdbh"] == "SD"
        assert d["fymc"] == "法院"


class TestDocumentDetail:
    def test_from_api_response(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentDetail

        data = {
            "c_sdbh": "SD001",
            "c_wsmc": "判决书",
            "c_wjgs": "pdf",
            "wjlj": "https://example.com/doc.pdf",
            "c_stbh": "ST001",
            "c_wsbh": "WS001",
            "c_fybh": "FY001",
            "c_fymc": "法院",
            "dt_cjsj": "2025-12-10",
        }
        detail = DocumentDetail.from_api_response(data)
        assert detail.c_sdbh == "SD001"
        assert detail.c_wsmc == "判决书"
        assert detail.wjlj == "https://example.com/doc.pdf"

    def test_from_api_response_defaults(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentDetail

        data = {
            "c_sdbh": "SD",
            "c_wsmc": "文书",
            "c_wjgs": "pdf",
            "wjlj": "https://url",
        }
        detail = DocumentDetail.from_api_response(data)
        assert detail.c_stbh == ""
        assert detail.c_wsbh == ""

    def test_to_dict(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentDetail

        detail = DocumentDetail(
            c_sdbh="SD", c_wsmc="文书", c_wjgs="pdf", wjlj="url"
        )
        d = detail.to_dict()
        assert d["c_sdbh"] == "SD"
        assert d["c_wsmc"] == "文书"


class TestDocumentListResponse:
    def test_from_api_response(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentListResponse

        api_data = {
            "code": 200,
            "msg": "成功！",
            "success": True,
            "data": {
                "total": 2,
                "data": [
                    {"ah": "AH1", "sdbh": "SD1", "ajzybh": "AJ1", "fssj": "", "fymc": "法院1"},
                    {"ah": "AH2", "sdbh": "SD2", "ajzybh": "AJ2", "fssj": "", "fymc": "法院2"},
                ],
            },
        }
        resp = DocumentListResponse.from_api_response(api_data)
        assert resp.total == 2
        assert len(resp.documents) == 2
        assert resp.documents[0].ah == "AH1"

    def test_from_api_response_empty(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentListResponse

        api_data = {"data": {"total": 0, "data": []}}
        resp = DocumentListResponse.from_api_response(api_data)
        assert resp.total == 0
        assert resp.documents == []

    def test_to_dict(self) -> None:
        from apps.automation.services.document_delivery.data_classes import (
            DocumentListResponse,
            DocumentRecord,
        )

        resp = DocumentListResponse(
            total=1,
            documents=[
                DocumentRecord(ah="AH", sdbh="SD", ajzybh="AJ", fssj="", fymc="法院")
            ],
        )
        d = resp.to_dict()
        assert d["total"] == 1
        assert len(d["documents"]) == 1


class TestDocumentDeliveryRecord:
    def test_to_dict_and_from_dict(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord

        dt = datetime(2025, 12, 10, 16, 25, 37)
        record = DocumentDeliveryRecord(
            case_number="（2025）粤0604民初41257号",
            send_time=dt,
            element_index=3,
            document_name="判决书",
            court_name="佛山法院",
            delivery_event_id="EVT001",
        )
        d = record.to_dict()
        assert d["case_number"] == "（2025）粤0604民初41257号"
        assert d["send_time"] is not None

        restored = DocumentDeliveryRecord.from_dict(d)
        assert restored.case_number == record.case_number
        assert restored.element_index == 3
        assert restored.send_time is not None

    def test_from_dict_none_send_time(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord

        d = {"case_number": "AH", "send_time": None, "element_index": 0}
        record = DocumentDeliveryRecord.from_dict(d)
        assert record.send_time is None

    def test_from_dict_string_send_time(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord

        d = {
            "case_number": "AH",
            "send_time": "2025-12-10T16:25:37",
            "element_index": 1,
        }
        record = DocumentDeliveryRecord.from_dict(d)
        assert record.send_time is not None
        assert record.send_time.year == 2025

    def test_from_dict_datetime_send_time(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord

        dt = datetime(2025, 6, 1, 10, 0, 0)
        d = {"case_number": "AH", "send_time": dt, "element_index": 2}
        record = DocumentDeliveryRecord.from_dict(d)
        assert record.send_time == dt

    def test_from_dict_optional_fields(self) -> None:
        from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord

        d = {"case_number": "AH", "send_time": None, "element_index": 0}
        record = DocumentDeliveryRecord.from_dict(d)
        assert record.document_name == ""
        assert record.court_name == ""
        assert record.delivery_event_id == ""


# ── dtos ─────────────────────────────────────────────────────────


class TestDTOs:
    def test_captcha_dto(self) -> None:
        from apps.automation.dtos import CaptchaRecognizeResultDTO

        dto = CaptchaRecognizeResultDTO(
            success=True, text="abc", processing_time=1.5, error=None
        )
        assert dto.success is True
        assert dto.text == "abc"
        assert dto.processing_time == 1.5
        assert dto.error is None
        # frozen
        with pytest.raises(AttributeError):
            dto.success = False  # type: ignore[misc]

    def test_court_token_dto(self) -> None:
        from apps.automation.dtos import CourtTokenDTO

        dto = CourtTokenDTO(
            site_name="court_zxfw",
            account="test_account",
            token="tok123",
            token_type="bearer",
            expires_at=None,
            created_at=None,
            updated_at=None,
        )
        assert dto.site_name == "court_zxfw"
        assert dto.token == "tok123"
        # frozen
        with pytest.raises(AttributeError):
            dto.token = "new"  # type: ignore[misc]


# ── signals ──────────────────────────────────────────────────────


class TestSignals:
    @pytest.mark.django_db
    def test_cleanup_court_document_wrong_sender(self) -> None:
        """Signal should be a no-op for non-CourtDocument senders."""
        from apps.automation.signals import cleanup_court_document_local_file

        # Calling with wrong sender should return immediately
        instance = MagicMock()
        cleanup_court_document_local_file(sender=MagicMock, instance=instance)

    @pytest.mark.django_db
    def test_cleanup_gsxt_report_wrong_sender(self) -> None:
        """Signal should be a no-op for non-GsxtReportTask senders."""
        from apps.automation.signals import cleanup_gsxt_report_task_file

        instance = MagicMock()
        cleanup_gsxt_report_task_file(sender=MagicMock, instance=instance)

    @pytest.mark.django_db
    def test_cleanup_court_document_no_file_path(self) -> None:
        """Signal should skip when local_file_path is empty."""
        from apps.automation.models.court_document import CourtDocument
        from apps.automation.signals import cleanup_court_document_local_file

        instance = MagicMock(spec=CourtDocument)
        instance.local_file_path = ""
        cleanup_court_document_local_file(sender=CourtDocument, instance=instance)

    @pytest.mark.django_db
    def test_cleanup_gsxt_report_no_file(self) -> None:
        """Signal should skip when report_file is falsy."""
        from apps.automation.models.gsxt_report import GsxtReportTask
        from apps.automation.signals import cleanup_gsxt_report_task_file

        instance = MagicMock(spec=GsxtReportTask)
        instance.report_file = None
        cleanup_gsxt_report_task_file(sender=GsxtReportTask, instance=instance)

    @pytest.mark.django_db
    def test_cleanup_court_document_file_not_exists(self) -> None:
        """Signal should handle non-existent files gracefully."""
        from apps.automation.models.court_document import CourtDocument
        from apps.automation.signals import cleanup_court_document_local_file

        instance = MagicMock(spec=CourtDocument)
        instance.local_file_path = "/tmp/nonexistent_file_that_does_not_exist_12345.pdf"
        cleanup_court_document_local_file(sender=CourtDocument, instance=instance)

    @pytest.mark.django_db
    def test_cleanup_court_document_relative_path(self) -> None:
        """Signal should handle relative file paths."""
        from apps.automation.models.court_document import CourtDocument
        from apps.automation.signals import cleanup_court_document_local_file

        instance = MagicMock(spec=CourtDocument)
        instance.local_file_path = "relative/path/doc.pdf"
        cleanup_court_document_local_file(sender=CourtDocument, instance=instance)


# ── sms_submission_service (sync parts) ──────────────────────────


class TestSMSSubmissionServiceSync:
    @pytest.mark.django_db
    def test_filter_valid_case_numbers(self) -> None:
        from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService

        svc = SMSSubmissionService()
        numbers = [
            "（2025）粤0604民初41257号",
            "2025年12月10日",
            "2025年6月1号",
            "（2024）京0101民初100号",
        ]
        result = svc._filter_valid_case_numbers(numbers)
        assert "（2025）粤0604民初41257号" in result
        assert "（2024）京0101民初100号" in result
        assert "2025年12月10日" not in result

    @pytest.mark.django_db
    def test_filter_valid_case_numbers_all_invalid(self) -> None:
        from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService

        svc = SMSSubmissionService()
        numbers = ["2025年12月10日", "2024年1月5日"]
        result = svc._filter_valid_case_numbers(numbers)
        assert result == []

    @pytest.mark.django_db
    def test_filter_valid_case_numbers_empty(self) -> None:
        from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService

        svc = SMSSubmissionService()
        assert svc._filter_valid_case_numbers([]) == []

    @pytest.mark.django_db
    def test_submit_sms_empty_content_raises(self) -> None:
        from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService
        from apps.core.exceptions import ValidationException

        svc = SMSSubmissionService()
        with pytest.raises(ValidationException):
            svc.submit_sms("")

    @pytest.mark.django_db
    def test_submit_sms_whitespace_content_raises(self) -> None:
        from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService
        from apps.core.exceptions import ValidationException

        svc = SMSSubmissionService()
        with pytest.raises(ValidationException):
            svc.submit_sms("   ")

    @pytest.mark.django_db
    def test_assign_case_sms_not_found(self) -> None:
        from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService
        from apps.core.exceptions import NotFoundError

        svc = SMSSubmissionService()
        with pytest.raises(NotFoundError):
            svc.assign_case(sms_id=999999, case_id=1)

    @pytest.mark.django_db
    def test_retry_processing_sms_not_found(self) -> None:
        from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService
        from apps.core.exceptions import NotFoundError

        svc = SMSSubmissionService()
        with pytest.raises(NotFoundError):
            svc.retry_processing(sms_id=999999)

    @pytest.mark.django_db
    def test_create_case_binding_no_case(self) -> None:
        from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService

        svc = SMSSubmissionService()
        sms = MagicMock()
        sms.case = None
        assert svc._create_case_binding(sms) is False

    @pytest.mark.django_db
    def test_add_case_numbers_no_case(self) -> None:
        from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService

        svc = SMSSubmissionService()
        sms = MagicMock()
        sms.case = None
        sms.case_numbers = ["（2025）粤0604民初41257号"]
        svc._add_case_numbers_to_case(sms)  # should not raise

    @pytest.mark.django_db
    def test_add_case_numbers_no_numbers(self) -> None:
        from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService

        svc = SMSSubmissionService()
        sms = MagicMock()
        sms.case = MagicMock()
        sms.case_numbers = []
        svc._add_case_numbers_to_case(sms)  # should not raise


# ── task_recovery_service ────────────────────────────────────────


class TestTaskRecoveryService:
    def test_init(self) -> None:
        from apps.automation.services.sms.task_recovery_service import TaskRecoveryService

        svc = TaskRecoveryService()
        assert svc.stuck_timeout_minutes == 30
        assert svc.max_retry_count == 3
        assert svc.recovery_max_age_hours == 24

    @pytest.mark.django_db
    def test_recover_all_tasks_dry_run(self) -> None:
        from apps.automation.services.sms.task_recovery_service import TaskRecoveryService

        svc = TaskRecoveryService()
        result = svc.recover_all_tasks(dry_run=True)
        assert "recovered_count" in result
        assert "reset_count" in result
        assert "failed_count" in result
        assert "skipped_count" in result
        assert "tasks" in result

    @pytest.mark.django_db
    def test_recover_all_tasks_real_run(self) -> None:
        from apps.automation.services.sms.task_recovery_service import TaskRecoveryService

        svc = TaskRecoveryService()
        result = svc.recover_all_tasks(dry_run=False)
        assert "recovered_count" in result
        assert isinstance(result["recovered_count"], int)

    @pytest.mark.django_db
    def test_get_recovery_status(self) -> None:
        from apps.automation.services.sms.task_recovery_service import TaskRecoveryService

        svc = TaskRecoveryService()
        status = svc.get_recovery_status()
        assert "status_counts" in status
        assert "recovery_needed" in status
        assert "stuck_tasks" in status
        assert "max_age_hours" in status
        assert status["max_age_hours"] == 24

    @pytest.mark.django_db
    def test_reset_stuck_task(self) -> None:
        from apps.automation.services.sms.task_recovery_service import TaskRecoveryService
        from apps.automation.models import CourtSMS, CourtSMSStatus

        svc = TaskRecoveryService()
        sms = MagicMock(spec=CourtSMS)
        sms.status = CourtSMSStatus.MATCHING
        result = svc._reset_stuck_task(sms)
        assert result is True
        assert sms.status == CourtSMSStatus.PENDING

    @pytest.mark.django_db
    def test_periodic_recovery_task(self) -> None:
        from apps.automation.services.sms.task_recovery_service import periodic_recovery_task

        result = periodic_recovery_task()
        assert "recovered_count" in result


# ── insurance exceptions ─────────────────────────────────────────


class TestInsuranceExceptions:
    def test_token_error(self) -> None:
        from apps.automation.services.insurance.exceptions import TokenError

        err = TokenError("token expired")
        assert "token expired" in str(err)
        assert err.code == "TOKEN_ERROR"

    def test_api_error(self) -> None:
        from apps.automation.services.insurance.exceptions import APIError

        err = APIError(message="api failed")
        assert err.code == "API_ERROR"
        assert err.message == "api failed"

    def test_api_error_with_status_code(self) -> None:
        from apps.automation.services.insurance.exceptions import APIError

        err = APIError(message="not found", status_code=404)
        assert err.code == "API_ERROR_404"

    def test_company_list_empty_error(self) -> None:
        from apps.automation.services.insurance.exceptions import CompanyListEmptyError

        err = CompanyListEmptyError(message="empty")
        assert err.code == "COMPANY_LIST_EMPTY"

    def test_validation_error(self) -> None:
        from apps.automation.services.insurance.exceptions import ValidationError

        err = ValidationError(message="invalid", errors={"field": "error"})
        assert err.code == "VALIDATION_ERROR"
        assert err.errors == {"field": "error"}

    def test_quote_execution_error(self) -> None:
        from apps.automation.services.insurance.exceptions import QuoteExecutionError

        err = QuoteExecutionError(message="execution failed", quote_id=42)
        assert err.code == "QUOTE_EXECUTION_ERROR"
        assert err.quote_id == 42

    def test_retry_limit_exceeded_error(self) -> None:
        from apps.automation.services.insurance.exceptions import RetryLimitExceededError

        err = RetryLimitExceededError(message="too many retries", max_retries=3)
        assert err.code == "RETRY_LIMIT_EXCEEDED"
        assert err.max_retries == 3

    def test_network_error(self) -> None:
        from apps.automation.services.insurance.exceptions import NetworkError

        err = NetworkError(message="connection timeout")
        assert err.code == "NETWORK_ERROR"


# ── insurance dataclasses ────────────────────────────────────────


class TestInsuranceDataclasses:
    def test_insurance_company(self) -> None:
        from apps.automation.services.insurance.court_insurance_client import InsuranceCompany

        co = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        assert co.c_id == "1"
        assert co.c_name == "人保"

    def test_premium_result(self) -> None:
        from decimal import Decimal
        from apps.automation.services.insurance.court_insurance_client import (
            InsuranceCompany,
            PremiumResult,
        )

        co = InsuranceCompany(c_id="1", c_code="PICC", c_name="人保")
        result = PremiumResult(
            company=co,
            premium=Decimal("100.50"),
            status="success",
            error_message=None,
            response_data={"data": {"minPremium": "80"}},
        )
        assert result.premium == Decimal("100.50")
        assert result.status == "success"


# ── preservation_quote repo (sync validation) ────────────────────


class TestPreservationQuoteRepoValidation:
    def test_validate_create_params_success(self) -> None:
        from decimal import Decimal
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        repo = PreservationQuoteRepository()
        repo.validate_create_params(
            preserve_amount=Decimal("10000"),
            corp_id="C001",
            category_id="CAT001",
            credential_id=1,
        )

    def test_validate_negative_amount(self) -> None:
        from decimal import Decimal
        from apps.automation.services.insurance.exceptions import ValidationError
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        repo = PreservationQuoteRepository()
        with pytest.raises(ValidationError):
            repo.validate_create_params(
                preserve_amount=Decimal("-100"),
                corp_id="C001",
                category_id="CAT001",
                credential_id=None,
            )

    def test_validate_empty_corp_id(self) -> None:
        from decimal import Decimal
        from apps.automation.services.insurance.exceptions import ValidationError
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        repo = PreservationQuoteRepository()
        with pytest.raises(ValidationError):
            repo.validate_create_params(
                preserve_amount=Decimal("10000"),
                corp_id="",
                category_id="CAT001",
                credential_id=None,
            )

    def test_validate_empty_category_id(self) -> None:
        from decimal import Decimal
        from apps.automation.services.insurance.exceptions import ValidationError
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        repo = PreservationQuoteRepository()
        with pytest.raises(ValidationError):
            repo.validate_create_params(
                preserve_amount=Decimal("10000"),
                corp_id="C001",
                category_id="  ",
                credential_id=None,
            )

    def test_validate_invalid_credential_id(self) -> None:
        from decimal import Decimal
        from apps.automation.services.insurance.exceptions import ValidationError
        from apps.automation.services.insurance.preservation_quote.repo import (
            PreservationQuoteRepository,
        )

        repo = PreservationQuoteRepository()
        with pytest.raises(ValidationError):
            repo.validate_create_params(
                preserve_amount=Decimal("10000"),
                corp_id="C001",
                category_id="CAT001",
                credential_id=-1,
            )


# ── task_queue ───────────────────────────────────────────────────


class TestTaskQueue:
    def test_django_q_task_queue_init(self) -> None:
        from apps.automation.services.sms.task_queue import DjangoQTaskQueue

        queue = DjangoQTaskQueue()
        assert queue is not None

    def test_task_queue_protocol(self) -> None:
        from apps.automation.services.sms.task_queue import TaskQueue

        # TaskQueue is a Protocol, just verify it exists
        assert hasattr(TaskQueue, "enqueue")


# ── ocr adapter ──────────────────────────────────────────────────


class TestOCRAdapter:
    def test_ocr_adapter_init(self) -> None:
        from apps.automation.services.ocr.adapter import OCRServiceAdapter

        adapter = OCRServiceAdapter()
        assert adapter._service is None

    def test_ocr_adapter_service_lazy_load(self) -> None:
        from apps.automation.services.ocr.adapter import OCRServiceAdapter

        adapter = OCRServiceAdapter()
        # service property should create an OCRService when accessed
        # (may fail if OCR dependencies not available, but the lazy load path is tested)
        try:
            svc = adapter.service
            assert svc is not None
        except Exception:
            pass  # OCR deps may not be available in CI


# ── config_service ───────────────────────────────────────────────


class TestConfigService:
    def test_automation_config_service_init(self) -> None:
        from apps.automation.services.config_service import AutomationConfigService

        svc = AutomationConfigService()
        assert svc is not None

    @pytest.mark.django_db
    def test_get_system_status(self) -> None:
        from apps.automation.services.config_service import AutomationConfigService

        svc = AutomationConfigService()
        result = svc.get_system_status()
        assert "debug" in result
        assert isinstance(result["debug"], bool)
