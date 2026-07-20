"""Tests for automation schema validation."""

from __future__ import annotations

import base64
from datetime import datetime

import pytest

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)

from pydantic import ValidationError

# ======================================================================
# court_filing_schemas
# ======================================================================

class TestCaseFilingInfoOut:
    def test_valid_data(self):
        from plugins.court_automation.filing.schemas import CaseFilingInfoOut
        data = CaseFilingInfoOut(
            case_id=1, case_name="测试", cause_of_action="借款",
            court_name="天河区人民法院", target_amount="10000",
            plaintiff_name="原告", defendant_name="被告",
        )
        assert data.case_id == 1
        assert data.plugin_available is True

    def test_defaults(self):
        from plugins.court_automation.filing.schemas import CaseFilingInfoOut
        data = CaseFilingInfoOut(case_id=1, case_name="测试", cause_of_action="", court_name=None, target_amount=None, plaintiff_name=None, defendant_name=None)
        assert data.our_party_is_plaintiff_side is False
        assert data.has_court_credential is False
        assert data.has_http_plugin is False


class TestExecuteCourtFilingIn:
    def test_required_case_id(self):
        from plugins.court_automation.filing.schemas import ExecuteCourtFilingIn
        data = ExecuteCourtFilingIn(case_id=42)
        assert data.case_id == 42
        assert data.filing_type is None

    def test_with_optional(self):
        from plugins.court_automation.filing.schemas import ExecuteCourtFilingIn
        data = ExecuteCourtFilingIn(case_id=1, filing_type="civil", filing_engine="api")
        assert data.filing_type == "civil"


class TestExecuteCourtFilingOut:
    def test_success(self):
        from plugins.court_automation.filing.schemas import ExecuteCourtFilingOut
        data = ExecuteCourtFilingOut(success=True, message="ok", session_id=1, status="completed")
        assert data.success is True

    def test_timing(self):
        from plugins.court_automation.filing.schemas import ExecuteCourtFilingOut
        data = ExecuteCourtFilingOut(
            success=True, message="ok", timing={"overall_start": 1.0}
        )
        assert data.timing["overall_start"] == 1.0


# ======================================================================
# court_guarantee_schemas
# ======================================================================

class TestCaseGuaranteeInfoOut:
    def test_valid(self):
        from plugins.court_automation.guarantee.schemas import CaseGuaranteeInfoOut
        data = CaseGuaranteeInfoOut(case_id=1, case_name="测试", court_name=None, cause_of_action="", preserve_amount=None, preserve_category="诉讼保全", has_case_number=False)
        assert data.case_id == 1
        assert data.plugin_available is True

    def test_defaults(self):
        from plugins.court_automation.guarantee.schemas import CaseGuaranteeInfoOut
        data = CaseGuaranteeInfoOut(case_id=1, case_name="测试", court_name=None, cause_of_action="", preserve_amount=None, preserve_category="诉前保全", has_case_number=False)
        assert data.has_court_credential is False
        assert data.our_party_is_plaintiff_side is False


class TestExecuteCourtGuaranteeIn:
    def test_defaults(self):
        from plugins.court_automation.guarantee.schemas import ExecuteCourtGuaranteeIn
        data = ExecuteCourtGuaranteeIn(case_id=1)
        assert data.insurance_company_name is None
        assert data.selected_respondent_ids is None


class TestCaseQuoteOperationIn:
    def test_required(self):
        from plugins.court_automation.guarantee.schemas import CaseQuoteOperationIn
        data = CaseQuoteOperationIn(case_id=10)
        assert data.case_id == 10


# ======================================================================
# captcha schemas
# ======================================================================

class TestCaptchaRecognizeIn:
    def test_valid_base64(self):
        from apps.automation.schemas.captcha import CaptchaRecognizeIn
        img = base64.b64encode(b"test_image").decode()
        data = CaptchaRecognizeIn(image_base64=img)
        assert data.image_base64 == img

    def test_strips_data_url_prefix(self):
        from apps.automation.schemas.captcha import CaptchaRecognizeIn
        img = base64.b64encode(b"test").decode()
        data = CaptchaRecognizeIn(image_base64=f"data:image/png;base64,{img}")
        assert data.image_base64 == img

    def test_empty_raises(self):
        from apps.automation.schemas.captcha import CaptchaRecognizeIn
        with pytest.raises(ValidationError):
            CaptchaRecognizeIn(image_base64="")

    def test_invalid_base64_raises(self):
        from apps.automation.schemas.captcha import CaptchaRecognizeIn
        with pytest.raises(ValidationError):
            CaptchaRecognizeIn(image_base64="not-valid-base64!!!")


