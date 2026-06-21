"""Coverage tests for automation scrapers, SMS, insurance, GSXT, and admin services."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
try:
    from plugins.court_automation import filing  # noqa: F401
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)



# --- hbfy_scraper ---

class TestHbfyScraper:
    def test_extract_public_msg_code(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        result = scraper._extract_public_msg_code("http://dzsd.hbfy.gov.cn/hb/msg=ABC123")
        assert result == "ABC123"

    def test_extract_public_msg_code_no_match(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        assert scraper._extract_public_msg_code("http://example.com") == ""

    def test_public_need_captcha_true(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        assert scraper._public_need_captcha({"isNeedCaptcha": "Y"}) is True

    def test_public_need_captcha_false(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        assert scraper._public_need_captcha({"isNeedCaptcha": "N"}) is False

    def test_public_doc_list(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        result = scraper._public_doc_list({"docList": [{"id": 1}]})
        assert len(result) == 1

    def test_public_doc_list_dict(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        result = scraper._public_doc_list({"docList": {"id": 1}})
        assert len(result) == 1

    def test_public_doc_list_empty(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        assert scraper._public_doc_list({}) == []

    def test_public_has_downloadable_docs_true(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        assert scraper._public_has_downloadable_docs({"docList": [{"downloadPath": "/file.pdf"}]}) is True

    def test_public_has_downloadable_docs_false(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        assert scraper._public_has_downloadable_docs({"docList": []}) is False

    def test_safe_filename(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        result = scraper._safe_filename("test:file*name.pdf")
        assert ":" not in result
        assert "*" not in result

    def test_safe_filename_empty(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        result = scraper._safe_filename("")
        assert len(result) > 0

    def test_encode_user_code(self):
        import base64

        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        result = scraper._encode_user_code("test123")
        assert "+" not in result
        assert "/" not in result

    def test_extract_account_credentials_from_content(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        account, pwd = scraper._extract_account_credentials_from_content("账号 123456789012345 默认密码：abc123")
        assert account == "123456789012345"
        assert pwd == "abc123"

    def test_extract_download_candidates(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        result = scraper._extract_download_candidates(
            '<a href="/deli/TsysFilesInfo/tsysfilesinfo!downloadByPath.action?path=/test.pdf">下载</a>'
        )
        assert len(result) > 0

    def test_extract_download_candidates_empty(self):
        from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper

        scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
        assert scraper._extract_download_candidates("<html>no links</html>") == []


# --- base_court_scraper ---

class TestBaseCourtScraper:
    def test_import(self):
        from apps.automation.services.scraper.scrapers.court_document.base_court_scraper import BaseCourtDocumentScraper

        assert BaseCourtDocumentScraper is not None


# --- sfdw_scraper ---

class TestSfdwScraper:
    def test_import(self):
        from apps.automation.services.scraper.scrapers.court_document.sfdw_scraper import SfdwCourtScraper

        assert SfdwCourtScraper is not None


# --- jysd_scraper ---

class TestJysdScraper:
    def test_import(self):
        from apps.automation.services.scraper.scrapers.court_document.jysd_scraper import JysdCourtScraper

        assert JysdCourtScraper is not None


# --- court_zxfw ---

class TestCourtZxfw:
    def test_import(self):
        from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService

        assert CourtZxfwService is not None


# --- court_zxfw_filing ---

class TestCourtZxfwFiling:
    def test_filing_steps_import(self):
        from plugins.court_automation.filing.playwright_filing.filing_steps import FilingStepsMixin

        assert FilingStepsMixin is not None

    def test_party_info_handler_import(self):
        from plugins.court_automation.filing.playwright_filing.party_info_handler import PartyInfoHandlerMixin

        assert PartyInfoHandlerMixin is not None

    def test_form_utils_import(self):
        from plugins.court_automation.filing.playwright_filing.form_utils import FormUtilsMixin

        assert FormUtilsMixin is not None

    def test_service_import(self):
        from plugins.court_automation.filing.playwright_filing.service import CourtZxfwFilingService

        assert CourtZxfwFilingService is not None


# --- guarantee upload_mixin ---

class TestGuaranteeUploadMixin:
    def test_import(self):
        from apps.automation.services.scraper.sites.guarantee.upload_mixin import GuaranteeUploadMixin

        assert GuaranteeUploadMixin is not None


# --- guarantee form_filling_mixin ---

class TestGuaranteeFormFillingMixin:
    def test_import(self):
        from apps.automation.services.scraper.sites.guarantee.form_filling_mixin import GuaranteeFormFillingMixin

        assert GuaranteeFormFillingMixin is not None


# --- SMS services ---

class TestSMSServices:
    def test_court_sms_service_import(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService

        assert CourtSMSService is not None

    def test_sms_download_mixin_import(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin is not None

    def test_sms_document_mixin_import(self):
        from apps.automation.services.sms._sms_document_mixin import SMSDocumentMixin

        assert SMSDocumentMixin is not None

    def test_document_attachment_service_import(self):
        from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService

        assert DocumentAttachmentService is not None


# --- insurance ---

class TestInsurance:
    def test_court_insurance_client_import(self):
        from plugins.court_automation.preservation_quote.court_insurance_client import CourtInsuranceClient

        assert CourtInsuranceClient is not None

    def test_preservation_quote_service_import(self):
        from plugins.court_automation.preservation_quote.service import PreservationQuoteService

        assert PreservationQuoteService is not None


# --- GSXT ---

class TestGSXT:
    def test_gsxt_login_service_import(self):
        from apps.automation.services.gsxt.gsxt_login_service import GsxtLoginService

        assert GsxtLoginService is not None

    def test_gsxt_report_service_import(self):
        from apps.automation.services.gsxt.gsxt_report_service import GsxtReportService

        assert GsxtReportService is not None


# --- admin services ---

class TestAdminServices:
    def test_preservation_quote_admin_service_import(self):
        from plugins.court_automation.preservation_quote.admin_service import PreservationQuoteAdminService

        assert PreservationQuoteAdminService is not None

    def test_court_document_admin_service_import(self):
        from apps.automation.services.admin.court_document_admin_service import CourtDocumentAdminService

        assert CourtDocumentAdminService is not None


# --- SMS admin ---

class TestSMSAdmin:
    def test_court_sms_admin_actions_import(self):
        from apps.automation.admin.sms.court_sms_admin_actions import CourtSMSAdminActions

        assert CourtSMSAdminActions is not None

    def test_court_sms_admin_base_import(self):
        from apps.automation.admin.sms.court_sms_admin_base import CourtSMSAdminBase

        assert CourtSMSAdminBase is not None

    def test_court_sms_admin_import(self):
        from apps.automation.admin.sms.court_sms_admin import CourtSMSAdmin

        assert CourtSMSAdmin is not None


# --- management commands ---

class TestManagementCommands:
    def test_smoke_check_import(self):
        from apps.automation.management.commands.smoke_check import Command

        assert Command is not None

    def test_recover_court_sms_tasks_import(self):
        from apps.automation.management.commands.recover_court_sms_tasks import Command as RecoverCommand

        assert RecoverCommand is not None


# --- scraping_tasks ---

class TestScrapingTasks:
    def test_import(self):
        from apps.automation.tasks.scraping_tasks import execute_scraper_task

        assert execute_scraper_task is not None

    def test_check_stuck_tasks_import(self):
        from apps.automation.tasks.scraping_tasks import check_stuck_tasks

        assert check_stuck_tasks is not None

    def test_startup_check_import(self):
        from apps.automation.tasks.scraping_tasks import startup_check

        assert startup_check is not None


# --- court_guarantee_api ---

class TestCourtGuaranteeApi:
    def test_import(self):
        from plugins.court_automation.guarantee.api_endpoint import router

        assert router is not None

    def test_check_plugin_import(self):
        from plugins.court_automation.guarantee.api_endpoint import _check_plugin

        assert callable(_check_plugin)
