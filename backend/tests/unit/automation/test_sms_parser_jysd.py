"""
测试 SMS 解析服务对 jysd.10102368.com 链接的支持
"""

from apps.automation.services.sms.sms_parser_service import SMSParserService


class TestSMSParserJysdLink:
    def setup_method(self):
        self.service = SMSParserService()

    def test_extract_jysd_link_from_sms(self):
        test_sms = (
            "【2368助手】海南南海翔龙实业有限公司，海口市龙华区人民法院依法向您发送（2026）琼0106行初27号相关文书，"
            "为保障您的合法权益，请点击 `https://jysd.10102368.com/sd?key=pKbAL9Jgv3UtIcSk-6275369f_01`  查看并下载文书。"
        )

        links = self.service.extract_download_links(test_sms)

        assert links == ["https://jysd.10102368.com/sd?key=pKbAL9Jgv3UtIcSk-6275369f_01"]

    def test_extract_jysd_link_with_trailing_punctuation(self):
        test_sms = (
            "请点击 https://jysd.10102368.com/sd?key=abc123_01。"
            "后续文字"
        )

        links = self.service.extract_download_links(test_sms)

        assert links == ["https://jysd.10102368.com/sd?key=abc123_01"]

    def test_extract_multiple_jysd_links(self):
        test_sms = (
            "链接1: https://jysd.10102368.com/sd?key=abc123_01 "
            "链接2: https://jysd.10102368.com/sd?key=xyz789_02"
        )

        links = self.service.extract_download_links(test_sms)

        assert len(links) == 2
        assert "https://jysd.10102368.com/sd?key=abc123_01" in links
        assert "https://jysd.10102368.com/sd?key=xyz789_02" in links

