"""Comprehensive tests for automation.services.sms.sms_parser_service.

Covers: parse, extract_download_links, _sanitize_link, _is_valid_download_link,
extract_verification_code, extract_case_numbers, extract_party_names,
_find_existing_clients_in_sms,
lazy-loaded properties.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from apps.automation.models import CourtSMSType
from apps.automation.services.sms.sms_parser_service import SMSParseResult, SMSParserService


class TestSMSParseResult:
    """Test the SMSParseResult dataclass."""

    def test_basic_creation(self):
        result = SMSParseResult(
            sms_type=CourtSMSType.DOCUMENT_DELIVERY,
            download_links=["http://example.com"],
            case_numbers=["(2025)粤01民初1号"],
            party_names=["张三"],
            has_valid_download_link=True,
            verification_code="1234",
        )
        assert result.sms_type == CourtSMSType.DOCUMENT_DELIVERY
        assert len(result.download_links) == 1
        assert result.verification_code == "1234"

    def test_default_verification_code(self):
        result = SMSParseResult(
            sms_type="info",
            download_links=[],
            case_numbers=[],
            party_names=[],
            has_valid_download_link=False,
        )
        assert result.verification_code == ""


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------


class TestExtractDownloadLinks:
    def setup_method(self):
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_zxfw_link(self):
        content = "请查收 https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=abc"
        links = self.service.extract_download_links(content)
        assert len(links) == 1

    def test_gdems_link(self):
        content = "请查收 https://sd.gdcourts.gov.cn/v3/dzsd/ABC123"
        links = self.service.extract_download_links(content)
        assert len(links) == 1

    def test_jysd_link(self):
        content = "请查收 https://sd.court.gov.cn/sd?key=abc123_def"
        links = self.service.extract_download_links(content)
        assert len(links) == 1

    def test_hbfy_public_link(self):
        content = "请查收 https://hbfy.court.gov.cn/hb/msg?msg=ABC123"
        links = self.service.extract_download_links(content)
        assert len(links) == 1

    def test_hbfy_account_link(self):
        content = "请登录 https://hbfy.court.gov.cn/sfsddz 查收"
        links = self.service.extract_download_links(content)
        assert len(links) == 1

    def test_sfdw_link(self):
        content = "请查收 https://sfsdw.court.gov.cn/sfsdw//r/ABC123"
        links = self.service.extract_download_links(content)
        assert len(links) == 1

    def test_no_valid_link(self):
        links = self.service.extract_download_links("这是一条普通短信")
        assert links == []

    def test_dedup(self):
        link = "https://sd.court.gov.cn/sd?key=abc123"
        content = f"链接1: {link} 链接2: {link}"
        links = self.service.extract_download_links(content)
        assert len(links) == 1

    def test_trailing_punctuation_stripped(self):
        content = "请查收 https://sd.gdcourts.gov.cn/v3/dzsd/ABC123。"
        links = self.service.extract_download_links(content)
        assert len(links) == 1
        assert not links[0].endswith("。")

    def test_zxfw_case_insensitive(self):
        """URL with uppercase path components should still match."""
        content = "https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=1&sdbh=2&sdsin=3"
        links = self.service.extract_download_links(content)
        assert len(links) == 1


# ---------------------------------------------------------------------------
# _sanitize_link
# ---------------------------------------------------------------------------


class TestSanitizeLink:
    def setup_method(self):
        self.service = SMSParserService()

    def test_strips_trailing_period(self):
        assert self.service._sanitize_link("https://example.com.") == "https://example.com"

    def test_strips_trailing_comma(self):
        assert self.service._sanitize_link("https://example.com,") == "https://example.com"

    def test_strips_chinese_punctuation(self):
        assert self.service._sanitize_link("https://example.com。") == "https://example.com"

    def test_no_trailing(self):
        assert self.service._sanitize_link("https://example.com") == "https://example.com"

    def test_empty(self):
        assert self.service._sanitize_link("") == ""

    def test_none(self):
        assert self.service._sanitize_link(None) == ""


# ---------------------------------------------------------------------------
# _is_valid_download_link
# ---------------------------------------------------------------------------


class TestIsValidDownloadLink:
    def setup_method(self):
        self.service = SMSParserService()

    def test_zxfw_valid(self):
        link = "https://court.gov.cn/zxfw/#/pagesajkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=abc"
        assert self.service._is_valid_download_link(link) is True

    def test_zxfw_missing_params(self):
        link = "https://court.gov.cn/zxfw/#/pagesajkj/app/wssd/index?qdbh=123"
        assert self.service._is_valid_download_link(link) is False

    def test_gdems_valid(self):
        assert self.service._is_valid_download_link("https://sd.gov.cn/v3/dzsd/ABC") is True

    def test_jysd_valid(self):
        assert self.service._is_valid_download_link("https://sd.gov.cn/sd?key=abc") is True

    def test_hbfy_msg_valid(self):
        assert self.service._is_valid_download_link("https://hb.gov.cn/hb/msg?msg=ABC") is True

    def test_hbfy_sfsddz_valid(self):
        assert self.service._is_valid_download_link("https://hb.gov.cn/sfsddz") is True

    def test_sfdw_valid(self):
        assert self.service._is_valid_download_link("https://sfsdw.gov.cn/sfsdw//r/ABC") is True

    def test_unknown_url(self):
        assert self.service._is_valid_download_link("https://random.com/page") is False


# ---------------------------------------------------------------------------
# extract_verification_code
# ---------------------------------------------------------------------------


class TestExtractVerificationCode:
    def setup_method(self):
        self.service = SMSParserService()

    def test_found(self):
        content = "您的验证码：1234，请使用"
        assert self.service.extract_verification_code(content) == "1234"

    def test_found_with_colon(self):
        content = "验证码:ABCD"
        assert self.service.extract_verification_code(content) == "ABCD"

    def test_not_found(self):
        content = "没有验证码"
        assert self.service.extract_verification_code(content) == ""


# ---------------------------------------------------------------------------
# extract_case_numbers
# ---------------------------------------------------------------------------


class TestExtractCaseNumbers:
    def setup_method(self):
        self.service = SMSParserService()

    @patch("apps.automation.services.sms.sms_parser_service.TextUtils")
    def test_delegates_to_text_utils(self, mock_utils):
        mock_utils.extract_case_numbers.return_value = ["(2025)粤01民初1号"]
        result = self.service.extract_case_numbers("some content")
        assert result == ["(2025)粤01民初1号"]
        mock_utils.extract_case_numbers.assert_called_once_with("some content")

    @patch("apps.automation.services.sms.sms_parser_service.TextUtils")
    def test_empty(self, mock_utils):
        mock_utils.extract_case_numbers.return_value = []
        assert self.service.extract_case_numbers("no case") == []


# ---------------------------------------------------------------------------
# extract_party_names
# ---------------------------------------------------------------------------


class TestExtractPartyNames:
    def setup_method(self):
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_existing_clients_found(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=["张三", "李四"])
        result = self.service.extract_party_names("content")
        assert result == ["张三", "李四"]

    def test_no_existing_clients_fallback_to_matching(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.return_value = ["张三"]
        self.service._party_candidate_extractor = extractor

        matcher = MagicMock()
        client = MagicMock()
        client.name = "张三"
        matcher.extract_and_match_parties_from_sms.return_value = [client]
        self.service._party_matching_service = matcher

        result = self.service.extract_party_names("content")
        assert result == ["张三"]

    def test_no_candidates_returns_empty(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.return_value = []
        self.service._party_candidate_extractor = extractor
        result = self.service.extract_party_names("content")
        assert result == []

    def test_extractor_exception_returns_empty(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.side_effect = RuntimeError("boom")
        self.service._party_candidate_extractor = extractor
        result = self.service.extract_party_names("content")
        assert result == []

    def test_matcher_no_interface_returns_empty(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.return_value = ["张三"]
        self.service._party_candidate_extractor = extractor

        matcher = MagicMock(spec=[])  # no extract_and_match_parties_from_sms
        self.service._party_matching_service = matcher

        result = self.service.extract_party_names("content")
        assert result == []

    def test_matcher_exception_returns_empty(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.return_value = ["张三"]
        self.service._party_candidate_extractor = extractor

        matcher = MagicMock()
        matcher.extract_and_match_parties_from_sms.side_effect = RuntimeError("boom")
        self.service._party_matching_service = matcher

        result = self.service.extract_party_names("content")
        assert result == []

    def test_duplicate_client_names_deduped(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        extractor = MagicMock()
        extractor.extract.return_value = ["A"]
        self.service._party_candidate_extractor = extractor

        matcher = MagicMock()
        c1 = MagicMock()
        c1.name = "张三"
        c2 = MagicMock()
        c2.name = "张三"
        matcher.extract_and_match_parties_from_sms.return_value = [c1, c2]
        self.service._party_matching_service = matcher

        result = self.service.extract_party_names("content")
        assert result == ["张三"]


# ---------------------------------------------------------------------------
# _find_existing_clients_in_sms
# ---------------------------------------------------------------------------


class TestFindExistingClientsInSMS:
    def setup_method(self):
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_finds_clients(self):
        c1 = MagicMock()
        c1.name = "张三"
        c2 = MagicMock()
        c2.name = "李四"
        c3 = MagicMock()
        c3.name = "短"  # too short, skipped
        self.service._client_service.get_all_clients_internal.return_value = [c1, c2, c3]

        result = self.service._find_existing_clients_in_sms("张三和李四的案件")
        assert "张三" in result
        assert "李四" in result
        assert "短" not in result

    def test_no_match(self):
        c1 = MagicMock()
        c1.name = "王五"
        self.service._client_service.get_all_clients_internal.return_value = [c1]
        result = self.service._find_existing_clients_in_sms("张三的案件")
        assert result == []

    def test_exception_returns_empty(self):
        self.service._client_service.get_all_clients_internal.side_effect = RuntimeError("boom")
        result = self.service._find_existing_clients_in_sms("content")
        assert result == []


# ---------------------------------------------------------------------------
# parse (integration of all parts)
# ---------------------------------------------------------------------------


class TestParse:
    def setup_method(self):
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_filing_notification_type(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        content = "您的案件已立案，请注意查收"
        result = self.service.parse(content)
        assert result.sms_type == CourtSMSType.FILING_NOTIFICATION

    def test_info_notification_type(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        content = "这是一条普通信息"
        result = self.service.parse(content)
        assert result.sms_type == CourtSMSType.INFO_NOTIFICATION

    def test_with_verification_code(self):
        self.service._find_existing_clients_in_sms = MagicMock(return_value=[])
        content = "验证码：1234，https://sfsdw.gov.cn/sfsdw//r/ABC123"
        result = self.service.parse(content)
        assert result.verification_code == "1234"


# ---------------------------------------------------------------------------
# Lazy-loaded properties
# ---------------------------------------------------------------------------


class TestLazyProperties:
    def test_ollama_model_lazy(self):
        service = SMSParserService()
        service._ollama_model = None
        with patch("apps.core.llm.config.LLMConfig.get_ollama_model", return_value="my-model"):
            assert service.ollama_model == "my-model"
        # Second call should use cached value
        assert service.ollama_model == "my-model"

    def test_ollama_base_url_lazy(self):
        service = SMSParserService()
        service._ollama_base_url = None
        with patch("apps.core.llm.config.LLMConfig.get_ollama_base_url", return_value="http://localhost"):
            assert service.ollama_base_url == "http://localhost"

    def test_llm_service_lazy(self):
        service = SMSParserService()
        service._llm_service = None
        with patch("apps.core.interfaces.ServiceLocator.get_llm_service", return_value="llm"):
            assert service.llm_service == "llm"

    def test_client_service_lazy(self):
        service = SMSParserService()
        service._client_service = None
        with patch("apps.core.dependencies.automation_sms_wiring.build_sms_client_service", return_value="cs"):
            assert service.client_service == "cs"

    def test_party_matching_service_lazy(self):
        service = SMSParserService()
        service._party_matching_service = None
        with patch("apps.automation.services.sms.matching._get_party_matching_service", return_value="pms"):
            assert service.party_matching_service == "pms"

    def test_party_candidate_extractor_lazy(self):
        service = SMSParserService()
        service._party_candidate_extractor = None
        with patch("apps.automation.services.sms.parsing.PartyCandidateExtractor", return_value="pce"):
            assert service.party_candidate_extractor == "pce"
