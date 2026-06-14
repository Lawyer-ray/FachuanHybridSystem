"""Tests for oa_filing JTN client import script - pure logic methods."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.oa_filing.services.oa_scripts.jtn.client_import.service import (
    ClientListFormState,
    CustomerListItem,
    JtnClientImportScript,
    OACustomerData,
)


def _make_script(**overrides: Any) -> JtnClientImportScript:
    return JtnClientImportScript(
        account=overrides.get("account", "testuser"),
        password=overrides.get("password", "testpass"),
        headless=overrides.get("headless", True),
        progress_callback=overrides.get("progress_callback"),
    )


# ---------------------------------------------------------------------------
# OACustomerData tests
# ---------------------------------------------------------------------------


class TestOACustomerData:
    def test_defaults(self):
        data = OACustomerData(name="Test", client_type="natural")
        assert data.phone is None
        assert data.address is None
        assert data.id_number is None

    def test_with_values(self):
        data = OACustomerData(
            name="Company",
            client_type="legal",
            phone="13800138000",  # pragma: allowlist secret
            address="Beijing",
            legal_representative="CEO",
        )
        assert data.phone == "13800138000"  # pragma: allowlist secret
        assert data.legal_representative == "CEO"


# ---------------------------------------------------------------------------
# CustomerListItem tests
# ---------------------------------------------------------------------------


class TestCustomerListItem:
    def test_basic(self):
        item = CustomerListItem(name="A", client_type="natural", key_id="123")
        assert item.key_id == "123"


# ---------------------------------------------------------------------------
# ClientListFormState tests
# ---------------------------------------------------------------------------


class TestClientListFormState:
    def test_defaults(self):
        state = ClientListFormState(action_url="http://test", payload={})
        assert state.total_count == 0
        assert state.page_size == 20


# ---------------------------------------------------------------------------
# JtnClientImportScript - pure utility methods
# ---------------------------------------------------------------------------


class TestJtnClientImportScriptNormalizeText:
    def test_normalize_none(self):
        assert JtnClientImportScript._normalize_text(None) == ""

    def test_normalize_whitespace(self):
        result = JtnClientImportScript._normalize_text("  hello   world  ")
        assert "hello world" in result

    def test_normalize_newlines_collapsed(self):
        result = JtnClientImportScript._normalize_text("a\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_normalize_nbsp(self):
        result = JtnClientImportScript._normalize_text("a b")
        assert " " not in result


class TestJtnClientImportScriptToInt:
    def test_none_returns_zero(self):
        assert JtnClientImportScript._to_int(None) == 0

    def test_int_passthrough(self):
        assert JtnClientImportScript._to_int(42) == 42

    def test_string_number(self):
        assert JtnClientImportScript._to_int("100") == 100

    def test_invalid_string(self):
        assert JtnClientImportScript._to_int("abc") == 0

    def test_mixed_string_with_digits(self):
        assert JtnClientImportScript._to_int("abc123def") == 123

    def test_empty_string(self):
        assert JtnClientImportScript._to_int("") == 0


class TestJtnClientImportScriptIsValidFieldValue:
    def test_none_returns_false(self):
        svc = _make_script()
        assert svc._is_valid_field_value(None) is False

    def test_slash_returns_false(self):
        svc = _make_script()
        assert svc._is_valid_field_value("/") is False

    def test_dash_returns_false(self):
        svc = _make_script()
        assert svc._is_valid_field_value("-") is False

    def test_na_returns_false(self):
        svc = _make_script()
        assert svc._is_valid_field_value("N/A") is False

    def test_wu_returns_false(self):
        svc = _make_script()
        assert svc._is_valid_field_value("无") is False

    def test_valid_value_returns_true(self):
        svc = _make_script()
        assert svc._is_valid_field_value("13800138000") is True  # pragma: allowlist secret


class TestJtnClientImportScriptIsValidPhone:
    def test_valid_phone(self):
        svc = _make_script()
        assert svc._is_valid_phone("13800138000") is True  # pragma: allowlist secret

    def test_too_short(self):
        svc = _make_script()
        assert svc._is_valid_phone("123") is False

    def test_too_long_is_id_number(self):
        svc = _make_script()
        assert svc._is_valid_phone("110101199001011234") is False  # pragma: allowlist secret

    def test_none_returns_false(self):
        svc = _make_script()
        assert svc._is_valid_phone(None) is False


class TestJtnClientImportScriptExtractLabeledValue:
    def test_found(self):
        svc = _make_script()
        result = svc._extract_labeled_value("电话: 13800138000\n地址: Beijing", "电话")  # pragma: allowlist secret
        assert result == "13800138000"  # pragma: allowlist secret

    def test_not_found(self):
        svc = _make_script()
        result = svc._extract_labeled_value("无关文本", "电话")
        assert result is None

    def test_chinese_colon(self):
        svc = _make_script()
        result = svc._extract_labeled_value("地址：北京市朝阳区", "地址")
        assert "北京市" in result


class TestJtnClientImportScriptParseCustomerDetailText:
    def test_natural_person_id_number(self):
        svc = _make_script()
        text = "客户名称: 张三\n身份证号码: 110101199001011234\n性别: 男"  # pragma: allowlist secret
        result = svc._parse_customer_detail_text("张三", "natural", text)
        assert result.id_number == "110101199001011234"  # pragma: allowlist secret
        assert result.gender == "男"
        assert result.client_type == "natural"

    def test_legal_representative_switches_type(self):
        svc = _make_script()
        text = "法定代表人: 张三\n地址: 北京"
        result = svc._parse_customer_detail_text("某公司", "unknown", text)
        assert result.legal_representative == "张三"
        assert result.client_type == "legal"

    def test_address_from_id_address(self):
        svc = _make_script()
        text = "身份证地址: 北京市朝阳区"
        result = svc._parse_customer_detail_text("张三", "natural", text)
        assert result.address == "北京市朝阳区"


class TestJtnClientImportScriptResolveDetailWorkers:
    def test_single_item(self):
        svc = _make_script()
        assert svc._resolve_detail_workers(total=1) == 1

    def test_many_items_uses_config(self):
        svc = _make_script()
        with patch.dict("os.environ", {"OA_CLIENT_IMPORT_DETAIL_WORKERS": "3"}):
            result = svc._resolve_detail_workers(total=10)
            assert result == 3

    def test_invalid_env_falls_back(self):
        svc = _make_script()
        with patch.dict("os.environ", {"OA_CLIENT_IMPORT_DETAIL_WORKERS": "abc"}):
            result = svc._resolve_detail_workers(total=10)
            assert result == 6


class TestJtnClientImportScriptResolveTotalPages:
    def test_zero_total(self):
        svc = _make_script()
        assert svc._resolve_total_pages(0, 20) == 0

    def test_normal(self):
        svc = _make_script()
        assert svc._resolve_total_pages(45, 20) == 3

    def test_exact(self):
        svc = _make_script()
        assert svc._resolve_total_pages(20, 20) == 1


class TestJtnClientImportScriptExtractKeyId:
    def test_valid_href(self):
        svc = _make_script()
        result = svc._extract_key_id_from_href("CustomerInfor.aspx?KeyID=abc123&Category=A")
        assert result == "abc123"

    def test_no_key_id(self):
        svc = _make_script()
        result = svc._extract_key_id_from_href("CustomerInfor.aspx?Category=A")
        assert result is None

    def test_empty_href(self):
        svc = _make_script()
        assert svc._extract_key_id_from_href("") is None


class TestJtnClientImportScriptEmitProgress:
    def test_no_callback(self):
        svc = _make_script()
        svc._emit_progress("test_event")  # Should not raise

    def test_callback_called(self):
        cb = MagicMock()
        svc = _make_script(progress_callback=cb)
        svc._emit_progress("test_event", key="value")
        cb.assert_called_once()

    def test_callback_exception_handled(self):
        cb = MagicMock(side_effect=TypeError("bad"))
        svc = _make_script(progress_callback=cb)
        svc._emit_progress("test_event")  # Should not raise