class TestCaptchaRecognizeOut:
    def test_success(self):
        from apps.automation.schemas.captcha import CaptchaRecognizeOut
        data = CaptchaRecognizeOut(success=True, text="AB12", processing_time=0.5)
        assert data.text == "AB12"

    def test_failure(self):
        from apps.automation.schemas.captcha import CaptchaRecognizeOut
        data = CaptchaRecognizeOut(success=False, error="识别失败")
        assert data.text is None


# ======================================================================
# court_sms schemas
# ======================================================================

class TestCourtSMSSubmitIn:
    def test_valid(self):
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn
        data = CourtSMSSubmitIn(content="测试短信")
        assert data.content == "测试短信"

    def test_strips_whitespace(self):
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn
        data = CourtSMSSubmitIn(content="  短信内容  ")
        assert data.content == "短信内容"

    def test_empty_raises(self):
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn
        with pytest.raises(ValidationError):
            CourtSMSSubmitIn(content="")

    def test_whitespace_only_raises(self):
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn
        with pytest.raises(ValidationError):
            CourtSMSSubmitIn(content="   ")


class TestCourtSMSBatchDeleteIn:
    def test_valid(self):
        from apps.automation.schemas.court_sms import CourtSMSBatchDeleteIn
        data = CourtSMSBatchDeleteIn(ids=[1, 2, 3])
        assert len(data.ids) == 3

    def test_empty_raises(self):
        from apps.automation.schemas.court_sms import CourtSMSBatchDeleteIn
        with pytest.raises(ValidationError):
            CourtSMSBatchDeleteIn(ids=[])


class TestCourtSMSAssignCaseIn:
    def test_valid(self):
        from apps.automation.schemas.court_sms import CourtSMSAssignCaseIn
        data = CourtSMSAssignCaseIn(case_id=42)
        assert data.case_id == 42

    def test_zero_raises(self):
        from apps.automation.schemas.court_sms import CourtSMSAssignCaseIn
        with pytest.raises(ValidationError):
            CourtSMSAssignCaseIn(case_id=0)


class TestSMSParseResult:
    def test_dataclass(self):
        from apps.automation.schemas.court_sms import SMSParseResult
        result = SMSParseResult(
            sms_type="送达",
            download_links=["http://example.com/doc.pdf"],
            case_numbers=["(2025)粤01民初1号"],
            party_names=["张三"],
            has_valid_download_link=True,
        )
        assert result.sms_type == "送达"
        assert len(result.download_links) == 1


class TestCourtSMSSubmitOut:
    def test_valid(self):
        from apps.automation.schemas.court_sms import CourtSMSSubmitOut
        data = CourtSMSSubmitOut(success=True, data={"id": 1})
        assert data.success is True


class TestCourtSMSBatchDeleteOut:
    def test_valid(self):
        from apps.automation.schemas.court_sms import CourtSMSBatchDeleteOut
        data = CourtSMSBatchDeleteOut(deleted=5)
        assert data.deleted == 5


class TestCourtSMSAssignCaseOut:
    def test_valid(self):
        from apps.automation.schemas.court_sms import CourtSMSAssignCaseOut
        data = CourtSMSAssignCaseOut(success=True, data={"id": 1})
        assert data.success is True


# ======================================================================
# document schemas
# ======================================================================

class TestDocumentProcessIn:
    def test_required_fields(self):
        from apps.automation.schemas.document import DocumentProcessIn
        data = DocumentProcessIn(file_path="/tmp/test.pdf", kind="pdf")
        assert data.file_path == "/tmp/test.pdf"
        assert data.limit is None

    def test_with_optional(self):
        from apps.automation.schemas.document import DocumentProcessIn
        data = DocumentProcessIn(file_path="/tmp/test.pdf", kind="pdf", limit=100, preview_page=1)
        assert data.limit == 100


class TestDocumentProcessOut:
    def test_empty(self):
        from apps.automation.schemas.document import DocumentProcessOut
        data = DocumentProcessOut()
        assert data.image_url is None


