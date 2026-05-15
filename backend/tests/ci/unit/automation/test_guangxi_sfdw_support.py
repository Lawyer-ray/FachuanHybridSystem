"""广西司法送达新入口支持相关回归测试。"""

from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
from apps.automation.services.sms.parsing.download_link_extractor import DownloadLinkExtractor
from apps.automation.services.sms.sms_parser_service import SMSParserService


def test_sms_parser_extract_guangxi_sfdw_link() -> None:
    service = SMSParserService()
    content = (
        "【广西法院短信平台】某地人民法院向您发送了（2099）桂0000民初000号案件相关文书，"
        "文书详见:http://171.106.48.55:28083/sfsdw//r/TESTTOKEN001"
    )

    links = service.extract_download_links(content)

    assert "http://171.106.48.55:28083/sfsdw//r/TESTTOKEN001" in links


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
    assert SMSDownloadMixin._is_sfdw_url("http://171.106.48.55:28083/sfsdw//r/TESTTOKEN001")
    assert SMSDownloadMixin._is_sfdw_url("https://sfpt.cdfy12368.gov.cn:806/sfsdw//r/demo")
    assert SMSDownloadMixin._is_sfdw_url("https://example.com/sfsdw//r/ALT_HOST_TOKEN")
    assert not SMSDownloadMixin._is_sfdw_url("https://jysd.10102368.com/sd?key=abc")


def test_sms_parser_extract_same_structure_new_domain() -> None:
    service = SMSParserService()
    content = (
        "【法院通知】文书下载：https://new-portal.example.cn/zxfw/#/pagesAjkj/app/wssd/index?"
        "qdbh=Q1&sdbh=S1&sdsin=U1"
    )

    links = service.extract_download_links(content)

    assert links == [
        "https://new-portal.example.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=Q1&sdbh=S1&sdsin=U1"
    ]


def test_download_link_extractor_extract_same_structure_new_domain() -> None:
    extractor = DownloadLinkExtractor()
    content = "请登录 https://alt-host.example.com/sd?key=ABCD1234 查看送达文书"

    links = extractor.extract(content)

    assert links == ["https://alt-host.example.com/sd?key=ABCD1234"]


def test_sms_download_mixin_identify_jysd_and_hbfy_structure_url() -> None:
    assert SMSDownloadMixin._is_jysd_url("https://jysd.10102368.com/sd?key=abc")
    assert SMSDownloadMixin._is_jysd_url("https://alt-host.example.com/sd?key=abc")

    assert SMSDownloadMixin._is_hbfy_account_url("https://dzsd.hbfy.gov.cn/sfsddz")
    assert SMSDownloadMixin._is_hbfy_account_url("https://same-structure.example.com/sfsddz")
    assert not SMSDownloadMixin._is_hbfy_account_url("https://example.com/sfsdw//r/token")
