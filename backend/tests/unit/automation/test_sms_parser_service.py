"""
SMSParserService 单元测试
"""

from unittest.mock import Mock, patch

import pytest

from apps.automation.models import CourtSMSType
from apps.automation.services.sms.sms_parser_service import SMSParseResult, SMSParserService


@pytest.mark.django_db
class TestSMSParserService:
    """短信解析服务测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        # 创建 Mock 客户服务
        self.mock_client_service = Mock()

        # 创建服务实例（注入 Mock）
        self.service = SMSParserService(client_service=self.mock_client_service)

    def test_parse_document_delivery_sms(self):
        """测试解析文书送达短信"""
        content = """
        佛山市禅城区人民法院：你好！你收到（2024）粤0604民初12345号案件文书，
        请查收：https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789
        """

        # 执行测试
        result = self.service.parse(content)

        # 断言结果
        assert isinstance(result, SMSParseResult)
        assert result.sms_type == CourtSMSType.DOCUMENT_DELIVERY
        assert result.has_valid_download_link is True
        assert len(result.download_links) == 1
        assert "zxfw.court.gov.cn" in result.download_links[0]
        assert len(result.case_numbers) == 1
        assert "（2024）粤0604民初12345号" in result.case_numbers

    def test_parse_filing_notification_sms(self):
        """测试解析立案通知短信"""
        content = """
        佛山市禅城区人民法院：你好！你的案件（2024）粤0604民初12345号已立案。
        """

        # 执行测试
        result = self.service.parse(content)

        # 断言结果
        assert result.sms_type == CourtSMSType.FILING_NOTIFICATION
        assert result.has_valid_download_link is False
        assert len(result.download_links) == 0
        assert len(result.case_numbers) == 1

    def test_parse_info_notification_sms(self):
        """测试解析信息通知短信"""
        content = """
        佛山市禅城区人民法院：你好！请于明日上午9点到庭参加庭审。
        """

        # 执行测试
        result = self.service.parse(content)

        # 断言结果
        assert result.sms_type == CourtSMSType.INFO_NOTIFICATION
        assert result.has_valid_download_link is False
        assert len(result.download_links) == 0

    def test_extract_download_links_zxfw(self):
        """测试提取 zxfw.court.gov.cn 下载链接"""
        content = "请查收：https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789"

        # 执行测试
        links = self.service.extract_download_links(content)

        # 断言结果
        assert len(links) == 1
        assert "zxfw.court.gov.cn" in links[0]
        assert "qdbh=123" in links[0]
        assert "sdbh=456" in links[0]
        assert "sdsin=789" in links[0]

    def test_extract_download_links_gdems(self):
        """测试提取广东电子送达链接"""
        content = "请查收：https://sd.gdems.com/v3/dzsd/abc123xyz"

        # 执行测试
        links = self.service.extract_download_links(content)

        # 断言结果
        assert len(links) == 1
        assert "sd.gdems.com" in links[0]
        assert "/v3/dzsd/" in links[0]

    def test_extract_download_links_multiple(self):
        """测试提取多个下载链接"""
        content = """
        链接1：https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789
        链接2：https://sd.gdems.com/v3/dzsd/abc123
        """

        # 执行测试
        links = self.service.extract_download_links(content)

        # 断言结果
        assert len(links) == 2

    def test_extract_download_links_invalid(self):
        """测试提取无效链接返回空列表"""
        # 缺少必要参数的链接
        content = "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123"

        # 执行测试
        links = self.service.extract_download_links(content)

        # 断言结果
        assert len(links) == 0

    def test_extract_case_numbers_single(self):
        """测试提取单个案号"""
        content = "你收到（2024）粤0604民初12345号案件文书"

        # 执行测试
        case_numbers = self.service.extract_case_numbers(content)

        # 断言结果
        assert len(case_numbers) == 1
        assert "（2024）粤0604民初12345号" in case_numbers

    def test_extract_case_numbers_multiple(self):
        """测试提取多个案号"""
        content = "案件（2024）粤0604民初12345号和（2024）粤0604民初67890号"

        # 执行测试
        case_numbers = self.service.extract_case_numbers(content)

        # 断言结果
        assert len(case_numbers) == 2

    def test_extract_case_numbers_none(self):
        """测试无案号返回空列表"""
        content = "这是一条没有案号的短信"

        # 执行测试
        case_numbers = self.service.extract_case_numbers(content)

        # 断言结果
        assert len(case_numbers) == 0

    def test_extract_party_names_from_existing_clients(self):
        """测试从现有客户中提取当事人"""
        content = "张三与李四合同纠纷案件"

        # 配置 Mock - 返回现有客户
        mock_client1 = Mock()
        mock_client1.name = "张三"
        mock_client2 = Mock()
        mock_client2.name = "李四"
        mock_client3 = Mock()
        mock_client3.name = "王五"

        self.mock_client_service.get_all_clients_internal.return_value = [mock_client1, mock_client2, mock_client3]

        # 执行测试
        party_names = self.service.extract_party_names(content)

        # 断言结果 - 应该找到张三和李四
        assert len(party_names) == 2
        assert "张三" in party_names
        assert "李四" in party_names
        assert "王五" not in party_names

    def test_extract_party_names_no_existing_clients(self):
        """测试没有现有客户时返回空列表"""
        content = "张三与李四合同纠纷案件"

        # 配置 Mock - 返回空列表
        self.mock_client_service.get_all_clients_internal.return_value = []

        # 执行测试
        party_names = self.service.extract_party_names(content)

        # 断言结果 - 应该返回空列表
        assert len(party_names) == 0

    def test_extract_party_names_client_not_in_sms(self):
        """测试客户名称不在短信中时不返回"""
        content = "张三与李四合同纠纷案件"

        # 配置 Mock - 返回不在短信中的客户
        mock_client = Mock()
        mock_client.name = "王五"

        self.mock_client_service.get_all_clients_internal.return_value = [mock_client]

        # 执行测试
        party_names = self.service.extract_party_names(content)

        # 断言结果
        assert len(party_names) == 0

    def test_extract_party_names_skip_short_names(self):
        """测试跳过太短的客户名称"""
        content = "张三与李四合同纠纷案件"

        # 配置 Mock - 包含单字名称
        mock_client1 = Mock()
        mock_client1.name = "张"  # 单字，应该被跳过
        mock_client2 = Mock()
        mock_client2.name = "张三"

        self.mock_client_service.get_all_clients_internal.return_value = [mock_client1, mock_client2]

        # 执行测试
        party_names = self.service.extract_party_names(content)

        # 断言结果 - 只应该找到张三
        assert len(party_names) == 1
        assert "张三" in party_names
        assert "张" not in party_names

    def test_is_valid_download_link_zxfw_valid(self):
        """测试验证有效的 zxfw 链接"""
        link = "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789"

        # 执行测试
        result = self.service._is_valid_download_link(link)

        # 断言结果
        assert result is True

    def test_is_valid_download_link_zxfw_missing_params(self):
        """测试验证缺少参数的 zxfw 链接"""
        link = "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456"

        # 执行测试
        result = self.service._is_valid_download_link(link)

        # 断言结果
        assert result is False

    def test_is_valid_download_link_gdems_valid(self):
        """测试验证有效的 gdems 链接"""
        link = "https://sd.gdems.com/v3/dzsd/abc123"

        # 执行测试
        result = self.service._is_valid_download_link(link)

        # 断言结果
        assert result is True

    def test_is_valid_download_link_invalid_domain(self):
        """测试验证无效域名的链接"""
        link = "https://invalid.com/path"

        # 执行测试
        result = self.service._is_valid_download_link(link)

        # 断言结果
        assert result is False

    def test_parse_with_company_names(self):
        """测试解析包含公司名称的短信"""
        content = """
        佛山市禅城区人民法院：你好！你收到（2024）粤0604民初12345号案件文书，
        涉及广东某某有限公司与深圳某某科技有限公司合同纠纷。
        请查收：https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789
        """

        # 配置 Mock - 返回公司客户
        mock_client1 = Mock()
        mock_client1.name = "广东某某有限公司"
        mock_client2 = Mock()
        mock_client2.name = "深圳某某科技有限公司"

        self.mock_client_service.get_all_clients_internal.return_value = [mock_client1, mock_client2]

        # 执行测试
        result = self.service.parse(content)

        # 断言结果
        assert result.sms_type == CourtSMSType.DOCUMENT_DELIVERY
        assert len(result.party_names) == 2
        assert "广东某某有限公司" in result.party_names
        assert "深圳某某科技有限公司" in result.party_names

    def test_parse_empty_content(self):
        """测试解析空内容"""
        content = ""

        # 配置 Mock
        self.mock_client_service.get_all_clients_internal.return_value = []

        # 执行测试
        result = self.service.parse(content)

        # 断言结果
        assert result.sms_type == CourtSMSType.INFO_NOTIFICATION
        assert result.has_valid_download_link is False
        assert len(result.download_links) == 0
        assert len(result.case_numbers) == 0
        assert len(result.party_names) == 0


@pytest.mark.django_db
class TestSMSParserServiceEdgeCases:
    """短信解析服务边界情况测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.mock_client_service = Mock()
        self.service = SMSParserService(client_service=self.mock_client_service)

    def test_extract_download_links_case_insensitive(self):
        """测试链接提取不区分大小写"""
        content = "https://ZXFW.COURT.GOV.CN/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789"

        # 执行测试
        links = self.service.extract_download_links(content)

        # 断言结果
        assert len(links) == 1

    def test_extract_download_links_with_extra_params(self):
        """测试提取包含额外参数的链接"""
        content = "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789&extra=value"

        # 执行测试
        links = self.service.extract_download_links(content)

        # 断言结果
        assert len(links) == 1
        assert "extra=value" in links[0]

    def test_extract_download_links_duplicate(self):
        """测试去重重复的链接"""
        content = """
        链接1：https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789
        链接2：https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789
        """

        # 执行测试
        links = self.service.extract_download_links(content)

        # 断言结果 - 应该去重
        assert len(links) == 1

    def test_find_existing_clients_exception_handling(self):
        """测试查找现有客户时异常处理"""
        content = "张三与李四合同纠纷案件"

        # 配置 Mock - 抛出异常
        self.mock_client_service.get_all_clients_internal.side_effect = Exception("Database error")

        # 执行测试 - 不应该抛出异常
        party_names = self.service.extract_party_names(content)

        # 断言结果 - 应该返回空列表
        assert len(party_names) == 0

    def test_parse_with_multiple_case_numbers_and_links(self):
        """测试解析包含多个案号和链接的复杂短信"""
        content = """
        案件（2024）粤0604民初12345号和（2024）粤0604民初67890号的文书已送达。
        链接1：https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789
        链接2：https://sd.gdems.com/v3/dzsd/abc123
        """

        # 配置 Mock
        self.mock_client_service.get_all_clients_internal.return_value = []

        # 执行测试
        result = self.service.parse(content)

        # 断言结果
        assert result.sms_type == CourtSMSType.DOCUMENT_DELIVERY
        assert len(result.download_links) == 2
        assert len(result.case_numbers) == 2

    def test_extract_party_names_with_whitespace(self):
        """测试处理客户名称包含空格的情况"""
        content = "张三 与李四合同纠纷案件"

        # 配置 Mock - 客户名称包含空格
        mock_client = Mock()
        mock_client.name = "  张三  "  # 前后有空格

        self.mock_client_service.get_all_clients_internal.return_value = [mock_client]

        # 执行测试
        party_names = self.service.extract_party_names(content)

        # 断言结果 - 应该能找到（因为会 strip）
        assert len(party_names) == 1
        assert "张三" in party_names

    def test_parse_sms_type_priority(self):
        """测试短信类型判定优先级"""
        # 有下载链接的优先判定为文书送达
        content_with_link = """
        你的案件已立案。
        请查收：https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=123&sdbh=456&sdsin=789
        """

        # 配置 Mock
        self.mock_client_service.get_all_clients_internal.return_value = []

        # 执行测试
        result = self.service.parse(content_with_link)

        # 断言结果 - 应该是文书送达，而不是立案通知
        assert result.sms_type == CourtSMSType.DOCUMENT_DELIVERY
