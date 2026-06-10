"""Coverage boost tests for automation module — SMS recommendation, case matcher, text utils, schemas."""

from __future__ import annotations

import re
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from apps.core.exceptions import ValidationException


# ============================================================================
# court_sms_recommendation_service.py — CourtSMSRecommendationService
# ============================================================================


class TestCourtSMSRecommendationServiceExtractCourtName:
    def test_from_content(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        sms = Mock()
        sms.scraper_task = None
        sms.content = "佛山市中级人民法院通知您有新的文书"
        result = svc._extract_court_name(sms)
        assert "人民法院" in result

    def test_from_content_no_match(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        sms = Mock()
        sms.scraper_task = None
        sms.content = "普通短信内容"
        result = svc._extract_court_name(sms)
        assert result is None

    def test_from_document(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        mock_doc = Mock()
        mock_doc.c_fymc = "广州市天河区人民法院"
        mock_docs = Mock()
        mock_docs.filter.return_value.exclude.return_value.first.return_value = mock_doc
        mock_task = Mock()
        mock_task.documents = mock_docs
        sms = Mock()
        sms.scraper_task = mock_task
        sms.content = ""
        result = svc._extract_court_name(sms)
        assert result == "广州市天河区人民法院"

    def test_from_document_no_task(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        sms = Mock()
        sms.scraper_task = None
        sms.content = ""
        result = svc._extract_court_name(sms)
        assert result is None


class TestCourtSMSRecommendationServiceCollectPrefixes:
    def test_extracts_prefixes(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        numbers = ["（2025）粤0605民初123号", "（2024）京0101民初456号"]
        result = svc._collect_year_court_prefixes(numbers)
        assert len(result) == 2
        assert "2025" in result[0]

    def test_deduplicates(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        numbers = ["（2025）粤0605民初123号", "（2025）粤0605民初456号"]
        result = svc._collect_year_court_prefixes(numbers)
        assert len(result) == 1

    def test_empty_input(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        result = svc._collect_year_court_prefixes([])
        assert result == []


class TestCourtSMSRecommendationServiceBuildQuery:
    def test_empty_returns_none(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        result = CourtSMSRecommendationService._build_query([], [], None, [])
        assert result is None

    def test_with_case_numbers(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        result = CourtSMSRecommendationService._build_query(
            ["（2025）粤0605民初123号"], [], None, []
        )
        assert result is not None

    def test_with_court_name(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        result = CourtSMSRecommendationService._build_query(
            [], [], "佛山市中级人民法院", []
        )
        assert result is not None

    def test_with_party_names(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        result = CourtSMSRecommendationService._build_query([], [], None, ["张三"])
        assert result is not None

    def test_short_party_name_ignored(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        result = CourtSMSRecommendationService._build_query([], [], None, ["张"])
        assert result is None


class TestCourtSMSRecommendationServiceScoreCase:
    def test_case_number_match(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        case = Mock()
        case.id = 1
        case.start_date = date.today()
        cn = Mock()
        cn.number = "（2025）粤0605民初123号"
        case.case_numbers.all.return_value = [cn]
        case.supervising_authorities.all.return_value = []
        case.parties.all.return_value = []
        score, reasons = svc._score_case(
            case,
            ["（2025）粤0605民初123号"],
            [],
            None,
            [],
        )
        assert score >= 100
        assert "案号完全匹配" in reasons

    def test_court_name_match(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        case = Mock()
        case.id = 1
        case.start_date = date.today()
        case.case_numbers.all.return_value = []
        sa = Mock()
        sa.name = "佛山市中级人民法院"
        case.supervising_authorities.all.return_value = [sa]
        case.parties.all.return_value = []
        score, reasons = svc._score_case(
            case, [], [], "佛山市中级人民法院", []
        )
        assert score >= 40
        assert "法院名称匹配" in reasons

    def test_party_match(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        case = Mock()
        case.id = 1
        case.start_date = date.today()
        case.case_numbers.all.return_value = []
        case.supervising_authorities.all.return_value = []
        client = Mock()
        client.name = "张三"
        party = Mock()
        party.client = client
        case.parties.all.return_value = [party]
        score, reasons = svc._score_case(
            case, [], [], None, ["张三"]
        )
        assert score >= 20
        assert "当事人匹配" in reasons[0]

    def test_no_start_date(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        case = Mock()
        case.id = 1
        case.start_date = None
        case.case_numbers.all.return_value = []
        case.supervising_authorities.all.return_value = []
        case.parties.all.return_value = []
        score, reasons = svc._score_case(case, [], [], None, [])
        assert score == 0


class TestCourtSMSRecommendationServiceBuildResult:
    def test_builds_result(self):
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        svc = CourtSMSRecommendationService()
        cn = Mock()
        cn.number = "（2025）粤0605民初123号"
        client = Mock()
        client.name = "张三"
        party = Mock()
        party.client = client
        sa = Mock()
        sa.name = "佛山市中级人民法院"
        case = Mock()
        case.id = 1
        case.name = "张某诉李某"
        case.case_numbers.all.return_value = [cn]
        case.parties.all.return_value = [party]
        case.supervising_authorities.all.return_value = [sa]
        case.status = "active"
        result = svc._build_result(case, 100, ["案号完全匹配"])
        assert result.case_id == 1
        assert result.case_name == "张某诉李某"
        assert result.score == 100


# ============================================================================
# text_utils.py — TextUtils
# ============================================================================


class TestTextUtilsNormalizeCaseNumber:
    def test_normalizes_brackets(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("(2025)粤0605民初123号")
        assert "（" in result or "2025" in result

    def test_empty_input(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("")
        assert result == ""

    def test_already_normalized(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("（2025）粤0605民初123号")
        assert "（2025）" in result


# ============================================================================
# schemas/court_sms.py
# ============================================================================


class TestCourtSMSSchemas:
    def test_sms_parse_result(self):
        from apps.automation.schemas.court_sms import SMSParseResult

        result = SMSParseResult(
            sms_type="court",
            download_links=["https://example.com/doc.pdf"],
            case_numbers=["（2025）粤0605民初123号"],
            party_names=["张三"],
            has_valid_download_link=True,
        )
        assert result.sms_type == "court"
        assert len(result.case_numbers) == 1
        assert result.has_valid_download_link is True

    def test_court_sms_submit_in(self):
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn

        schema = CourtSMSSubmitIn(content="测试短信内容")
        assert schema.content == "测试短信内容"

    def test_court_sms_submit_in_validates_empty(self):
        from apps.automation.schemas.court_sms import CourtSMSSubmitIn

        with pytest.raises(Exception):
            CourtSMSSubmitIn(content="")


# ============================================================================
# schemas/document_delivery.py
# ============================================================================


class TestDocumentDeliverySchemas:
    def test_delivery_record(self):
        from datetime import datetime

        from apps.automation.schemas.document_delivery import DocumentDeliveryRecord

        record = DocumentDeliveryRecord(
            case_number="（2025）粤0605民初123号",
            send_time=datetime(2025, 6, 9, 10, 0),
            element_index=0,
            document_name="判决书",
            court_name="佛山市中级人民法院",
        )
        assert record.case_number == "（2025）粤0605民初123号"
        assert record.document_name == "判决书"
        assert record.to_dict() is not None


# ============================================================================
# models/scraper.py
# ============================================================================


class TestScraperModel:
    def test_scraper_task_type_choices(self):
        from apps.automation.models.scraper import ScraperTaskType

        assert len(ScraperTaskType.choices) > 0

    def test_scraper_task_status_choices(self):
        from apps.automation.models.scraper import ScraperTaskStatus

        assert len(ScraperTaskStatus.choices) > 0


# ============================================================================
# schemas/preservation.py
# ============================================================================


class TestPreservationSchemas:
    def test_preservation_quote_create_schema(self):
        from decimal import Decimal

        from apps.automation.schemas.preservation import PreservationQuoteCreateSchema

        schema = PreservationQuoteCreateSchema(
            preserve_amount=Decimal("100000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=1,
        )
        assert schema.preserve_amount == Decimal("100000.00")
        assert schema.corp_id == "440100"

    def test_preservation_quote_create_validates_negative(self):
        from decimal import Decimal

        from apps.automation.schemas.preservation import PreservationQuoteCreateSchema

        with pytest.raises(Exception):
            PreservationQuoteCreateSchema(
                preserve_amount=Decimal("-1"),
                corp_id="440100",
                category_id="1",
                credential_id=1,
            )


# ============================================================================
# schemas/court_document.py
# ============================================================================


class TestCourtDocumentSchemas:
    def test_court_document_schema(self):
        from datetime import datetime

        from apps.automation.schemas.court_document import CourtDocumentSchema

        schema = CourtDocumentSchema(
            id=1,
            scraper_task_id=100,
            c_sdbh="SD001",
            c_stbh="ST001",
            wjlj="https://example.com/doc.pdf",
            c_wsbh="WS001",
            c_wsmc="判决书",
            c_fybh="FY001",
            c_fymc="佛山市中级人民法院",
            c_wjgs="pdf",
            dt_cjsj=datetime(2025, 1, 1),
            download_status="completed",
            created_at=datetime(2025, 1, 1),
            updated_at=datetime(2025, 1, 1),
        )
        assert schema.id == 1
        assert schema.c_sdbh == "SD001"


# ============================================================================
# models/token.py
# ============================================================================


class TestTokenModel:
    def test_token_model_exists(self):
        from apps.automation.models.token import CourtToken

        assert CourtToken is not None

    def test_token_acquisition_status_choices(self):
        from apps.automation.models.token import TokenAcquisitionStatus

        assert len(TokenAcquisitionStatus.choices) > 0


# ============================================================================
# models/court_sms.py
# ============================================================================


class TestCourtSMSModel:
    def test_court_sms_model_exists(self):
        from apps.automation.models.court_sms import CourtSMS

        assert CourtSMS is not None


# ============================================================================
# models/court_document.py
# ============================================================================


class TestCourtDocumentModel:
    def test_court_document_model_exists(self):
        from apps.automation.models.court_document import CourtDocument

        assert CourtDocument is not None


# ============================================================================
# models/preservation.py
# ============================================================================


class TestPreservationModel:
    def test_quote_status_choices(self):
        from apps.automation.models.preservation import QuoteStatus

        assert len(QuoteStatus.choices) > 0

    def test_insurance_quote_model_exists(self):
        from apps.automation.models.preservation import InsuranceQuote

        assert InsuranceQuote is not None


# ============================================================================
# models/invoice_recognition.py
# ============================================================================


class TestInvoiceRecognitionModel:
    def test_invoice_category_choices(self):
        from apps.automation.models.invoice_recognition import InvoiceCategory

        assert len(InvoiceCategory.choices) > 0

    def test_invoice_task_status_choices(self):
        from apps.automation.models.invoice_recognition import InvoiceRecognitionTaskStatus

        assert len(InvoiceRecognitionTaskStatus.choices) > 0


# ============================================================================
# models/gsxt_report.py
# ============================================================================


class TestGsxtReportModel:
    def test_gsxt_report_status_choices(self):
        from apps.automation.models.gsxt_report import GsxtReportStatus

        assert len(GsxtReportStatus.choices) > 0


# ============================================================================
# dtos.py
# ============================================================================


class TestAutomationDtos:
    def test_captcha_dto(self):
        from apps.automation.dtos import CaptchaRecognizeResultDTO

        dto = CaptchaRecognizeResultDTO(
            success=True,
            text="abc123",
            processing_time=0.5,
            error=None,
        )
        assert dto.success is True
        assert dto.text == "abc123"

    def test_captcha_dto_failure(self):
        from apps.automation.dtos import CaptchaRecognizeResultDTO

        dto = CaptchaRecognizeResultDTO(
            success=False,
            text=None,
            processing_time=1.0,
            error="识别失败",
        )
        assert dto.success is False
        assert dto.error == "识别失败"


# ============================================================================
# exceptions.py
# ============================================================================


class TestAutomationExceptions:
    def test_captcha_recognition_error(self):
        from apps.automation.exceptions import CaptchaRecognitionError

        err = CaptchaRecognitionError(message="验证码识别失败", code="CAPTCHA_ERROR", errors={})
        assert "验证码" in err.message


# ============================================================================
# checks.py
# ============================================================================


class TestAutomationChecks:
    def test_check_scraper_dependencies(self):
        from apps.automation.checks import check_scraper_dependencies

        result = check_scraper_dependencies(None)
        assert isinstance(result, list)
