"""测试当事人信息处理的纯逻辑方法

覆盖: apps/automation/services/scraper/sites/court_zxfw_filing/party_info_handler.py
重点: _normalize_client_type, _is_mobile_phone (静态方法)
"""

from __future__ import annotations

import re

import pytest
try:
    from plugins.court_automation import filing  # noqa: F401
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


from plugins.court_automation.filing.playwright_filing.party_info_handler import PartyInfoHandlerMixin


# ============================================================
# _normalize_client_type (static method)
# ============================================================


class TestNormalizeClientType:
    """测试当事人类别归一化"""

    def test_natural_returns_natural(self) -> None:
        assert PartyInfoHandlerMixin._normalize_client_type("natural") == "natural"

    def test_legal_returns_legal(self) -> None:
        assert PartyInfoHandlerMixin._normalize_client_type("legal") == "legal"

    def test_empty_string_returns_legal(self) -> None:
        """空字符串默认为 legal"""
        assert PartyInfoHandlerMixin._normalize_client_type("") == "legal"

    def test_unknown_type_returns_legal(self) -> None:
        assert PartyInfoHandlerMixin._normalize_client_type("some_random_type") == "legal"

    def test_other_organization_returns_other(self) -> None:
        assert PartyInfoHandlerMixin._normalize_client_type("other_organization") == "other_organization"

    def test_individual_business_returns_other(self) -> None:
        assert PartyInfoHandlerMixin._normalize_client_type("个体工商户") == "other_organization"

    def test_non_legal_person_returns_other(self) -> None:
        assert PartyInfoHandlerMixin._normalize_client_type("非法人组织") == "other_organization"

    def test_personal_investment_enterprise_returns_other(self) -> None:
        assert PartyInfoHandlerMixin._normalize_client_type("个人独资企业") == "other_organization"


# ============================================================
# _is_mobile_phone (static method)
# ============================================================


class TestIsMobilePhone:
    """测试手机号码验证"""

    def test_valid_mobile_13x(self) -> None:
        assert PartyInfoHandlerMixin._is_mobile_phone("13812345678") is True  # allowlist secret

    def test_valid_mobile_15x(self) -> None:
        assert PartyInfoHandlerMixin._is_mobile_phone("15912345678") is True  # allowlist secret

    def test_valid_mobile_18x(self) -> None:
        assert PartyInfoHandlerMixin._is_mobile_phone("18612345678") is True  # allowlist secret

    def test_valid_mobile_19x(self) -> None:
        assert PartyInfoHandlerMixin._is_mobile_phone("19912345678") is True  # allowlist secret

    def test_invalid_starts_with_0(self) -> None:
        assert PartyInfoHandlerMixin._is_mobile_phone("01234567890") is False

    def test_invalid_too_short(self) -> None:
        assert PartyInfoHandlerMixin._is_mobile_phone("1381234567") is False

    def test_invalid_too_long(self) -> None:
        assert PartyInfoHandlerMixin._is_mobile_phone("138123456789") is False

    def test_invalid_letters(self) -> None:
        assert PartyInfoHandlerMixin._is_mobile_phone("abcdefghijk") is False

    def test_empty_string(self) -> None:
        assert PartyInfoHandlerMixin._is_mobile_phone("") is False

    def test_none_input(self) -> None:
        assert PartyInfoHandlerMixin._is_mobile_phone(None) is False  # type: ignore[arg-type]

    def test_whitespace_stripped(self) -> None:
        """带空格的输入，strip后应匹配"""
        assert PartyInfoHandlerMixin._is_mobile_phone(" 13812345678 ") is True  # allowlist secret

    def test_valid_17x(self) -> None:
        assert PartyInfoHandlerMixin._is_mobile_phone("17812345678") is True  # allowlist secret
