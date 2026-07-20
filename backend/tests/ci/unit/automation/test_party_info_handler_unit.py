"""party_info_handler.py 单元测试 — 纯逻辑函数。"""

from __future__ import annotations

import pytest
try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)



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
        from plugins.court_automation.filing.playwright_filing.party_info_handler import PartyInfoHandlerMixin
        assert PartyInfoHandlerMixin._normalize_client_type(raw) == expected


class TestIsMobilePhone:

    @pytest.mark.parametrize("value,expected", [
        ("12000000000", True),
        ("013800138000", False),
        ("1380013800", False),
        ("", False),
        ("abc", False),
    ])
    def test_is_mobile_phone(self, value, expected):
        from plugins.court_automation.filing.playwright_filing.party_info_handler import PartyInfoHandlerMixin
        assert PartyInfoHandlerMixin._is_mobile_phone(value) == expected
