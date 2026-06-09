"""Coverage tests for story_viz, doc_converter, evidence, automation, workbench, oa_filing, finance, contracts, client, cases, reminders, organization, sales_dispute, pdf_splitting."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock
from datetime import date
from decimal import Decimal


# ── story_viz ──
class TestAnimationHtmlComposerService:
    def test_compose_timeline(self):
        from apps.story_viz.services.html_composer_service import AnimationHtmlComposerService
        svc = AnimationHtmlComposerService()
        html = svc.compose(
            title="Test Timeline",
            viz_type="timeline",
            render_payload={"nodes": [{"time": "2024-01", "label": "事件1"}]},
            fragment_payload={"fragments": []},
        )
        assert "Test Timeline" in html
        assert "<!doctype html>" in html

    def test_compose_relationship(self):
        from apps.story_viz.services.html_composer_service import AnimationHtmlComposerService
        svc = AnimationHtmlComposerService()
        html = svc.compose(
            title="关系图",
            viz_type="relationship",
            render_payload={"nodes": [{"id": "1", "label": "A"}], "edges": [{"source": "1", "target": "1"}]},
            fragment_payload={},
        )
        assert "d3.min.js" in html

    def test_compose_claim_judgment(self):
        from apps.story_viz.services.html_composer_service import AnimationHtmlComposerService
        svc = AnimationHtmlComposerService()
        html = svc.compose(
            title="诉求vs判决",
            viz_type="claim_judgment",
            render_payload={"nodes": [], "annotations": ["要点1"]},
            fragment_payload={},
        )
        assert "诉求 vs 判决" in html


# ── automation/document_delivery ──
class TestCourtDocumentResponseParser:
    def test_parse_document_list_error(self):
        from apps.automation.services.document_delivery.court_api.court_document_response_parser import CourtDocumentResponseParser
        from apps.automation.services.document_delivery.court_api.court_document_api_exceptions import ApiResponseError
        parser = CourtDocumentResponseParser()
        with pytest.raises(ApiResponseError):
            parser.parse_document_list({"code": 500, "msg": "error"})

    def test_parse_document_list_success(self):
        from apps.automation.services.document_delivery.court_api.court_document_response_parser import CourtDocumentResponseParser
        parser = CourtDocumentResponseParser()
        result = parser.parse_document_list({"code": 200, "data": {"total": 0, "data": []}})
        assert result.total == 0
        assert result.documents == []

    def test_parse_document_details_error(self):
        from apps.automation.services.document_delivery.court_api.court_document_response_parser import CourtDocumentResponseParser
        from apps.automation.services.document_delivery.court_api.court_document_api_exceptions import ApiResponseError
        parser = CourtDocumentResponseParser()
        with pytest.raises(ApiResponseError):
            parser.parse_document_details({"code": 400, "msg": "bad"})


class TestCourtDocumentHttpClient:
    def test_init(self):
        from apps.automation.services.document_delivery.court_api.court_document_http_client import CourtDocumentHttpClient
        client = CourtDocumentHttpClient(timeout_seconds=10.0)
        assert client.timeout_seconds == 10.0


class TestCourtDocumentApiCoordinator:
    def test_auth_headers(self):
        from apps.automation.services.document_delivery.court_api.court_document_api_coordinator import CourtDocumentApiCoordinator
        from apps.automation.services.document_delivery.court_api.court_document_http_client import CourtDocumentHttpClient
        from apps.automation.services.document_delivery.court_api.court_document_response_parser import CourtDocumentResponseParser
        coord = CourtDocumentApiCoordinator(
            http_client=CourtDocumentHttpClient(timeout_seconds=10),
            parser=CourtDocumentResponseParser(),
            retry_count=1,
        )
        headers = coord._auth_headers("my-token")
        assert headers["Authorization"] == "my-token"
        assert headers["Content-Type"] == "application/json"


# ── automation/services/token ──
class TestCourtTokenStoreService:
    def test_get_latest_valid_token_none(self):
        from apps.automation.services.token.court_token_store_service import CourtTokenStoreService
        svc = CourtTokenStoreService()
        with patch("apps.automation.models.CourtToken") as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value.first.return_value = None
            result = svc.get_latest_valid_token_internal(site_name="test")
            assert result is None


# ── automation/services/scraper ──
class TestGuaranteeDataMixin:
    def test_normalize_party_type(self):
        from apps.automation.services.scraper.sites.guarantee.data_mixin import GuaranteeDataMixin
        mixin = GuaranteeDataMixin()
        assert mixin._normalize_party_type("natural") == "natural"
        assert mixin._normalize_party_type("legal") == "legal"
        assert mixin._normalize_party_type("corp") == "legal"
        assert mixin._normalize_party_type("non_legal_org") == "non_legal_org"
        assert mixin._normalize_party_type("unknown") == "natural"
        assert mixin._normalize_party_type(None) == "natural"

    def test_parse_case_number(self):
        from apps.automation.services.scraper.sites.guarantee.data_mixin import GuaranteeDataMixin
        year, court, type_, seq = GuaranteeDataMixin.parse_case_number("(2024)粤01民初123号")
        assert year == "2024"
        assert seq == "123"

    def test_parse_case_number_invalid(self):
        from apps.automation.services.scraper.sites.guarantee.data_mixin import GuaranteeDataMixin
        year, court, type_, seq = GuaranteeDataMixin.parse_case_number("invalid")
        assert year == "" and court == "" and type_ == "" and seq == ""

    def test_build_agent_dialog_defaults(self):
        from apps.automation.services.scraper.sites.guarantee.data_mixin import GuaranteeDataMixin
        mixin = GuaranteeDataMixin()
        mixin.DEFAULT_NATURAL_ID_NUMBER = "000000000000000000"
        result = mixin._build_agent_dialog_defaults({"name": "张律师", "phone": "12000000000"})
        assert result["party_type"] == "agent"
        assert result["name"] == "张律师"


# ── automation/ocr ──
class TestPDFTextExtractor:
    def test_init(self):
        from apps.automation.services.ocr.pdf_text_extractor import PDFTextExtractor
        ext = PDFTextExtractor()
        assert ext.MIN_TEXT_THRESHOLD == 50


# ── automation/court_filing ──
class TestCourtFilingScraper:
    def test_class_exists(self):
        from apps.automation.services.scraper.scrapers.court_filing import CourtFilingScraper
        assert CourtFilingScraper is not None


# ── automation/wiring ──
def test_wiring_function_exists():
    from apps.automation.services.document_delivery.wiring import build_document_delivery_coordinator
    assert callable(build_document_delivery_coordinator)


# ── automation/gsxt_tasks ──
def test_check_gsxt_report_email_func_exists():
    from apps.automation.tasks.gsxt_tasks import check_gsxt_report_email
    assert callable(check_gsxt_report_email)


# ── automation/process_pending_tasks ──
class TestProcessPendingTasksCommand:
    def test_command_class_exists(self):
        from apps.automation.management.commands.process_pending_tasks import Command
        assert Command.help == "处理所有待处理的爬虫任务"


# ── reminders ──
class TestIcsUrlProvider:
    def test_validate_url_http_rejected(self):
        from apps.reminders.services.calendar_providers.ics_url_provider import IcsUrlProvider
        provider = IcsUrlProvider()
        error = provider._validate_url("http://example.com/cal.ics")
        assert "https" in error

    def test_validate_url_no_host(self):
        from apps.reminders.services.calendar_providers.ics_url_provider import IcsUrlProvider
        provider = IcsUrlProvider()
        error = provider._validate_url("https://")
        assert "主机名" in error

    def test_validate_url_localhost(self):
        from apps.reminders.services.calendar_providers.ics_url_provider import IcsUrlProvider
        provider = IcsUrlProvider()
        error = provider._validate_url("https://localhost/cal.ics")
        assert "本地" in error

    def test_validate_url_private_ip(self):
        from apps.reminders.services.calendar_providers.ics_url_provider import IcsUrlProvider
        provider = IcsUrlProvider()
        error = provider._validate_url("https://192.168.1.1/cal.ics")
        assert "内网" in error

    def test_validate_url_valid(self):
        from apps.reminders.services.calendar_providers.ics_url_provider import IcsUrlProvider
        provider = IcsUrlProvider()
        error = provider._validate_url("https://calendar.google.com/cal.ics")
        assert error == ""

    @patch("apps.reminders.services.calendar_providers.ics_url_provider.httpx")
    def test_fetch_events_invalid_url(self, mock_httpx):
        from apps.reminders.services.calendar_providers.ics_url_provider import IcsUrlProvider
        provider = IcsUrlProvider()
        result = provider.fetch_events(url="http://bad")
        assert result == []


class TestTargetQuery:
    def test_get_target_options_func_exists(self):
        from apps.reminders.services.target_query import get_target_options
        assert callable(get_target_options)


# ── evidence ──
class TestEvidenceFileService:
    def test_supported_formats(self):
        from apps.evidence.services.core.evidence_file_service import EvidenceFileService
        svc = EvidenceFileService()
        assert ".pdf" in svc.SUPPORTED_FORMATS
        assert svc.MAX_FILE_SIZE == 50 * 1024 * 1024

    @pytest.mark.django_db
    def test_upload_file_unsupported_format(self):
        from apps.evidence.services.core.evidence_file_service import EvidenceFileService
        from apps.core.exceptions import ValidationException
        svc = EvidenceFileService()
        mock_item = MagicMock()
        mock_file = MagicMock()
        mock_file.name = "test.exe"
        mock_file.size = 100
        with pytest.raises(ValidationException):
            svc.upload_file(item=mock_item, file=mock_file)

    @pytest.mark.django_db
    def test_upload_file_too_large(self):
        from apps.evidence.services.core.evidence_file_service import EvidenceFileService
        from apps.core.exceptions import ValidationException
        svc = EvidenceFileService()
        mock_item = MagicMock()
        mock_file = MagicMock()
        mock_file.name = "big.pdf"
        mock_file.size = 100 * 1024 * 1024
        with pytest.raises(ValidationException):
            svc.upload_file(item=mock_item, file=mock_file)


class TestEvidenceAIService:
    def test_suggest_purpose_empty(self):
        from apps.evidence.services.ai.evidence_ai_service import EvidenceAIService
        svc = EvidenceAIService()
        # Will return empty list on LLM failure
        result = svc.suggest_purpose()
        assert isinstance(result, list)

    def test_generate_cross_exam_empty(self):
        from apps.evidence.services.ai.evidence_ai_service import EvidenceAIService
        svc = EvidenceAIService()
        result = svc.generate_cross_examination()
        assert isinstance(result, dict)


class TestEvidenceQueryService:
    def test_list_evidence_items_empty(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService
        svc = EvidenceQueryService()
        result = svc.list_evidence_items_for_digest_internal([], [])
        assert result == []


# ── core/services/email ──
class TestEmailService:
    @patch("apps.core.services.email_service.EmailConfigService")
    def test_send_password_reset_not_configured(self, mock_config):
        from apps.core.services.email_service import EmailService
        mock_config.is_configured.return_value = False
        result = EmailService.send_password_reset_email("test@test.com", "user", "http://reset")  # allowlist secret
        assert result is False

    @patch("apps.core.services.email_service.EmailConfigService")
    def test_send_password_changed_not_configured(self, mock_config):
        from apps.core.services.email_service import EmailService
        mock_config.is_configured.return_value = False
        result = EmailService.send_password_changed_notification("test@test.com", "user")  # allowlist secret
        assert result is False


# ── contracts ──
class TestFilingNumberService:
    def test_format_case_type_label(self):
        from apps.contracts.services.assignment.filing_number_service import FilingNumberService
        from apps.core.models.enums import CaseType
        svc = FilingNumberService()
        assert svc._format_case_type_label(CaseType.CIVIL) == "民商事"
        assert svc._format_case_type_label(CaseType.CRIMINAL) == "刑事"

    def test_generate_contract_filing_number_empty_type(self):
        from apps.contracts.services.assignment.filing_number_service import FilingNumberService
        from apps.core.exceptions import ValidationException
        svc = FilingNumberService()
        with pytest.raises(ValidationException):
            svc.generate_contract_filing_number(1, "", 2024)

    def test_generate_contract_filing_number_bad_year(self):
        from apps.contracts.services.assignment.filing_number_service import FilingNumberService
        from apps.core.exceptions import ValidationException
        svc = FilingNumberService()
        with pytest.raises(ValidationException):
            svc.generate_contract_filing_number(1, "civil", 9999)


class TestClientPaymentImageService:
    def test_get_image_url_empty(self):
        from apps.contracts.services.client_payment.client_payment_image_service import ClientPaymentImageService
        svc = ClientPaymentImageService()
        assert svc.get_image_url("") == ""

    def test_get_image_url(self):
        from apps.contracts.services.client_payment.client_payment_image_service import ClientPaymentImageService
        svc = ClientPaymentImageService()
        url = svc.get_image_url("contracts/payments/1/img.jpg")
        assert "contracts/payments/1/img.jpg" in url

    def test_delete_image_empty(self):
        from apps.contracts.services.client_payment.client_payment_image_service import ClientPaymentImageService
        svc = ClientPaymentImageService()
        svc.delete_image("")  # Should not raise


class TestContractListAssembler:
    def test_enrich_empty(self):
        from apps.contracts.services.contract.assemblers.contract_list_assembler import ContractListAssembler
        svc = ContractListAssembler()
        svc.enrich([])  # Should not raise


class TestDocumentTemplateMatcher:
    def test_class_exists(self):
        from apps.documents.services.generation.pipeline.template_matcher import TemplateMatcher
        assert TemplateMatcher is not None


class TestPlaceholderExtractor:
    def test_pattern_matches(self):
        from apps.documents.services.document_template.placeholder_extractor import PLACEHOLDER_PATTERN
        import re
        matches = PLACEHOLDER_PATTERN.findall("{{ 案件名称 }} 和 {{ 合同金额 }}")
        assert "案件名称" in matches
        assert "合同金额" in matches


# ── documents/generation ──
class TestDocxPreviewService:
    def test_class_exists(self):
        from apps.documents.services.generation.pipeline.preview import DocxPreviewService
        assert DocxPreviewService is not None


# ── documents/placeholders ──
class TestEnforcementServices:
    def test_exit_restriction_no_case_id(self):
        from apps.documents.services.placeholders.litigation.enforcement_exit_restriction_service import EnforcementExitRestrictionRequestService
        svc = EnforcementExitRestrictionRequestService.__new__(EnforcementExitRestrictionRequestService)
        svc.case_details_accessor = MagicMock()
        result = svc.generate({})
        assert result == {}

    def test_spending_restriction_no_case_id(self):
        from apps.documents.services.placeholders.litigation.enforcement_spending_restriction_service import EnforcementSpendingRestrictionRequestService
        svc = EnforcementSpendingRestrictionRequestService.__new__(EnforcementSpendingRestrictionRequestService)
        svc.case_details_accessor = MagicMock()
        result = svc.generate({})
        assert result == {}


class TestCriminalCauseService:
    def test_generate_no_contract(self):
        from apps.documents.services.placeholders.contract.criminal_cause_service import CriminalCauseService
        svc = CriminalCauseService()
        result = svc.generate({})
        assert result == {"案由": ""}

    def test_generate_with_case(self):
        from apps.documents.services.placeholders.contract.criminal_cause_service import CriminalCauseService
        svc = CriminalCauseService()
        mock_case = MagicMock()
        mock_case.cause_of_action = "盗窃罪"
        result = svc.generate({"case": mock_case})
        assert result == {"案由": "盗窃罪"}

    def test_clean_cause_of_action(self):
        from apps.documents.services.placeholders.contract.criminal_cause_service import CriminalCauseService
        svc = CriminalCauseService()
        mock_case = MagicMock()
        mock_case.cause_of_action = "  危险作业罪  "
        result = svc._clean_cause_of_action(mock_case)
        assert result == "危险作业罪"

    def test_clean_cause_of_action_none(self):
        from apps.documents.services.placeholders.contract.criminal_cause_service import CriminalCauseService
        svc = CriminalCauseService()
        mock_case = MagicMock()
        mock_case.cause_of_action = None
        result = svc._clean_cause_of_action(mock_case)
        assert result == ""


class TestPrincipalSignatureService:
    def test_generate_no_contract(self):
        from apps.documents.services.placeholders.party.principal_signature_service import PrincipalSignatureService
        svc = PrincipalSignatureService()
        result = svc.generate({})
        assert result == {}


class TestDocumentTemplateValidationService:
    def test_normalize_file_path_none(self):
        from apps.documents.services.document_template.validation_service import DocumentTemplateValidationService
        svc = DocumentTemplateValidationService()
        assert svc.normalize_file_path(None) is None

    def test_normalize_file_path_strips(self):
        from apps.documents.services.document_template.validation_service import DocumentTemplateValidationService
        svc = DocumentTemplateValidationService()
        assert svc.normalize_file_path("  path  ") == "path"

    def test_validate_file_path_empty(self):
        from apps.documents.services.document_template.validation_service import DocumentTemplateValidationService
        svc = DocumentTemplateValidationService()
        assert svc.validate_file_path("") is False

    def test_require_single_source_both(self):
        from apps.documents.services.document_template.validation_service import DocumentTemplateValidationService
        from apps.core.exceptions import ValidationException
        svc = DocumentTemplateValidationService()
        with pytest.raises(ValidationException):
            svc.require_single_source(file=MagicMock(), file_path="/some/path")

    def test_require_single_source_neither(self):
        from apps.documents.services.document_template.validation_service import DocumentTemplateValidationService
        from apps.core.exceptions import ValidationException
        svc = DocumentTemplateValidationService()
        with pytest.raises(ValidationException):
            svc.require_single_source(file=None, file_path=None)


# ── organization ──
class TestLawyerResolveService:
    def test_cache_init(self):
        from apps.organization.services.lawyer_resolve_service import LawyerResolveService
        svc = LawyerResolveService()
        assert svc._cache == {}

    @patch("apps.organization.services.lawyer_resolve_service.Lawyer")
    def test_resolve_no_phone_no_username(self, mock_model):
        from apps.organization.services.lawyer_resolve_service import LawyerResolveService
        svc = LawyerResolveService()
        result = svc.resolve({})
        assert result is None


# ── client ──
class TestClientResolveService:
    def test_cache_init(self):
        from apps.client.services.client_resolve_service import ClientResolveService
        svc = ClientResolveService()
        assert svc._cache == {}


class TestClientQueryService:
    def test_init(self):
        from apps.client.services.client_query_service import ClientQueryService
        svc = ClientQueryService()
        assert svc._list_query is None

    def test_init_with_deps(self):
        from apps.client.services.client_query_service import ClientQueryService
        mock_list = MagicMock()
        svc = ClientQueryService(list_query=mock_list)
        assert svc.list_query is mock_list


class TestClientQueryFacade:
    def test_init(self):
        from apps.client.services.client_query_facade import ClientQueryFacade
        facade = ClientQueryFacade()
        assert facade._query_service is None


# ── cases ──
class TestFilenamePolicy:
    def test_safe_name(self):
        from apps.cases.services.template.unified.filename import FilenamePolicy
        policy = FilenamePolicy(date_provider=MagicMock(today_yyyymmdd=MagicMock(return_value="20240101")))
        assert policy.safe_name("") == "未命名"
        assert policy.safe_name("  hello  ") == "hello"
        assert policy.safe_name("a/b") == "a／b"

    def test_build_default(self):
        from apps.cases.services.template.unified.filename import FilenamePolicy, FilenameInputs
        date_prov = MagicMock(today_yyyymmdd=MagicMock(return_value="20240101"))
        policy = FilenamePolicy(date_provider=date_prov)
        inputs = FilenameInputs(template_name="起诉状", case_name="张三诉李四", client_name=None, function_code=None, mode=None, our_party_count=1)
        result = policy.build(inputs=inputs, legal_rep_cert_code="LRC", power_of_attorney_code="POA")
        assert "起诉状" in result
        assert "20240101" in result


class TestPartySelectionPolicy:
    def test_select_default(self):
        from apps.cases.services.template.unified.party_selection import PartySelectionPolicy
        policy = PartySelectionPolicy(repo=MagicMock(), client_service=MagicMock())
        result = policy.select(case=MagicMock(), function_code=None, client_id=None, client_ids=None, mode=None, legal_rep_cert_code="LRC", power_of_attorney_code="POA")
        assert result.client is None


class TestCaseLogInternalService:
    @pytest.mark.django_db
    def test_get_case_log_model_not_found(self):
        from apps.cases.services.case.case_log_internal_service import CaseLogInternalService
        svc = CaseLogInternalService()
        # Use a non-existent ID that won't be in the test DB
        result = svc.get_case_log_model_internal(-999999)
        assert result is None


class TestCaseFullCreateWorkflow:
    def test_init(self):
        from apps.cases.services.case.workflows.case_full_create_workflow import CaseFullCreateWorkflow
        mock_svc = MagicMock()
        wf = CaseFullCreateWorkflow(case_service=mock_svc)
        assert wf.case_service is mock_svc


class TestCasesActionsMixin:
    def test_class_exists(self):
        from apps.cases.admin.mixins.actions import CaseAdminActionsMixin
        assert CaseAdminActionsMixin is not None


# ── pdf_splitting ──
def test_execute_pdf_split_job_func_exists():
    from apps.pdf_splitting.tasks import execute_pdf_split_job, export_pdf_split_job
    assert callable(execute_pdf_split_job)
    assert callable(export_pdf_split_job)


# ── doc_converter ──
class TestDocConverterEngine:
    def test_batch_convert_empty(self):
        from apps.doc_converter.services.engine import batch_convert
        result = batch_convert([], "/tmp/test_output")
        assert result == {}


class TestCleanupCommand:
    def test_command_exists(self):
        from apps.doc_converter.management.commands.cleanup_stale_doc_converter_jobs import Command
        assert Command.help == "清理过期的 DOC 转换任务及其文件"


# ── workbench ──
class TestWorkbenchMessageService:
    def test_message_to_dict(self):
        from apps.workbench.services.message_service import WorkbenchMessageService
        assert callable(WorkbenchMessageService._message_to_dict)


# ── sales_dispute ──
def test_dashboard_router_exists():
    from apps.sales_dispute.api.sales_dispute_dashboard_api import router
    assert router is not None


# ── document_recognition ──
class TestDocumentRecognitionTaskService:
    def test_class_exists(self):
        from apps.document_recognition.services.task_service import DocumentRecognitionTaskService
        svc = DocumentRecognitionTaskService()
        assert svc is not None


class TestDocumentRecognitionNotificationService:
    def test_build_notification_message(self):
        from apps.document_recognition.services.notification_service import DocumentRecognitionNotificationService
        svc = DocumentRecognitionNotificationService(case_chat_service=MagicMock())
        msg = svc.build_notification_message(
            document_type="summons",
            case_number="(2024)粤01民初123号",
            key_time=None,
            case_name="张三诉李四",
        )
        assert "传票" in msg
        assert "张三诉李四" in msg

    def test_build_notification_with_key_time(self):
        from apps.document_recognition.services.notification_service import DocumentRecognitionNotificationService
        from datetime import datetime
        svc = DocumentRecognitionNotificationService(case_chat_service=MagicMock())
        msg = svc.build_notification_message(
            document_type="summons",
            case_number=None,
            key_time=datetime(2024, 6, 15, 9, 30),
            case_name="测试案件",
        )
        assert "开庭时间" in msg

    def test_build_notification_other_type(self):
        from apps.document_recognition.services.notification_service import DocumentRecognitionNotificationService
        svc = DocumentRecognitionNotificationService(case_chat_service=MagicMock())
        msg = svc.build_notification_message(
            document_type="other",
            case_number="CN123",
            key_time=None,
            case_name="案件",
        )
        assert "法院文书" in msg


# ── core/dependencies ──
def test_automation_sms_wiring_exists():
    from apps.core.dependencies.automation_sms_wiring import build_court_sms_service_with_deps
    assert callable(build_court_sms_service_with_deps)


# ── core/tasking ──
class TestTaskQueryService:
    def test_class_exists(self):
        from apps.core.tasking.query import TaskQueryService, ScheduleQueryService
        assert TaskQueryService is not None
        assert ScheduleQueryService is not None


class TestTaskQueueQuery:
    def test_functions_exist(self):
        from apps.core.tasking.task_queue_query import (
            list_queued, list_completed, list_failed, list_scheduled,
            get_last_run_time, delete_task, delete_schedule, get_task_or_none, resubmit_task,
        )
        for fn in [list_queued, list_completed, list_failed, list_scheduled,
                    get_last_run_time, delete_task, delete_schedule, get_task_or_none, resubmit_task]:
            assert callable(fn)


# ── documents/admin ──
class TestTemplateAuditLogAdmin:
    def test_has_permissions(self):
        from apps.documents.admin.audit_log_admin import TemplateAuditLogAdmin
        admin = TemplateAuditLogAdmin.__new__(TemplateAuditLogAdmin)
        assert admin.has_add_permission(MagicMock()) is False
        assert admin.has_change_permission(MagicMock()) is False
        assert admin.has_delete_permission(MagicMock()) is False


class TestEvidenceItemInline:
    def test_class_exists(self):
        from apps.documents.admin.evidence.inlines import EvidenceItemInline
        assert EvidenceItemInline is not None


# ── evidence/admin ──
class TestEvidenceAdminActions:
    def test_class_exists(self):
        from apps.evidence.admin.evidence.mixins.actions import EvidenceListAdminActionsMixin
        assert EvidenceListAdminActionsMixin is not None


# ── finance/tasks ──
def test_finance_tasks_exist():
    import importlib
    mod = importlib.import_module("apps.finance.tasks")
    assert mod is not None


# ── oa_filing ──
class TestOaFilingServices:
    def test_import_session_service_exists(self):
        import importlib
        mod = importlib.import_module("apps.oa_filing.services.import_session_service")
        assert mod is not None

    def test_jtn_filing_service_exists(self):
        import importlib
        mod = importlib.import_module("apps.oa_filing.services.oa_scripts.jtn.filing.service")
        assert mod is not None


# ── automation/services/admin ──
class TestDocumentDeliveryScheduleAdminService:
    def test_init(self):
        from apps.automation.services.admin.document_delivery_schedule_admin_service import DocumentDeliveryScheduleAdminService
        svc = DocumentDeliveryScheduleAdminService()
        assert svc._schedule_service is None

    def test_schedule_service_property_raises(self):
        from apps.automation.services.admin.document_delivery_schedule_admin_service import DocumentDeliveryScheduleAdminService
        svc = DocumentDeliveryScheduleAdminService()
        with pytest.raises(RuntimeError):
            _ = svc.schedule_service


# ── documents/evidence ──
class TestEvidencePageRangeCalculator:
    def test_class_exists(self):
        from apps.evidence.services.core.page_range_calculator import EvidencePageRangeCalculator
        assert EvidencePageRangeCalculator is not None


class TestDocumentsEvidencePageRange:
    def test_class_exists(self):
        from apps.documents.services.evidence.page_range_calculator import EvidencePageRangeCalculator
        assert EvidencePageRangeCalculator is not None
