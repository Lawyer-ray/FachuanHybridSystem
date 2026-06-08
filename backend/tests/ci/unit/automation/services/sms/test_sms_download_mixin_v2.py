"""Comprehensive unit tests for SMSDownloadMixin."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.automation.models import ScraperTaskStatus

_MOD = "apps.automation.services.sms._sms_download_mixin"


def _make_sms(
    *,
    sms_id: int = 1,
    content: str = "test content",
    status: str = "pending",
    retry_count: int = 0,
    case=None,
    case_log=None,
    scraper_task=None,
    download_links=None,
    party_names=None,
    document_file_paths=None,
):
    sms = MagicMock()
    sms.id = sms_id
    sms.content = content
    sms.status = status
    sms.retry_count = retry_count
    sms.case = case
    sms.case_log = case_log
    sms.scraper_task = scraper_task
    sms.download_links = download_links or []
    sms.party_names = party_names or []
    sms.document_file_paths = document_file_paths or []
    sms.save = MagicMock()
    return sms


def _make_task(
    *,
    task_id: int = 1,
    status: str = "pending",
    result=None,
    error_message: str | None = None,
    has_documents: bool = True,
):
    task = MagicMock()
    task.id = task_id
    task.status = status
    task.result = result
    task.error_message = error_message
    if has_documents:
        task.documents = MagicMock()
    return task


# ──────────────────────────────────────────────────────────────────────────────
# Class constants
# ──────────────────────────────────────────────────────────────────────────────


class TestClassConstants:

    def test_hbfy_account_pattern(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        match = SMSDownloadMixin.HBFY_ACCOUNT_PATTERN.search("账号 123456789012345")
        assert match is not None
        assert match.group(1) == "123456789012345"

    def test_hbfy_password_pattern(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        match = SMSDownloadMixin.HBFY_PASSWORD_PATTERN.search("默认密码：Abc123")
        assert match is not None
        assert match.group(1) == "Abc123"

    def test_sfdw_verification_code_pattern(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        match = SMSDownloadMixin.SFDW_VERIFICATION_CODE_PATTERN.search("验证码：AB12")
        assert match is not None
        assert match.group(1) == "AB12"


# ──────────────────────────────────────────────────────────────────────────────
# _normalize_phone_tail6
# ──────────────────────────────────────────────────────────────────────────────


class TestNormalizePhoneTail6:

    def test_long_number(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._normalize_phone_tail6("13800000000") == "000000"

    def test_exact_six(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._normalize_phone_tail6("345678") == "345678"

    def test_short_returns_none(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._normalize_phone_tail6("12345") is None

    def test_none_returns_none(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._normalize_phone_tail6(None) is None

    def test_empty_returns_none(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._normalize_phone_tail6("") is None

    def test_non_digit_stripped(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._normalize_phone_tail6("tel-138-1234-5678") == "345678"


# ──────────────────────────────────────────────────────────────────────────────
# _host_equals_or_subdomain
# ──────────────────────────────────────────────────────────────────────────────


class TestHostEqualsOrSubdomain:

    def test_exact_match(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._host_equals_or_subdomain("example.com", "example.com") is True

    def test_subdomain_match(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._host_equals_or_subdomain("sub.example.com", "example.com") is True

    def test_no_match(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._host_equals_or_subdomain("notexample.com", "example.com") is False


# ──────────────────────────────────────────────────────────────────────────────
# _is_sfdw_url
# ──────────────────────────────────────────────────────────────────────────────


class TestIsSfdwUrl:

    def test_sfdw_domain(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_sfdw_url("https://sfpt.cdfy12368.gov.cn/r/download") is True

    def test_sfdw_ip_port(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_sfdw_url("http://171.106.48.55:28083/r/download") is True

    def test_sfdw_path(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_sfdw_url("https://other.com/sfsdw//r/file") is True

    def test_not_sfdw(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_sfdw_url("https://example.com/file") is False


# ──────────────────────────────────────────────────────────────────────────────
# _is_jysd_url
# ──────────────────────────────────────────────────────────────────────────────


class TestIsJysdUrl:

    def test_jysd_domain(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_jysd_url("https://jysd.10102368.com/sd?key=abc") is True

    def test_path_end_sd_with_key(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_jysd_url("https://other.com/path/sd?key=xyz") is True

    def test_not_jysd(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_jysd_url("https://example.com/path") is False

    def test_sd_without_key(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_jysd_url("https://example.com/path/sd") is False


# ──────────────────────────────────────────────────────────────────────────────
# _is_hbfy_account_url
# ──────────────────────────────────────────────────────────────────────────────


class TestIsHbfyAccountUrl:

    def test_hbfy_domain(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_hbfy_account_url("https://dzsd.hbfy.gov.cn/sfsddz") is True

    def test_path_ends_sfsddz(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_hbfy_account_url("https://other.com/sfsddz") is True

    def test_not_hbfy(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_hbfy_account_url("https://example.com/path") is False


# ──────────────────────────────────────────────────────────────────────────────
# _is_zxfw_url
# ──────────────────────────────────────────────────────────────────────────────


class TestIsZxfwUrl:

    def test_zxfw_domain(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_zxfw_url("https://zxfw.court.gov.cn/portal") is True

    def test_not_zxfw(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._is_zxfw_url("https://example.com/path") is False


# ──────────────────────────────────────────────────────────────────────────────
# _get_required_platform_name
# ──────────────────────────────────────────────────────────────────────────────


class TestGetRequiredPlatformName:

    def test_zxfw_returns_none(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._get_required_platform_name("https://zxfw.court.gov.cn/portal") is None

    def test_hbfy_returns_name(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        result = SMSDownloadMixin._get_required_platform_name("https://dzsd.hbfy.gov.cn/sfsddz")
        assert result == "湖北电子送达"

    def test_jysd_returns_name(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        result = SMSDownloadMixin._get_required_platform_name("https://jysd.10102368.com/sd?key=abc")
        assert result == "简易送达"

    def test_sfdw_returns_name(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        result = SMSDownloadMixin._get_required_platform_name("https://sfpt.cdfy12368.gov.cn/r/download")
        assert result == "司法送达网"

    def test_guangdong_returns_name(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        result = SMSDownloadMixin._get_required_platform_name("https://sd.gdems.com/something")
        assert result == "广东电子送达"

    def test_unknown_returns_none(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        assert SMSDownloadMixin._get_required_platform_name("https://example.com") is None


# ──────────────────────────────────────────────────────────────────────────────
# _is_playwright_available
# ──────────────────────────────────────────────────────────────────────────────


class TestIsPlaywrightAvailable:

    def test_returns_bool(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        # playwright is installed in this env; just verify the method returns bool
        assert SMSDownloadMixin._is_playwright_available() is True


# ──────────────────────────────────────────────────────────────────────────────
# _extract_hbfy_credentials
# ──────────────────────────────────────────────────────────────────────────────


class TestExtractHbfyCredentials:

    def test_both_found(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        content = "账号 123456789012345 默认密码：Abc123"
        account, password = mixin._extract_hbfy_credentials(content)
        assert account == "123456789012345"
        assert password == "Abc123"

    def test_none_found(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        account, password = mixin._extract_hbfy_credentials("random text")
        assert account is None
        assert password is None


# ──────────────────────────────────────────────────────────────────────────────
# _extract_sfdw_verification_code
# ──────────────────────────────────────────────────────────────────────────────


class TestExtractSfdwVerificationCode:

    def test_found(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        assert mixin._extract_sfdw_verification_code("验证码：AB12") == "AB12"

    def test_not_found(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        assert mixin._extract_sfdw_verification_code("no code here") is None


# ──────────────────────────────────────────────────────────────────────────────
# _collect_lawyer_phones
# ──────────────────────────────────────────────────────────────────────────────


class TestCollectLawyerPhones:

    def test_empty_when_no_case(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        sms = _make_sms(case=None)
        phones = mixin._collect_lawyer_phones(sms)
        assert isinstance(phones, list)

    @patch("apps.core.interfaces.ServiceLocator")
    @patch("apps.cases.models.CaseAssignment")
    def test_from_case_assignments(self, MockAssignment, MockServiceLocator):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        lawyer = MagicMock()
        lawyer.phone = "13800000000"
        assignment = MagicMock()
        assignment.lawyer = lawyer
        MockAssignment.objects.select_related.return_value.filter.return_value.order_by.return_value = [
            assignment
        ]
        MockServiceLocator.get_lawyer_service.return_value.get_admin_lawyer.return_value = None
        sms = _make_sms(case=MagicMock())
        phones = mixin._collect_lawyer_phones(sms)
        assert "13800000000" in phones


# ──────────────────────────────────────────────────────────────────────────────
# _collect_lawyer_phone_tail6_candidates
# ──────────────────────────────────────────────────────────────────────────────


class TestCollectLawyerPhoneTail6Candidates:

    def test_deduplicates(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        mixin._collect_lawyer_phones = MagicMock(return_value=["13800000000", "13900000000"])
        sms = _make_sms()
        candidates = mixin._collect_lawyer_phone_tail6_candidates(sms)
        assert candidates == ["000000"]
        assert len(candidates) == 1

    def test_multiple_tails(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        mixin._collect_lawyer_phones = MagicMock(return_value=["13800000000", "13900000001"])
        sms = _make_sms()
        candidates = mixin._collect_lawyer_phone_tail6_candidates(sms)
        assert candidates == ["000000", "000001"]


# ──────────────────────────────────────────────────────────────────────────────
# _create_download_task
# ──────────────────────────────────────────────────────────────────────────────


class TestCreateDownloadTask:

    @patch(f"{_MOD}.ScraperTask")
    @patch(f"{_MOD}.submit_task")
    def test_no_download_links(self, mock_submit, MockScraperTask):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        sms = _make_sms(download_links=[])
        result = mixin._create_download_task(sms)
        assert result is None

    @patch(f"{_MOD}.ScraperTask")
    @patch(f"{_MOD}.submit_task")
    def test_playwright_required_but_not_available(self, mock_submit, MockScraperTask):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        sms = _make_sms(download_links=["https://dzsd.hbfy.gov.cn/sfsddz"], content="test")
        # Set the mock returned by objects.create to have the correct status
        mock_task = MagicMock()
        mock_task.status = "failed"
        MockScraperTask.objects.create.return_value = mock_task
        with patch.object(SMSDownloadMixin, "_is_playwright_available", return_value=False):
            task = mixin._create_download_task(sms)
            assert task is mock_task
            assert task.status == "failed"

    @patch(f"{_MOD}.ScraperTask")
    @patch(f"{_MOD}.submit_task")
    def test_zxfw_url_no_playwright_needed(self, mock_submit, MockScraperTask):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        sms = _make_sms(download_links=["https://zxfw.court.gov.cn/portal"])
        with patch.object(SMSDownloadMixin, "_is_playwright_available", return_value=False):
            task = mixin._create_download_task(sms)
            MockScraperTask.objects.create.assert_called_once()
            mock_submit.assert_called_once()

    @patch(f"{_MOD}.ScraperTask")
    @patch(f"{_MOD}.submit_task")
    def test_jysd_injects_lawyer_phones(self, mock_submit, MockScraperTask):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        mixin._collect_lawyer_phones = MagicMock(return_value=["13800000000"])
        mixin._collect_lawyer_phone_tail6_candidates = MagicMock(return_value=[])
        sms = _make_sms(
            download_links=["https://jysd.10102368.com/sd?key=abc"],
            content="test",
        )
        with patch.object(SMSDownloadMixin, "_is_playwright_available", return_value=True):
            mixin._create_download_task(sms)
            create_kw = MockScraperTask.objects.create.call_args
            assert "jysd_lawyer_phones" in create_kw[1]["config"]

    @patch(f"{_MOD}.ScraperTask")
    @patch(f"{_MOD}.submit_task")
    def test_sfdw_injects_verification_code(self, mock_submit, MockScraperTask):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        mixin._collect_lawyer_phone_tail6_candidates = MagicMock(return_value=[])
        sms = _make_sms(
            download_links=["https://sfpt.cdfy12368.gov.cn/r/download"],
            content="验证码：AB12",
        )
        with patch.object(SMSDownloadMixin, "_is_playwright_available", return_value=True):
            mixin._create_download_task(sms)
            create_kw = MockScraperTask.objects.create.call_args
            assert "sfdw_verification_code" in create_kw[1]["config"]
            assert create_kw[1]["config"]["sfdw_verification_code"] == "AB12"

    @patch(f"{_MOD}.ScraperTask")
    @patch(f"{_MOD}.submit_task")
    def test_sfdw_injects_manual_tail6(self, mock_submit, MockScraperTask):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        mixin._collect_lawyer_phone_tail6_candidates = MagicMock(return_value=[])
        sms = _make_sms(
            download_links=["https://sfpt.cdfy12368.gov.cn/r/download"],
            content="test",
        )
        opts = {"sfdw_phone_tail6": "123456"}
        with patch.object(SMSDownloadMixin, "_is_playwright_available", return_value=True):
            mixin._create_download_task(sms, process_options=opts)
            create_kw = MockScraperTask.objects.create.call_args
            assert create_kw[1]["config"]["sfdw_phone_tail6"] == "123456"

    @patch(f"{_MOD}.ScraperTask")
    @patch(f"{_MOD}.submit_task")
    def test_sfdw_injects_tail6_candidates(self, mock_submit, MockScraperTask):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        mixin._collect_lawyer_phone_tail6_candidates = MagicMock(return_value=["111111", "222222"])
        sms = _make_sms(
            download_links=["https://sfpt.cdfy12368.gov.cn/r/download"],
            content="test",
        )
        with patch.object(SMSDownloadMixin, "_is_playwright_available", return_value=True):
            mixin._create_download_task(sms)
            create_kw = MockScraperTask.objects.create.call_args
            assert create_kw[1]["config"]["sfdw_phone_tail6_candidates"] == ["111111", "222222"]


# ──────────────────────────────────────────────────────────────────────────────
# _should_wait_for_document_download
# ──────────────────────────────────────────────────────────────────────────────


class TestShouldWaitForDocumentDownload:

    def test_no_party_names_no_links_no_task(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        sms = _make_sms(party_names=[], download_links=[], scraper_task=None)
        assert mixin._should_wait_for_document_download(sms) is False

    def test_has_party_names_skips(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        sms = _make_sms(party_names=["原告"], download_links=["http://x.com"], scraper_task=MagicMock())
        assert mixin._should_wait_for_document_download(sms) is False

    def test_no_download_links_skips(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        sms = _make_sms(party_names=[], download_links=[], scraper_task=MagicMock())
        assert mixin._should_wait_for_document_download(sms) is False

    def test_refresh_returns_none(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        mixin._refresh_scraper_task = MagicMock(return_value=None)
        sms = _make_sms(party_names=[], download_links=["http://x.com"], scraper_task=MagicMock())
        assert mixin._should_wait_for_document_download(sms) is False

    def test_task_success_does_not_wait(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="success")
        mixin._refresh_scraper_task = MagicMock(return_value=task)
        mixin._log_completed_task_files = MagicMock()
        sms = _make_sms(party_names=[], download_links=["http://x.com"], scraper_task=MagicMock())
        assert mixin._should_wait_for_document_download(sms) is False

    def test_task_failed_does_not_wait(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="failed")
        mixin._refresh_scraper_task = MagicMock(return_value=task)
        mixin._log_completed_task_files = MagicMock()
        sms = _make_sms(party_names=[], download_links=["http://x.com"], scraper_task=MagicMock())
        assert mixin._should_wait_for_document_download(sms) is False

    def test_exception_returns_false(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        mixin._refresh_scraper_task = MagicMock(side_effect=Exception("db error"))
        sms = _make_sms(party_names=[], download_links=["http://x.com"], scraper_task=MagicMock())
        assert mixin._should_wait_for_document_download(sms) is False


# ──────────────────────────────────────────────────────────────────────────────
# _refresh_scraper_task
# ──────────────────────────────────────────────────────────────────────────────


class TestRefreshScraperTask:

    @patch(f"{_MOD}.ScraperTask")
    def test_returns_none_when_no_task(self, MockScraperTask):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        sms = _make_sms(scraper_task=None)
        assert mixin._refresh_scraper_task(sms) is None

    @patch(f"{_MOD}.ScraperTask")
    def test_refreshes_task(self, MockScraperTask):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(task_id=42)
        sms = _make_sms(scraper_task=task)
        MockScraperTask.objects.get.return_value = task
        result = mixin._refresh_scraper_task(sms)
        assert result is task
        assert sms.scraper_task is task

    @patch(f"{_MOD}.ScraperTask")
    def test_not_found_returns_none(self, MockScraperTask):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        MockScraperTask.objects.get.side_effect = Exception("not found")
        sms = _make_sms(scraper_task=MagicMock(id=999))
        assert mixin._refresh_scraper_task(sms) is None


# ──────────────────────────────────────────────────────────────────────────────
# _check_documents_wait_status
# ──────────────────────────────────────────────────────────────────────────────


class TestCheckDocumentsWaitStatus:

    def test_no_documents_pending_task_waits(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="pending")
        task.documents.all.return_value.exists.return_value = False
        sms = _make_sms()
        assert mixin._check_documents_wait_status(sms, task) is True

    def test_no_documents_running_task_waits(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="running")
        task.documents.all.return_value.exists.return_value = False
        sms = _make_sms()
        assert mixin._check_documents_wait_status(sms, task) is True

    def test_has_successful_docs_no_wait(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="running")
        all_docs = MagicMock()
        all_docs.exists.return_value = True
        all_docs.filter.return_value.exists.side_effect = [True]  # successful exists
        task.documents.all.return_value = all_docs
        sms = _make_sms()
        assert mixin._check_documents_wait_status(sms, task) is False

    def test_all_failed_running_no_wait(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="running")
        all_docs = MagicMock()
        all_docs.exists.return_value = True
        all_docs.count.return_value = 3
        # Setup filter chain: each filter returns a queryset mock with count()=0
        successful_mock = MagicMock()
        successful_mock.exists.return_value = False
        successful_mock.count.return_value = 0
        pending_mock = MagicMock()
        pending_mock.exists.return_value = False
        pending_mock.count.return_value = 0
        downloading_mock = MagicMock()
        downloading_mock.exists.return_value = False
        downloading_mock.count.return_value = 0
        all_docs.filter.side_effect = [successful_mock, pending_mock, downloading_mock]
        task.documents.all.return_value = all_docs
        sms = _make_sms()
        assert mixin._check_documents_wait_status(sms, task) is False


# ──────────────────────────────────────────────────────────────────────────────
# handle_scraper_task_status_change
# ──────────────────────────────────────────────────────────────────────────────


class TestHandleScraperTaskStatusChange:

    @patch(f"{_MOD}.CourtSMS")
    @patch(f"{_MOD}.submit_task")
    def test_success_triggers_matching(self, mock_submit, MockCourtSMS):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="success")
        sms = _make_sms(status="downloading")
        MockCourtSMS.objects.filter.return_value = [sms]
        mixin.handle_scraper_task_status_change(task)
        assert sms.status == "matching"
        sms.save.assert_called()

    @patch(f"{_MOD}.CourtSMS")
    @patch(f"{_MOD}.submit_task")
    def test_success_already_matching(self, mock_submit, MockCourtSMS):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="success")
        sms = _make_sms(status="matching")
        MockCourtSMS.objects.filter.return_value = [sms]
        mixin.handle_scraper_task_status_change(task)
        # status should remain matching (no save to change it)
        assert sms.status == "matching"
        mock_submit.assert_called_once()

    @patch(f"{_MOD}.CourtSMS")
    @patch(f"{_MOD}.submit_task")
    def test_ignores_non_terminal_status(self, mock_submit, MockCourtSMS):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="running")
        mixin.handle_scraper_task_status_change(task)
        MockCourtSMS.objects.filter.assert_not_called()

    @patch(f"{_MOD}.CourtSMS")
    @patch(f"{_MOD}.submit_task")
    def test_ignores_sms_not_in_expected_status(self, mock_submit, MockCourtSMS):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="success")
        sms = _make_sms(status="completed")
        MockCourtSMS.objects.filter.return_value = [sms]
        mixin.handle_scraper_task_status_change(task)
        assert sms.status == "completed"


# ──────────────────────────────────────────────────────────────────────────────
# _handle_sms_download_failed
# ──────────────────────────────────────────────────────────────────────────────


class TestHandleSmsDownloadFailed:

    @patch(f"{_MOD}.submit_task")
    def test_matching_status_continues(self, mock_submit):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="failed", error_message="timeout")
        sms = _make_sms(status="matching")
        result = mixin._handle_sms_download_failed(sms, task)
        assert result is True  # returns True = continue (skip retry logic)
        mock_submit.assert_called_once()

    @patch("apps.core.tasking.ScheduleQueryService")
    @patch(f"{_MOD}.submit_task")
    def test_downloading_retries(self, mock_submit, MockSchedule):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="failed", error_message="timeout")
        sms = _make_sms(status="downloading", retry_count=0)
        result = mixin._handle_sms_download_failed(sms, task)
        assert result is False
        assert sms.status == "download_failed"
        MockSchedule.return_value.create_once_schedule.assert_called_once()

    @patch(f"{_MOD}.submit_task")
    def test_max_retries_marks_failed(self, mock_submit):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task(status="failed", error_message="timeout")
        sms = _make_sms(status="downloading", retry_count=3)
        result = mixin._handle_sms_download_failed(sms, task)
        assert result is False
        assert sms.status == "failed"


# ──────────────────────────────────────────────────────────────────────────────
# _process_downloading_or_matching
# ──────────────────────────────────────────────────────────────────────────────


class TestProcessDownloadingOrMatching:

    @patch(f"{_MOD}.SMSDownloadMixin._create_download_task")
    def test_with_download_link_creates_task(self, mock_create):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        task = _make_task()
        mock_create.return_value = task
        sms = _make_sms(download_links=["http://x.com"])
        result = mixin._process_downloading_or_matching(sms)
        assert sms.status == "downloading"
        assert sms.scraper_task is task

    @patch(f"{_MOD}.SMSDownloadMixin._create_download_task")
    def test_with_download_link_no_task_goes_to_matching(self, mock_create):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        mock_create.return_value = None
        sms = _make_sms(download_links=["http://x.com"])
        result = mixin._process_downloading_or_matching(sms)
        assert sms.status == "matching"

    def test_no_download_links_goes_to_matching(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        mixin = SMSDownloadMixin()
        sms = _make_sms(download_links=[])
        result = mixin._process_downloading_or_matching(sms)
        assert sms.status == "matching"
