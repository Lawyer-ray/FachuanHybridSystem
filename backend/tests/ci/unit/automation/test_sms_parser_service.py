"""SMS 解析服务测试 - 真实执行代码，不 mock 被测函数。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.automation.models import CourtSMSType
from apps.automation.services.sms.sms_parser_service import SMSParseResult, SMSParserService


class TestSMSParserServiceLinkExtraction:
    """测试下载链接提取。"""

    def setup_method(self) -> None:
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_extract_zxfw_link(self) -> None:
        """提取人民法院在线服务网链接。"""
        content = "请点击链接查收文书 https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=abc"
        links = self.service.extract_download_links(content)
        assert len(links) == 1
        assert "qdbh=123" in links[0]

    def test_extract_gdems_link(self) -> None:
        """提取广东电子送达链接。"""
        content = "请查收 https://sd.gdcourts.gov.cn/v3/dzsd/ABC123"
        links = self.service.extract_download_links(content)
        assert len(links) == 1
        assert "/v3/dzsd/ABC123" in links[0]

    def test_extract_jysd_link(self) -> None:
        """提取简易送达链接。"""
        content = "请查收 https://sd.court.gov.cn/sd?key=abc123_def"
        links = self.service.extract_download_links(content)
        assert len(links) == 1
        assert "key=abc123_def" in links[0]

    def test_extract_hbfy_public_link(self) -> None:
        """提取湖北电子送达免账号链接。"""
        content = "请查收 https://hbfy.court.gov.cn/hb/msg?msg=ABC123"
        links = self.service.extract_download_links(content)
        assert len(links) == 1

    def test_extract_hbfy_account_link(self) -> None:
        """提取湖北电子送达账号入口链接。"""
        content = "请登录 https://hbfy.court.gov.cn/sfsddz 查收"
        links = self.service.extract_download_links(content)
        assert len(links) == 1

    def test_extract_sfdw_link(self) -> None:
        """提取司法送达网链接。"""
        content = "请查收 https://sfsdw.court.gov.cn/sfsdw//r/ABC123"
        links = self.service.extract_download_links(content)
        assert len(links) == 1

    def test_no_valid_link(self) -> None:
        """无有效链接返回空列表。"""
        content = "这是一条普通短信，没有链接"
        links = self.service.extract_download_links(content)
        assert links == []

    def test_duplicate_links_deduped(self) -> None:
        """重复链接去重。"""
        link = "https://sd.court.gov.cn/sd?key=abc123"
        content = f"链接1: {link} 链接2: {link}"
        links = self.service.extract_download_links(content)
        assert len(links) == 1

    def test_trailing_punctuation_stripped(self) -> None:
        """链接尾部标点被清除。"""
        content = "请查收 https://sd.gdcourts.gov.cn/v3/dzsd/ABC123。"
        links = self.service.extract_download_links(content)
        assert len(links) == 1
        assert not links[0].endswith("。")

    def test_zxfw_link_missing_params_invalid(self) -> None:
        """缺少必要参数的 zxfw 链接不被提取。"""
        content = "https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123"
        links = self.service.extract_download_links(content)
        assert links == []


class TestSMSParserServiceSanitizeLink:
    """测试链接清洗。"""

    def setup_method(self) -> None:
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_sanitize_trailing_comma(self) -> None:
        result = self.service._sanitize_link("https://example.com,")
        assert result == "https://example.com"

    def test_sanitize_trailing_period(self) -> None:
        result = self.service._sanitize_link("https://example.com.")
        assert result == "https://example.com"

    def test_sanitize_trailing_semicolon(self) -> None:
        result = self.service._sanitize_link("https://example.com;")
        assert result == "https://example.com"

    def test_sanitize_trailing_chinese_punct(self) -> None:
        result = self.service._sanitize_link("https://example.com。")
        assert result == "https://example.com"

    def test_sanitize_empty_string(self) -> None:
        result = self.service._sanitize_link("")
        assert result == ""

    def test_sanitize_none(self) -> None:
        result = self.service._sanitize_link(None)  # type: ignore[arg-type]
        assert result == ""

    def test_sanitize_whitespace(self) -> None:
        result = self.service._sanitize_link("  https://example.com  ")
        assert result == "https://example.com"


class TestSMSParserServiceIsValidDownloadLink:
    """测试链接有效性验证。"""

    def setup_method(self) -> None:
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_zxfw_valid(self) -> None:
        link = "https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=1&sdbh=2&sdsin=3"
        assert self.service._is_valid_download_link(link) is True

    def test_zxfw_missing_sdsin(self) -> None:
        link = "https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=1&sdbh=2"
        assert self.service._is_valid_download_link(link) is False

    def test_gdems_valid(self) -> None:
        link = "https://sd.gdcourts.gov.cn/v3/dzsd/ABC123"
        assert self.service._is_valid_download_link(link) is True

    def test_jysd_valid(self) -> None:
        link = "https://sd.court.gov.cn/sd?key=abc123"
        assert self.service._is_valid_download_link(link) is True

    def test_jysd_no_key(self) -> None:
        link = "https://sd.court.gov.cn/sd"
        assert self.service._is_valid_download_link(link) is False

    def test_hbfy_public_valid(self) -> None:
        link = "https://hbfy.court.gov.cn/hb/msg?msg=ABC123"
        assert self.service._is_valid_download_link(link) is True

    def test_hbfy_account_valid(self) -> None:
        link = "https://hbfy.court.gov.cn/sfsddz"
        assert self.service._is_valid_download_link(link) is True

    def test_sfdw_valid(self) -> None:
        link = "https://sfsdw.court.gov.cn/sfsdw//r/ABC123"
        assert self.service._is_valid_download_link(link) is True

    def test_random_url_invalid(self) -> None:
        link = "https://example.com/some/path"
        assert self.service._is_valid_download_link(link) is False


class TestSMSParserServiceVerificationCode:
    """测试验证码提取。"""

    def setup_method(self) -> None:
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_extract_verification_code(self) -> None:
        content = "您的验证码：1234，请在页面输入"
        code = self.service.extract_verification_code(content)
        assert code == "1234"

    def test_extract_verification_code_colon(self) -> None:
        content = "验证码:5678"
        code = self.service.extract_verification_code(content)
        assert code == "5678"

    def test_no_verification_code(self) -> None:
        content = "这是一条普通短信"
        code = self.service.extract_verification_code(content)
        assert code == ""

    def test_verification_code_6_chars(self) -> None:
        content = "验证码：ABCDEF"
        code = self.service.extract_verification_code(content)
        assert code == "ABCDEF"


class TestSMSParserServiceCaseNumbers:
    """测试案号提取。"""

    def setup_method(self) -> None:
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_extract_case_number(self) -> None:
        content = "（2025）粤0604民初41257号案件已受理"
        numbers = self.service.extract_case_numbers(content)
        assert len(numbers) >= 1
        assert any("41257" in n for n in numbers)

    def test_no_case_number(self) -> None:
        content = "这是一条普通短信"
        numbers = self.service.extract_case_numbers(content)
        assert numbers == []

    def test_multiple_case_numbers(self) -> None:
        content = "（2025）粤0604民初1号（2025）粤0604民初2号"
        numbers = self.service.extract_case_numbers(content)
        assert len(numbers) >= 2


class TestSMSParserServiceParse:
    """测试完整解析流程。"""

    def setup_method(self) -> None:
        self.mock_client_service = MagicMock()
        self.mock_client_service.get_all_clients_internal.return_value = []
        self.service = SMSParserService(
            client_service=self.mock_client_service,
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_parse_document_delivery_sms(self) -> None:
        """包含下载链接的短信识别为文书送达。"""
        content = (
            "您有新的文书送达 https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index"
            "?qdbh=1&sdbh=2&sdsin=3 （2025）粤0604民初41257号"
        )
        result = self.service.parse(content)
        assert isinstance(result, SMSParseResult)
        assert result.sms_type == CourtSMSType.DOCUMENT_DELIVERY
        assert result.has_valid_download_link is True
        assert len(result.download_links) >= 1

    def test_parse_filing_notification(self) -> None:
        """包含立案关键词的短信识别为立案通知。"""
        content = "您的案件已立案，请等待通知"
        result = self.service.parse(content)
        assert result.sms_type == CourtSMSType.FILING_NOTIFICATION

    def test_parse_info_notification(self) -> None:
        """普通短信识别为信息通知。"""
        content = "这是一条普通通知"
        result = self.service.parse(content)
        assert result.sms_type == CourtSMSType.INFO_NOTIFICATION
        assert result.has_valid_download_link is False

    def test_parse_sfdw_with_verification_code(self) -> None:
        """司法送达网短信提取验证码。"""
        content = "请查收 https://sfsdw.court.gov.cn/sfsdw//r/ABC123 验证码：5678"
        result = self.service.parse(content)
        assert result.verification_code == "5678"
        assert len(result.download_links) >= 1


class TestSMSParserServicePartyExtraction:
    """测试当事人提取（regex 降级方案）。"""

    def setup_method(self) -> None:
        self.service = SMSParserService(
            client_service=MagicMock(),
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_extract_company_names(self) -> None:
        """提取公司名称。"""
        parties: list[str] = []
        self.service._collect_company_names("佛山市某某有限公司与张三合同纠纷", parties)
        assert any("某某有限公司" in p for p in parties)

    def test_extract_versus_patterns(self) -> None:
        """提取 A 与 B 模式。"""
        parties: list[str] = []
        self.service._collect_versus_patterns("张三与李四合同纠纷案", parties)
        assert len(parties) >= 2

    def test_filter_parties_excludes_keywords(self) -> None:
        """过滤包含排除关键词的当事人。"""
        result = self.service._filter_parties(["人民法院", "张三", "书记员", "李四"])
        assert "人民法院" not in result
        assert "书记员" not in result
        assert "张三" in result
        assert "李四" in result

    def test_filter_parties_excludes_short_names(self) -> None:
        """过滤太短的名称。"""
        result = self.service._filter_parties(["张", "张三"])
        assert "张" not in result
        assert "张三" in result

    def test_filter_parties_excludes_invalid_fragments(self) -> None:
        """过滤无效片段。"""
        result = self.service._filter_parties(["有限公司", "股份有限公司", "张三"])
        assert "有限公司" not in result
        assert "股份有限公司" not in result
        assert "张三" in result

    def test_filter_parties_excludes_non_chinese(self) -> None:
        """过滤非纯中文名称（允许数字）。"""
        result = self.service._filter_parties(["ABC", "张三123", "李四"])
        assert "ABC" not in result
        # 张三123 包含中文和数字，正则允许
        assert "张三123" in result
        assert "李四" in result

    def test_filter_parties_excludes_trailing_keywords(self) -> None:
        """过滤以特定字结尾的名称。"""
        result = self.service._filter_parties(["张三的", "李四案", "王五财", "赵六"])
        assert "张三的" not in result
        assert "李四案" not in result
        assert "王五财" not in result
        assert "赵六" in result


class TestSMSParserServiceDocumentDeliveryDetection:
    """测试文书送达短信检测。"""

    def setup_method(self) -> None:
        self.mock_client_service = MagicMock()
        self.mock_client_service.get_all_clients_internal.return_value = []
        self.service = SMSParserService(
            client_service=self.mock_client_service,
            party_matching_service=MagicMock(),
            party_candidate_extractor=MagicMock(),
        )

    def test_is_document_delivery_with_link_and_case_number(self) -> None:
        content = (
            "请查收送达文书 https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index"
            "?qdbh=1&sdbh=2&sdsin=3 （2025）粤0604民初1号"
        )
        assert self.service._is_document_delivery_without_parties(content) is True

    def test_is_not_delivery_without_link(self) -> None:
        content = "请查收送达文书（2025）粤0604民初1号"
        assert self.service._is_document_delivery_without_parties(content) is False

    def test_is_not_delivery_with_party_indicator(self) -> None:
        content = (
            "请查收送达文书 https://court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index"
            "?qdbh=1&sdbh=2&sdsin=3 （2025）粤0604民初1号 张三与李四"
        )
        assert self.service._is_document_delivery_without_parties(content) is False
