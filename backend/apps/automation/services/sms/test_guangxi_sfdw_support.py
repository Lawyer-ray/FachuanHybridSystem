"""广西司法送达新入口支持相关回归测试。"""

from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
from apps.automation.services.sms.parsing.download_link_extractor import DownloadLinkExtractor
from apps.automation.services.sms.sms_parser_service import SMSParserService


def test_sms_parser_extract_guangxi_sfdw_link() -> None:
    service = SMSParserService()
    content = (
        "【广西法院短信平台】环江县人民法院向您发送了（2026）桂1226民初420号案件相关文书，"
        "文书详见:http://171.106.48.55:28083/sfsdw//r/YbXWaDAj4a"
    )

    links = service.extract_download_links(content)

    assert "http://171.106.48.55:28083/sfsdw//r/YbXWaDAj4a" in links


def test_download_link_extractor_extract_guangxi_sfdw_link() -> None:
    extractor = DownloadLinkExtractor()
    content = "文书链接：http://171.106.48.55:28083/sfsdw//r/AbCd1234"

    links = extractor.extract(content)

    assert links == ["http://171.106.48.55:28083/sfsdw//r/AbCd1234"]


def test_sms_download_mixin_normalize_phone_tail6() -> None:
    assert SMSDownloadMixin._normalize_phone_tail6("138975829") == "975829"
    assert SMSDownloadMixin._normalize_phone_tail6("后6位: 975829") == "975829"
    assert SMSDownloadMixin._normalize_phone_tail6("12345") is None


def test_sms_download_mixin_identify_sfdw_url() -> None:
    assert SMSDownloadMixin._is_sfdw_url("http://171.106.48.55:28083/sfsdw//r/YbXWaDAj4a")
    assert SMSDownloadMixin._is_sfdw_url("https://sfpt.cdfy12368.gov.cn:806/sfsdw//r/demo")
    assert not SMSDownloadMixin._is_sfdw_url("https://jysd.10102368.com/sd?key=abc")
