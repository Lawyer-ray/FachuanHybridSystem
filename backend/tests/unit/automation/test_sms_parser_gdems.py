"""
测试 SMS 解析服务对 sd.gdems.com 链接的支持

Requirements: 短信解析服务应该能够提取广东电子送达链接
"""
import pytest
import re


class TestSMSParserGdemsLink:
    """测试 sd.gdems.com 链接提取"""
    
    # 广东电子送达链接正则
    GDEMS_LINK_PATTERN = re.compile(
        r'https://sd\.gdems\.com/v3/dzsd/[a-zA-Z0-9]+',
        re.IGNORECASE
    )
    
    def test_extract_gdems_link_from_sms(self):
        """测试从短信中提取 sd.gdems.com 链接"""
        test_sms = (
            "【佛山市禅城区人民法院】佛山市升平百货有限公司,"
            "（2025）粤0604民初42953号您有一条新的送达通知需要您查看："
            "https://sd.gdems.com/v3/dzsd/mDN68y"
        )
        
        matches = self.GDEMS_LINK_PATTERN.findall(test_sms)
        
        assert len(matches) == 1
        assert matches[0] == "https://sd.gdems.com/v3/dzsd/mDN68y"
    
    def test_extract_multiple_gdems_links(self):
        """测试提取多个 sd.gdems.com 链接"""
        test_sms = (
            "链接1: https://sd.gdems.com/v3/dzsd/abc123 "
            "链接2: https://sd.gdems.com/v3/dzsd/xyz789"
        )
        
        matches = self.GDEMS_LINK_PATTERN.findall(test_sms)
        
        assert len(matches) == 2
        assert "https://sd.gdems.com/v3/dzsd/abc123" in matches
        assert "https://sd.gdems.com/v3/dzsd/xyz789" in matches
    
    def test_gdems_link_pattern_variations(self):
        """测试不同格式的 sd.gdems.com 链接"""
        test_cases = [
            ("https://sd.gdems.com/v3/dzsd/mDN68y", True),
            ("https://sd.gdems.com/v3/dzsd/ABC123", True),
            ("https://sd.gdems.com/v3/dzsd/a1b2c3d4", True),
            ("http://sd.gdems.com/v3/dzsd/test", False),  # 必须是 https
            ("https://sd.gdems.com/v2/dzsd/test", False),  # 必须是 v3
            ("https://other.gdems.com/v3/dzsd/test", False),  # 必须是 sd 子域名
        ]
        
        for url, should_match in test_cases:
            matches = self.GDEMS_LINK_PATTERN.findall(url)
            if should_match:
                assert len(matches) == 1, f"应该匹配: {url}"
            else:
                assert len(matches) == 0, f"不应该匹配: {url}"
    
    def test_case_number_extraction(self):
        """测试案号提取（中文括号）"""
        from apps.automation.utils.text_utils import TextUtils
        
        test_sms = (
            "【佛山市禅城区人民法院】佛山市升平百货有限公司,"
            "（2025）粤0604民初42953号您有一条新的送达通知需要您查看"
        )
        
        case_numbers = TextUtils.extract_case_numbers(test_sms)
        
        assert len(case_numbers) == 1
        assert "（2025）粤0604民初42953号" in case_numbers[0]


class TestSMSParserBothLinkTypes:
    """测试同时支持两种链接类型"""
    
    # zxfw.court.gov.cn 链接正则
    ZXFW_LINK_PATTERN = re.compile(
        r'https://zxfw\.court\.gov\.cn/zxfw/#/pagesAjkj/app/wssd/index\?'
        r'[^\s]*?(?=.*qdbh=[^\s&]+)(?=.*sdbh=[^\s&]+)(?=.*sdsin=[^\s&]+)[^\s]*',
        re.IGNORECASE
    )
    
    # 广东电子送达链接正则
    GDEMS_LINK_PATTERN = re.compile(
        r'https://sd\.gdems\.com/v3/dzsd/[a-zA-Z0-9]+',
        re.IGNORECASE
    )
    
    def test_extract_both_link_types(self):
        """测试同时提取两种类型的链接"""
        test_sms = (
            "链接1: https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?"
            "qdbh=123&sdbh=456&sdsin=789 "
            "链接2: https://sd.gdems.com/v3/dzsd/mDN68y"
        )
        
        zxfw_matches = self.ZXFW_LINK_PATTERN.findall(test_sms)
        gdems_matches = self.GDEMS_LINK_PATTERN.findall(test_sms)
        
        assert len(zxfw_matches) == 1
        assert len(gdems_matches) == 1
