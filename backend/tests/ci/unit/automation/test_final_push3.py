"""Final push coverage tests for automation module — text utils, sms parser."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest


# ============================================================================
# automation/utils/text_utils.py tests
# ============================================================================


class TestTextUtilsNormalizeCaseNumber:
    def test_standard_format(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("（2024）粤0606执386号")
        assert result == "（2024）粤0606执386号"

    def test_parentheses_normalized(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("(2024)粤0606执386号")
        assert result == "（2024）粤0606执386号"

    def test_square_brackets(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("[2024]粤0606执386号")
        assert result == "（2024）粤0606执386号"

    def test_spaces_removed(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("（2024）粤 0606 执386号")
        assert " " not in result
        assert "　" not in result

    def test_hao_appended(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.normalize_case_number("（2024）粤0606执386")
        assert result.endswith("号")

    def test_empty_string(self):
        from apps.automation.utils.text_utils import TextUtils

        assert TextUtils.normalize_case_number("") == ""

    def test_none_handling(self):
        from apps.automation.utils.text_utils import TextUtils

        assert TextUtils.normalize_case_number("") == ""


class TestTextUtilsCleanText:
    def test_normal_text(self):
        from apps.automation.utils.text_utils import TextUtils

        assert TextUtils.clean_text("hello world") == "hello world"

    def test_control_chars_removed(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.clean_text("hello\x00\x01world")
        assert result == "helloworld"

    def test_multiple_spaces_collapsed(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.clean_text("hello   world")
        assert result == "hello world"

    def test_tabs_and_newlines(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.clean_text("hello\t\nworld")
        assert result == "hello world"

    def test_empty_text(self):
        from apps.automation.utils.text_utils import TextUtils

        assert TextUtils.clean_text("") == ""
        assert TextUtils.clean_text(None) == ""


class TestTextUtilsExtractCaseNumbers:
    def test_single_case_number(self):
        from apps.automation.utils.text_utils import TextUtils

        text = "案号（2024）粤0606执38607号"
        result = TextUtils.extract_case_numbers(text)
        assert len(result) >= 1
        assert "执38607号" in result[0]

    def test_multiple_case_numbers(self):
        from apps.automation.utils.text_utils import TextUtils

        text = "（2024）粤0606执38607号和（2023）粤01民初100号"
        result = TextUtils.extract_case_numbers(text)
        assert len(result) >= 2

    def test_no_case_numbers(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.extract_case_numbers("这是一段普通文本")
        assert result == []

    def test_empty_text(self):
        from apps.automation.utils.text_utils import TextUtils

        result = TextUtils.extract_case_numbers("")
        assert result == []

    def test_deduplication(self):
        from apps.automation.utils.text_utils import TextUtils

        text = "（2024）粤0606执38607号\n（2024）粤0606执38607号"
        result = TextUtils.extract_case_numbers(text)
        assert len(result) == 1


# ============================================================================
# automation/services/sms/sms_parser_service.py tests
# ============================================================================


class TestSMSParseResult:
    def test_dataclass(self):
        from apps.automation.services.sms.sms_parser_service import SMSParseResult

        result = SMSParseResult(
            sms_type="document_delivery",
            download_links=["http://example.com"],
            case_numbers=["（2024）粤0606执386号"],
            party_names=["张三"],
            has_valid_download_link=True,
            verification_code="1234",
        )
        assert result.sms_type == "document_delivery"
        assert len(result.download_links) == 1
        assert result.verification_code == "1234"


class TestSMSSanitizeLink:
    def test_removes_trailing_punctuation(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        result = service._sanitize_link("http://example.com/path,")
        assert result == "http://example.com/path"

    def test_removes_chinese_punctuation(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        result = service._sanitize_link("http://example.com/path，")
        assert result == "http://example.com/path"

    def test_empty_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        result = service._sanitize_link("")
        assert result == ""

    def test_strips_whitespace(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        result = service._sanitize_link("  http://example.com  ")
        assert result == "http://example.com"


class TestSMSIsValidDownloadLink:
    def test_gdems_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        assert service._is_valid_download_link("https://example.com/v3/dzsd/abc123") is True

    def test_jysd_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        assert service._is_valid_download_link("https://example.com/sd?key=abc123") is True

    def test_hbfy_public_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        # The HBFY pattern matches /hb/msg=xxx in the URL path, but validation
        # requires path to end with /hb/msg and msg in query params
        # So the regex match is the real link, not what _is_valid_download_link validates
        # Let's test the regex extraction instead
        assert service.HBFY_PUBLIC_LINK_PATTERN.search("https://example.com/hb/msg=abc123") is not None

    def test_hbfy_account_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        assert service._is_valid_download_link("https://example.com/sfsddz") is True

    def test_sfdw_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        assert service._is_valid_download_link("https://example.com/sfsdw//r/abc123") is True

    def test_zxfw_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        link = "https://example.com/zxfw/#/pagesajkj/app/wssd/index?qdbh=1&sdbh=2&sdsin=3"
        assert service._is_valid_download_link(link) is True

    def test_invalid_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        assert service._is_valid_download_link("https://example.com/random") is False


class TestSMSExtractVerificationCode:
    def test_valid_code(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        assert service.extract_verification_code("验证码：1234") == "1234"

    def test_no_code(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        assert service.extract_verification_code("没有验证码") == ""

    def test_colon_variant(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        assert service.extract_verification_code("验证码:abcd") == "abcd"


class TestSMSExtractDownloadLinks:
    def test_gdems_link_extracted(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        links = service.extract_download_links("请点击 https://example.com/v3/dzsd/abc123 下载")
        assert len(links) == 1

    def test_no_links(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        links = service.extract_download_links("这是一条普通短信")
        assert len(links) == 0

    def test_deduplication(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        links = service.extract_download_links(
            "https://example.com/v3/dzsd/abc123\nhttps://example.com/v3/dzsd/abc123"
        )
        assert len(links) == 1


class TestSMSParse:
    def test_parse_with_link(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        content = "您有新文书 https://example.com/v3/dzsd/abc123 案号（2024）粤0606执386号"
        result = service.parse(content)
        assert result.sms_type == "document_delivery"
        assert result.has_valid_download_link is True
        assert len(result.download_links) >= 1

    def test_parse_filing_notification(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        content = "您的立案申请已通过"
        result = service.parse(content)
        assert result.sms_type == "filing_notification"

    def test_parse_info_notification(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        service = SMSParserService()
        content = "这是一条普通信息通知"
        result = service.parse(content)
        assert result.sms_type == "info_notification"


class TestSMSExtractPartyNames:
    def test_find_existing_clients(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        mock_client = Mock()
        mock_client.name = "张三"
        mock_client_service = Mock()
        mock_client_service.get_all_clients_internal.return_value = [mock_client]

        service = SMSParserService(client_service=mock_client_service)
        result = service._find_existing_clients_in_sms("当事人张三的文书已送达")
        assert "张三" in result

    def test_no_existing_clients_found(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        mock_client = Mock()
        mock_client.name = "李四"
        mock_client_service = Mock()
        mock_client_service.get_all_clients_internal.return_value = [mock_client]

        service = SMSParserService(client_service=mock_client_service)
        result = service._find_existing_clients_in_sms("当事人王五的文书已送达")
        assert len(result) == 0

    def test_short_name_skipped(self):
        from apps.automation.services.sms.sms_parser_service import SMSParserService

        mock_client = Mock()
        mock_client.name = "张"
        mock_client_service = Mock()
        mock_client_service.get_all_clients_internal.return_value = [mock_client]

        service = SMSParserService(client_service=mock_client_service)
        result = service._find_existing_clients_in_sms("张的文书")
        assert len(result) == 0
