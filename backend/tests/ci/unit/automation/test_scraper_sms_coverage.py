"""Coverage tests for automation.services.scraper and automation.services.sms."""

from unittest.mock import MagicMock, patch

import pytest


class TestSMSCaseBindingMixin:
    def test_filter_valid_case_numbers(self):
        from apps.automation.services.sms._sms_case_binding_mixin import SMSCaseBindingMixin

        class Concrete(SMSCaseBindingMixin):
            @property
            def case_service(self): return MagicMock()
            @property
            def lawyer_service(self): return MagicMock()

        obj = Concrete()
        numbers = ["(2024)浙01民初123号", "2024年1月15号", "普通案号"]
        result = obj._filter_valid_case_numbers(numbers)
        assert "(2024)浙01民初123号" in result
        assert "普通案号" in result

    def test_create_case_binding_no_case(self):
        from apps.automation.services.sms._sms_case_binding_mixin import SMSCaseBindingMixin

        class Concrete(SMSCaseBindingMixin):
            @property
            def case_service(self): return MagicMock()
            @property
            def lawyer_service(self): return MagicMock()

        obj = Concrete()
        sms = MagicMock()
        sms.case = None
        result = obj._create_case_binding(sms)
        assert result is False


class TestProgressReporter:
    def test_resolve_filing_engine_api(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.progress_reporter import ProgressReporterMixin

        result = ProgressReporterMixin._resolve_filing_engine({"filing_engine": "api"})
        assert result == "api"

    def test_resolve_filing_engine_playwright(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.progress_reporter import ProgressReporterMixin

        result = ProgressReporterMixin._resolve_filing_engine({"filing_engine": "playwright"})
        assert result == "playwright"

    def test_resolve_filing_engine_use_api_flag(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.progress_reporter import ProgressReporterMixin

        result = ProgressReporterMixin._resolve_filing_engine({"use_api_for_execution": True})
        assert result == "api"

    @patch.dict("sys.modules", {"plugins": None})
    def test_resolve_filing_engine_default(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.progress_reporter import ProgressReporterMixin

        result = ProgressReporterMixin._resolve_filing_engine({})
        assert result == "playwright"

    def test_allow_playwright_fallback_true(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.progress_reporter import ProgressReporterMixin

        assert ProgressReporterMixin._allow_playwright_fallback({}) is True

    def test_allow_playwright_fallback_false(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.progress_reporter import ProgressReporterMixin

        assert ProgressReporterMixin._allow_playwright_fallback({"playwright_fallback": False}) is False

    def test_allow_playwright_fallback_string(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.progress_reporter import ProgressReporterMixin

        assert ProgressReporterMixin._allow_playwright_fallback({"playwright_fallback": "false"}) is False


class TestDialogUIHelpers:
    def test_choose_party_type_defaults(self):
        from apps.automation.services.scraper.sites.guarantee.dialog_ui_helpers import GuaranteeDialogUIHelpersMixin

        # Just test class exists and has expected methods
        assert hasattr(GuaranteeDialogUIHelpersMixin, '_choose_party_type_in_dialog')
        assert hasattr(GuaranteeDialogUIHelpersMixin, '_click_add_button')
        assert hasattr(GuaranteeDialogUIHelpersMixin, '_wait_for_g_two_ready')
        assert hasattr(GuaranteeDialogUIHelpersMixin, '_clear_g_two_existing_data')


class TestGsxtEmailService:
    def test_decode_header_value_none(self):
        from apps.automation.services.gsxt.gsxt_email_service import _decode_header_value

        assert _decode_header_value(None) == ""

    def test_decode_header_value_plain(self):
        from apps.automation.services.gsxt.gsxt_email_service import _decode_header_value

        assert _decode_header_value("plain text") == "plain text"

    def test_fetch_report_attachment(self):
        from apps.automation.services.gsxt.gsxt_email_service import GsxtEmailService

        svc = GsxtEmailService()
        with patch("apps.automation.services.gsxt.gsxt_email_service._fetch_report_attachment", return_value=None):
            result = svc.fetch_report_attachment("user", "pass", "company")
            assert result is None


class TestGsxtReverseLogin:
    def test_rsa_encrypt(self):
        from apps.automation.services.gsxt.gsxt_reverse_login import rsa_encrypt

        result = rsa_encrypt("test")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_not_implemented_solver(self):
        from apps.automation.services.gsxt.gsxt_reverse_login import NotImplementedSolver

        solver = NotImplementedSolver()
        with pytest.raises(NotImplementedError):
            solver.solve_geetest_v4("id", "challenge")

    def test_set_captcha_solver(self):
        from apps.automation.services.gsxt.gsxt_reverse_login import set_captcha_solver, CaptchaSolver

        class MockSolver(CaptchaSolver):
            def solve_geetest_v4(self, captcha_id, challenge):
                return {"lot_number": "1", "captcha_output": "2", "pass_token": "3", "gen_time": "4"}

        set_captcha_solver(MockSolver())
        from apps.automation.services.gsxt.gsxt_reverse_login import _solver
        assert isinstance(_solver, MockSolver)
