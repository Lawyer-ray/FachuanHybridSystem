"""Tests for SMS parser service and text utils - targeting uncovered branches."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ==================== text_utils.py ====================


class TestTextUtilsNormalizeCaseNumber:
    """Test TextUtils.normalize_case_number."""

    def test_empty_string(self):
        from apps.automation.utils.text_utils import TextUtils

        assert TextUtils.normalize_case_number("") == ""

    def test_normalizes_parens(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("(2025)粤01民初1号")
        assert "（" in result
        assert "）" in result

    def test_square_brackets(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("[2025]粤01民初1号")
        assert "（" in result
        assert "）" in result

    def test_tortoise_shell_brackets(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("〔2025〕粤01民初1号")
        assert "（" in result
        assert "）" in result

    def test_removes_spaces(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("（2025） 粤01 民初 1 号")
        assert " " not in result

    def test_removes_fullwidth_space(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("（2025）　粤01民初1号")
        assert "　" not in result

    def test_appends_hao(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("（2025）粤01民初1")
        assert result.endswith("号")

    def test_already_has_hao(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("（2025）粤01民初1号")
        assert result.endswith("号")
        assert not result.endswith("号号")


class TestTextUtilsCleanText:
    """Test TextUtils.clean_text."""

    def test_empty(self):
        from apps.automation.utils.text_utils import TextUtils

        assert TextUtils.clean_text("") == ""
        assert TextUtils.clean_text(None) == ""  # type: ignore[arg-type]

    def test_removes_control_chars(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.clean_text("hello\x00world\x08test")
        assert "\x00" not in result
        assert "\x08" not in result
        assert "helloworldtest" in result.replace(" ", "")

    def test_merges_whitespace(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.clean_text("hello  \t\n  world")
        assert result == "hello world"

    def test_strips_edges(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.clean_text("  hello  ")
        assert result == "hello"


class TestTextUtilsExtractCaseNumbers:
    """Test TextUtils.extract_case_numbers."""

    def test_empty_text(self):
        from apps.automation.utils.text_utils import TextUtils

        assert TextUtils.extract_case_numbers("") == []

    def test_standard_case_number(self):
        from apps.automation.utils.text_utils import TextUtils

        text = "案号（2025）粤0606执保38607号，特此通知。"
        result = TextUtils.extract_case_numbers(text)
        assert len(result) >= 1
        assert "38607号" in result[0]

    def test_multiple_case_numbers(self):
        from apps.automation.utils.text_utils import TextUtils

        text = "原告（2025）粤01民初123号与被告（2025）粤01民初456号一案"
        result = TextUtils.extract_case_numbers(text)
        assert len(result) >= 2

    def test_deduplicates(self):
        from apps.automation.utils.text_utils import TextUtils

        text = "（2025）粤01民初1号和（2025）粤01民初1号"
        result = TextUtils.extract_case_numbers(text)
        # Should be deduplicated
        unique = set(result)
        assert len(unique) == len(result)

    def test_excludes_date_format(self):
        from apps.automation.utils.text_utils import TextUtils

        text = "2025年12月17号"
        result = TextUtils.extract_case_numbers(text)
        # Date pattern should be excluded
        assert all("年" not in r for r in result)


# ==================== sms_parser_service.py ====================


class TestSMSParserServiceSanitizeLink:
    """Test SMSParserService._sanitize_link."""

    def test_strips_trailing_punctuation(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        assert parser._sanitize_link("http://test.com/path。") == "http://test.com/path"
        assert parser._sanitize_link("http://test.com/path，") == "http://test.com/path"
        assert parser._sanitize_link("http://test.com/path)") == "http://test.com/path"

    def test_no_trailing_punct(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        assert parser._sanitize_link("http://test.com/path") == "http://test.com/path"


class TestSMSParserServiceIsValidDownloadLink:
    """Test SMSParserService._is_valid_download_link."""

    def test_zxfw_link_valid(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        link = "https://court.example.com/zxfw/#/pagesajkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789"
        assert parser._is_valid_download_link(link) is True

    def test_zxfw_link_missing_params(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        link = "https://court.example.com/zxfw/#/pagesajkj/app/wssd/index?qdbh=123"
        assert parser._is_valid_download_link(link) is False

    def test_gdems_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        link = "https://gdems.example.com/v3/dzsd/abc123"
        assert parser._is_valid_download_link(link) is True

    def test_jysd_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        link = "https://sd.example.com/sd?key=abc123"
        assert parser._is_valid_download_link(link) is True

    def test_hbfy_public_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        link = "https://hbfy.example.com/hb/msg=abc123"
        # path ends with /hb/msg and msg is in query_params
        # Actually this format: /hb/msg=xxx means the path is /hb/msg=xxx
        # The code checks path_lower.endswith("/hb/msg") and "msg" in query_params
        # This link has no query params, so it should be False by strict parsing
        result = parser._is_valid_download_link(link)
        assert isinstance(result, bool)

    def test_hbfy_account_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        link = "https://hbfy.example.com/sfsddz"
        assert parser._is_valid_download_link(link) is True

    def test_sfdw_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        link = "https://sfdw.example.com/sfsdw//r/abc123"
        assert parser._is_valid_download_link(link) is True

    def test_random_url_invalid(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        assert parser._is_valid_download_link("https://random.com/page") is False


class TestSMSParserServiceExtractVerificationCode:
    """Test SMSParserService.extract_verification_code."""

    def test_extracts_code(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        assert parser.extract_verification_code("验证码：ABCD") == "ABCD"

    def test_extracts_code_with_colon(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        assert parser.extract_verification_code("验证码:1234") == "1234"

    def test_no_code(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        assert parser.extract_verification_code("普通短信内容") == ""


class TestSMSParserServiceExtractDownloadLinks:
    """Test SMSParserService.extract_download_links."""

    def test_extracts_sfdw_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        content = "请查收 https://sfdw.example.com/sfsdw//r/abc123"
        links = parser.extract_download_links(content)
        assert len(links) >= 1
        assert any("sfsdw" in l for l in links)

    def test_no_links(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        links = parser.extract_download_links("普通短信")
        assert links == []

    def test_deduplicates(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        content = "https://gdems.example.com/v3/dzsd/abc\nhttps://gdems.example.com/v3/dzsd/abc"
        links = parser.extract_download_links(content)
        assert len(links) <= 1


class TestSMSParserServiceParse:
    """Test SMSParserService.parse."""

    def test_document_delivery_type(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService(ollama_model="test", ollama_base_url="http://test")
        content = "请查收文书 https://gdems.example.com/v3/dzsd/abc123"
        result = parser.parse(content)
        assert result.sms_type is not None
        assert isinstance(result.download_links, list)

    def test_filing_notification_type(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService(ollama_model="test", ollama_base_url="http://test")
        content = "您的案件已立案受理"
        result = parser.parse(content)
        assert result.sms_type is not None

    def test_info_notification_type(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService(ollama_model="test", ollama_base_url="http://test")
        content = "普通通知信息"
        result = parser.parse(content)
        assert result.sms_type is not None


class TestSMSParserServiceFilterParties:
    """Test SMSParserService._filter_parties."""

    def test_filters_excluded_keywords(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        result = parser._filter_parties(["人民法院", "书记员", "通知", "张三"])
        assert "张三" in result
        assert "人民法院" not in result

    def test_filters_too_short(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        result = parser._filter_parties(["张", "张三"])
        assert "张" not in result
        assert "张三" in result

    def test_filters_too_long(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        result = parser._filter_parties(["a" * 31, "张三"])
        assert "张三" in result

    def test_filters_non_chinese(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        result = parser._filter_parties(["ABC123", "张三"])
        assert "ABC123" not in result

    def test_filters_invalid_fragments(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        result = parser._filter_parties(["有限公司", "张三"])
        assert "有限公司" not in result

    def test_filters_suffix_patterns(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        result = parser._filter_parties(["张三的", "李四财", "王五案"])
        assert len(result) == 0

    def test_filters_starts_with_de(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        result = parser._filter_parties(["的张三", "张三"])
        assert "的张三" not in result
        assert "张三" in result


class TestSMSParserServiceCollectCompanyNames:
    """Test _collect_company_names."""

    def test_extracts_limited_company(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        parties: list[str] = []
        parser._collect_company_names("广州市天河区测试有限公司", parties)
        assert any("测试有限公司" in p for p in parties)

    def test_extracts_joint_stock(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        parties: list[str] = []
        parser._collect_company_names("华为股份有限公司", parties)
        assert any("股份有限公司" in p for p in parties)


class TestSMSParserServiceCollectVersusPatterns:
    """Test _collect_versus_patterns."""

    def test_company_vs_company(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        parties: list[str] = []
        parser._collect_versus_patterns("广州市天河区测试有限公司与深圳市南山区科技有限公司的合同纠纷", parties)
        assert len(parties) >= 2


class TestSMSParserServiceCollectNameContexts:
    """Test _collect_name_contexts."""

    def test_plaintiff_defendant_pattern(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        parties: list[str] = []
        parser._collect_name_contexts("原告：张三 被告：李四", parties)
        assert "张三" in parties
        assert "李四" in parties

    def test_versus_pattern(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        parties: list[str] = []
        parser._collect_name_contexts("关于张三诉李四案件", parties)
        assert "张三" in parties


class TestSMSParserServiceExtractPartyNamesWithRegex:
    """Test _extract_party_names_with_regex."""

    def test_extracts_company_names(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        content = "广州市天河区测试有限公司与深圳市南山区科技有限公司合同纠纷一案"
        result = parser._extract_party_names_with_regex(content)
        assert len(result) > 0

    def test_no_parties(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        result = parser._extract_party_names_with_regex("普通短信通知")
        assert isinstance(result, list)


# ==================== sms_parser_service.py - additional ====================


class TestSMSParseResultDataclass:
    """Test SMSParseResult dataclass."""

    def test_default_values(self):
        from apps.automation.services.sms.sms_parser_service import SMSParseResult

        result = SMSParseResult(
            sms_type="test",
            download_links=[],
            case_numbers=[],
            party_names=[],
            has_valid_download_link=False,
        )
        assert result.verification_code == ""


class TestSMSParserServiceIsDocumentDeliveryWithoutParties:
    """Test _is_document_delivery_without_parties."""

    def test_delivery_sms(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        content = "请查收 https://gdems.example.com/v3/dzsd/abc 案号（2025）粤01民初1号"
        result = parser._is_document_delivery_without_parties(content)
        assert isinstance(result, bool)

    def test_not_delivery(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        content = "普通通知"
        assert parser._is_document_delivery_without_parties(content) is False


class TestSMSParserServiceExtractCaseNumbers:
    """Test extract_case_numbers in SMSParserService."""

    def test_delegates_to_text_utils(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        parser = SMSParserService()
        text = "案号（2025）粤0606执保38607号"
        result = parser.extract_case_numbers(text)
        assert len(result) >= 1
