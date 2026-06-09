"""Tests for fee_notice services, oa_filing, contract_review, and misc."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# fee_notice/services/extraction/extraction_service.py
# ============================================================

class TestFeeNoticeExtractionService:
    def _make_service(self):
        from apps.fee_notice.services.extraction.extraction_service import FeeNoticeExtractionService
        svc = FeeNoticeExtractionService.__new__(FeeNoticeExtractionService)
        svc._text_service = None
        svc._detector = None
        svc._extractor = None
        return svc

    def test_is_supported_format_pdf(self):
        svc = self._make_service()
        assert svc._is_supported_format("/tmp/test.pdf") is True

    def test_is_supported_format_docx(self):
        svc = self._make_service()
        assert svc._is_supported_format("/tmp/test.docx") is False

    def test_is_supported_format_uppercase(self):
        svc = self._make_service()
        assert svc._is_supported_format("/tmp/test.PDF") is True

    def test_extract_from_files_empty(self):
        svc = self._make_service()
        result = svc.extract_from_files([], debug=False)
        assert result.total_files == 0
        assert len(result.notices) == 0
        assert len(result.errors) == 0

    def test_extract_from_files_unsupported_format(self):
        svc = self._make_service()
        result = svc.extract_from_files(["/tmp/test.docx"], debug=False)
        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "UNSUPPORTED_FORMAT"

    def test_extract_from_files_nonexistent(self):
        svc = self._make_service()
        with patch("apps.fee_notice.services.extraction.extraction_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.suffix.lower.return_value = ".pdf"
            MockPath.return_value = mock_path
            # exists returns False
            mock_path.exists.return_value = False
            result = svc.extract_from_files(["/tmp/nonexistent.pdf"], debug=False)
            assert len(result.errors) == 1
            assert result.errors[0]["code"] == "FILE_NOT_FOUND"


# ============================================================
# fee_notice/services/comparison/check_service.py
# ============================================================

class TestFeeNoticeCheckService:
    def _make_service(self):
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService
        return FeeNoticeCheckService.__new__(FeeNoticeCheckService)

    def test_filter_fee_notice_files_matches_keyword(self):
        svc = self._make_service()
        paths = [
            "/tmp/交费通知书.pdf",
            "/tmp/判决书.pdf",
            "/tmp/缴费通知书2.pdf",
        ]
        result = svc._filter_fee_notice_files(paths)
        assert len(result) == 2

    def test_filter_fee_notice_files_non_pdf_skipped(self):
        svc = self._make_service()
        paths = ["/tmp/交费通知书.docx"]
        result = svc._filter_fee_notice_files(paths)
        assert len(result) == 0

    def test_check_fee_notices_no_case(self):
        svc = self._make_service()
        sms = MagicMock()
        sms.case = None
        from apps.fee_notice.services.comparison.check_service import FeeCheckResult
        result = svc.check_fee_notices(sms, [])
        assert result.has_fee_notice is False

    def test_check_fee_notices_no_files(self):
        svc = self._make_service()
        sms = MagicMock()
        sms.case = MagicMock()
        sms.id = 1
        from apps.fee_notice.services.comparison.check_service import FeeCheckResult
        result = svc.check_fee_notices(sms, [])
        assert result.has_fee_notice is False

    def test_format_feishu_message_no_items(self):
        svc = self._make_service()
        from apps.fee_notice.services.comparison.check_service import FeeCheckResult
        result = FeeCheckResult(has_fee_notice=False, items=[])
        assert svc.format_feishu_message(result) is None


class TestFeeCheckItem:
    def test_default_values(self):
        from apps.fee_notice.services.comparison.check_service import FeeCheckItem
        item = FeeCheckItem(file_name="test.pdf", file_path="/tmp/test.pdf")
        assert item.can_compare is True
        assert item.acceptance_fee_match is False
        assert item.extracted_acceptance_fee is None


# ============================================================
# oa_filing/tasks.py - session status checks
# ============================================================

class TestOaFilingTasks:
    def test_run_client_import_nonexistent_session(self):
        from apps.oa_filing.tasks import run_client_import_task
        with patch("apps.oa_filing.models.ClientImportSession") as MockSession:
            MockSession.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockSession.objects.select_related.return_value.get.side_effect = MockSession.DoesNotExist
            # Should not raise, just log error and return
            run_client_import_task(999)

    def test_run_case_import_preview_nonexistent(self):
        from apps.oa_filing.tasks import run_case_import_preview_task
        with patch("apps.oa_filing.models.CaseImportSession") as MockSession:
            MockSession.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockSession.objects.select_related.return_value.get.side_effect = MockSession.DoesNotExist
            run_case_import_preview_task(999, "/tmp/test.xlsx")


# ============================================================
# court_zxfw_filing/service.py - resolve_province_code
# ============================================================

class TestResolveProvinceCode:
    def test_exact_match(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.service import CourtZxfwFilingService
        assert CourtZxfwFilingService.resolve_province_code("广东省") == "440000"

    def test_fuzzy_match_guangxi(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.service import CourtZxfwFilingService
        assert CourtZxfwFilingService.resolve_province_code("广西") == "450000"

    def test_fuzzy_match_inner_mongolia(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.service import CourtZxfwFilingService
        assert CourtZxfwFilingService.resolve_province_code("内蒙古") == "150000"

    def test_unsupported_raises(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.service import CourtZxfwFilingService
        with pytest.raises(ValueError, match="不支持的省份"):
            CourtZxfwFilingService.resolve_province_code("火星省")

    def test_all_provinces_have_codes(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.service import CourtZxfwFilingService
        for name, code in CourtZxfwFilingService.PROVINCE_CODES.items():
            assert len(code) == 6, f"{name} code should be 6 digits"
            assert code.isdigit(), f"{name} code should be digits"


# ============================================================
# gsxt/gsxt_report_service.py
# ============================================================

class TestGsxtReportService:
    def test_gsxt_report_error(self):
        from apps.automation.services.gsxt.gsxt_report_service import GsxtReportError
        e = GsxtReportError("test error")
        assert str(e) == "test error"

    def test_gsxt_report_service_start_report_flow(self):
        from apps.automation.services.gsxt.gsxt_report_service import GsxtReportService
        svc = GsxtReportService()
        with patch("apps.automation.services.gsxt.gsxt_report_service.start_report_flow") as mock_start:
            svc.start_report_flow(42)
            mock_start.assert_called_once_with(42)


# ============================================================
# recover_court_sms_tasks.py
# ============================================================

class TestRecoverCourtSmsTasks:
    def test_recover_single_sms_pending(self):
        from apps.automation.management.commands.recover_court_sms_tasks import Command
        cmd = Command.__new__(Command)
        sms = MagicMock()
        sms.status = "pending"
        submit_fn = MagicMock()
        with patch("apps.automation.models.CourtSMSStatus") as MockStatus:
            MockStatus.PENDING = "pending"
            MockStatus.DOWNLOAD_FAILED = "download_failed"
            MockStatus.MATCHING = "matching"
            MockStatus.RENAMING = "renaming"
            MockStatus.NOTIFYING = "notifying"
            MockStatus.DOWNLOADING = "downloading"
            result = cmd._recover_single_sms(sms, submit_fn)
            assert result is True
            submit_fn.assert_called_once()


# ============================================================
# contract_review/services/format_normalizer/llm_helper.py
# ============================================================

class TestContractStructureAnalyzer:
    def test_cache_hit(self):
        from apps.contract_review.services.format_normalizer.llm_helper import ContractStructureAnalyzer
        analyzer = ContractStructureAnalyzer.__new__(ContractStructureAnalyzer)
        analyzer._cache = {}
        paragraphs = ["一、合同主体", "甲方：XXX"]
        expected = [{"level": 1}, {"level": 0}]
        analyzer._cache["|".join(paragraphs)] = expected
        result = analyzer.analyze_document(paragraphs)
        assert result is expected


# ============================================================
# smoke_check.py - smoke_q_task
# ============================================================

class TestSmokeQTask:
    def test_addition(self):
        from apps.automation.management.commands.smoke_check import smoke_q_task
        assert smoke_q_task(20, 22) == 42
        assert smoke_q_task(0, 0) == 0
        assert smoke_q_task(-1, 1) == 0