class TestOllamaChatIn:
    def test_required(self):
        from apps.automation.schemas.document import OllamaChatIn
        data = OllamaChatIn(model="qwen", prompt="test", text="hello")
        assert data.model == "qwen"


class TestAutoToolProcessIn:
    def test_defaults(self):
        from apps.automation.schemas.document import AutoToolProcessIn
        data = AutoToolProcessIn(file_path="/tmp/test.pdf")
        assert data.model == "qwen3:0.6b"
        assert data.limit is None


class TestAsyncTaskSubmitOut:
    def test_valid(self):
        from apps.automation.schemas.document import AsyncTaskSubmitOut
        data = AsyncTaskSubmitOut(task_id="abc", status="pending", message="ok")
        assert data.task_id == "abc"


class TestAsyncTaskStatusOut:
    def test_valid(self):
        from apps.automation.schemas.document import AsyncTaskStatusOut
        data = AsyncTaskStatusOut(task_id="abc", status="done", result={"key": "val"})
        assert data.result == {"key": "val"}


# ======================================================================
# performance schemas
# ======================================================================

class TestPerformanceMetricsOut:
    def test_valid(self):
        from apps.automation.schemas.performance import PerformanceMetricsOut
        data = PerformanceMetricsOut(
            total_acquisitions=100, successful_acquisitions=90, failed_acquisitions=10,
            success_rate=90.0, avg_duration=1.5, avg_login_duration=0.5,
            timeout_count=2, network_error_count=3, captcha_error_count=1,
            credential_error_count=0, concurrent_acquisitions=5, cache_hit_rate=85.0,
        )
        assert data.success_rate == 90.0


class TestAlertSchema:
    def test_valid(self):
        from apps.automation.schemas.performance import AlertSchema
        data = AlertSchema(type="timeout", message="超时告警", severity="high")
        assert data.severity == "high"


class TestHealthCheckOut:
    def test_valid(self):
        from apps.automation.schemas.performance import HealthCheckOut
        data = HealthCheckOut(
            status="healthy", timestamp="2026-01-01T00:00:00",
            metrics={}, alerts=[], thresholds={},
        )
        assert data.status == "healthy"


# ======================================================================
# court_document schema
# ======================================================================

class TestAPIInterceptResponseSchema:
    def test_valid(self):
        from apps.automation.schemas.court_document import APIInterceptResponseSchema
        data = APIInterceptResponseSchema(
            code=200, msg="ok", data=[
                {
                    "c_sdbh": "SD001",
                    "c_stbh": "ST001",
                    "wjlj": "http://example.com/doc.pdf",
                    "c_wsbh": "WS001",
                    "c_wsmc": "判决书",
                    "c_fybh": "FY001",
                    "c_fymc": "天河法院",
                    "c_wjgs": "pdf",
                    "dt_cjsj": "2025-01-01",
                }
            ], success=True, totalRows=1,
        )
        assert data.totalRows == 1

    def test_validator_runs(self):
        from apps.automation.schemas.court_document import APIInterceptResponseSchema

        # Empty data should pass (validator doesn't reject)
        data = APIInterceptResponseSchema(code=200, msg="ok", data=[], success=True, totalRows=0)
        assert data.data == []


class TestCourtDocumentSchema:
    def test_with_all_fields(self):
        from apps.automation.schemas.court_document import CourtDocumentSchema
        now = datetime.now()
        data = CourtDocumentSchema(
            id=1, scraper_task_id=10, case_id=5,
            c_sdbh="SD001", c_stbh="ST001", wjlj="http://example.com",
            c_wsbh="WS001", c_wsmc="判决书", c_fybh="FY001", c_fymc="天河法院",
            c_wjgs="pdf", dt_cjsj=now,
            download_status="success", created_at=now, updated_at=now,
        )
        assert data.c_wsmc == "判决书"
        assert data.case_id == 5

    def test_optional_fields_none(self):
        from apps.automation.schemas.court_document import CourtDocumentSchema
        now = datetime.now()
        data = CourtDocumentSchema(
            id=1, scraper_task_id=10,
            c_sdbh="SD001", c_stbh="ST001", wjlj="http://example.com",
            c_wsbh="WS001", c_wsmc="文书", c_fybh="FY001", c_fymc="法院",
            c_wjgs="pdf", dt_cjsj=now,
            download_status="pending", created_at=now, updated_at=now,
        )
        assert data.case_id is None
        assert data.local_file_path is None
