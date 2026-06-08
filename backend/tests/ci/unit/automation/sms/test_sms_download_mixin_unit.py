"""sms_download_mixin.py 单元测试。"""

from __future__ import annotations

import pytest


class TestNormalizePhoneTail6:

    @pytest.mark.parametrize("raw,expected", [
        ("13800000000", "000000"),   # 138-0000-0000 -> last 6 = 000000
        ("+8613800000000", "000000"),
        ("138001", "138001"),  # exactly 6 digits
        ("", None),
        (None, None),
        ("abc13800000000xyz", "000000"),
    ])
    def test_normalize_phone_tail6(self, raw, expected):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._normalize_phone_tail6(raw) == expected


class TestHostEqualsOrSubdomain:

    def test_exact_match(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._host_equals_or_subdomain("example.com", "example.com") is True

    def test_subdomain(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._host_equals_or_subdomain("sub.example.com", "example.com") is True

    def test_no_match(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._host_equals_or_subdomain("other.com", "example.com") is False


class TestIsZxfwUrl:

    @pytest.mark.parametrize("url,expected", [
        ("https://zxfw.court.gov.cn/zxfw/#/page", True),
        ("https://www.zxfw.court.gov.cn/api/data", True),
        ("https://example.com/page", False),
    ])
    def test_is_zxfw_url(self, url, expected):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._is_zxfw_url(url) == expected


class TestIsHbfyAccountUrl:

    def test_hbfy_account_url(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._is_hbfy_account_url("http://dzsd.hbfy.gov.cn/sfsddz") is True

    def test_non_hbfy_url(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._is_hbfy_account_url("https://example.com/page") is False


class TestIsJysdUrl:

    def test_jysd_url(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._is_jysd_url("https://jysd.10102368.com/sd?key=abc") is True

    def test_non_jysd_url(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._is_jysd_url("https://example.com/sd") is False


class TestIsSfdwUrl:

    def test_sfdw_cdfy_url(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._is_sfdw_url("https://sfpt.cdfy12368.gov.cn/sfsdw//r/abc") is True

    def test_sfdw_ip_url(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._is_sfdw_url("http://171.106.48.55:28083/page") is True

    def test_non_sfdw_url(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._is_sfdw_url("https://example.com/page") is False


class TestGetRequiredPlatformName:

    def test_zxfw_returns_none(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._get_required_platform_name("https://zxfw.court.gov.cn/page") is None

    def test_hbfy_returns_name(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        result = SMSDownloadMixin._get_required_platform_name("http://dzsd.hbfy.gov.cn/sfsddz")
        assert result is not None
        assert "湖北" in result

    def test_jysd_returns_name(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        result = SMSDownloadMixin._get_required_platform_name("https://jysd.10102368.com/sd?key=abc")
        assert result is not None
        assert "简易送达" in result

    def test_unknown_returns_none(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        assert SMSDownloadMixin._get_required_platform_name("https://example.com/page") is None


class TestExtractHbfyCredentials:

    def test_extracts_credentials(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        mixin = SMSDownloadMixin()
        content = "账号 42010012345678901，默认密码：Abc12345"
        account, password = mixin._extract_hbfy_credentials(content)
        assert account == "42010012345678901"
        assert password == "Abc12345"

    def test_no_credentials(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        mixin = SMSDownloadMixin()
        account, password = mixin._extract_hbfy_credentials("无关内容")
        assert account is None
        assert password is None


class TestExtractSfdwVerificationCode:

    def test_extracts_code(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        mixin = SMSDownloadMixin()
        assert mixin._extract_sfdw_verification_code("验证码：123456") == "123456"

    def test_no_code(self):
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin
        mixin = SMSDownloadMixin()
        assert mixin._extract_sfdw_verification_code("没有验证码") is None
