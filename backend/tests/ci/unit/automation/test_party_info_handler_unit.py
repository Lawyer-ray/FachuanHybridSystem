"""party_info_handler.py 单元测试 — 纯逻辑函数。"""

from __future__ import annotations

import pytest


class TestNormalizeClientType:

    @pytest.mark.parametrize("raw,expected", [
        ("natural", "natural"),
        ("legal", "legal"),
        ("非法人组织", "other_organization"),
        ("个体工商户", "other_organization"),
        ("个人独资企业", "other_organization"),
        ("other_organization", "other_organization"),
        ("", "legal"),
        ("unknown", "legal"),
    ])
    def test_normalize_client_type(self, raw, expected):
        from apps.automation.services.scraper.sites.court_zxfw_filing.party_info_handler import PartyInfoHandlerMixin
        assert PartyInfoHandlerMixin._normalize_client_type(raw) == expected


class TestIsMobilePhone:

    @pytest.mark.parametrize("value,expected", [
        ("13800138000", True),
        ("013800138000", False),
        ("1380013800", False),
        ("", False),
        ("abc", False),
    ])
    def test_is_mobile_phone(self, value, expected):
        from apps.automation.services.scraper.sites.court_zxfw_filing.party_info_handler import PartyInfoHandlerMixin
        assert PartyInfoHandlerMixin._is_mobile_phone(value) == expected
