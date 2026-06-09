"""Tests for oa_filing.http_filing - HttpFilingMixin static/pure methods."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.oa_filing.services.oa_scripts.jtn.filing.http_filing import HttpFilingMixin
from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import (
    FilingFormState,
    ResolvedCustomer,
)


class TestHttpFilingMixinProjectFieldName:
    def test_basic(self):
        result = HttpFilingMixin._project_field_name("manager_id")
        assert "project_manager_id" in result
        assert result.startswith("ctl00$")

    def test_category(self):
        result = HttpFilingMixin._project_field_name("category_id")
        assert "project_category_id" in result


class TestHttpFilingMixinHandlerUrl:
    def test_handler_url(self):
        result = HttpFilingMixin._handler_url("CustSeachGetList")
        assert "CustSeachGetList" in result
        assert result.endswith("CustSeachGetList")


class TestHttpFilingMixinParseJsonObject:
    def test_valid_dict(self):
        result = HttpFilingMixin._parse_json_object('{"key": "value"}')
        assert result == {"key": "value"}

    def test_bom_stripped(self):
        result = HttpFilingMixin._parse_json_object('﻿{"key": "value"}')
        assert result == {"key": "value"}

    def test_non_dict_raises(self):
        with pytest.raises(RuntimeError, match="OA 接口返回格式异常"):
            HttpFilingMixin._parse_json_object('[1, 2, 3]')

    def test_whitespace_stripped(self):
        result = HttpFilingMixin._parse_json_object('  {"a": 1}  ')
        assert result == {"a": 1}


class TestHttpFilingMixinNormalizeText:
    def test_none_returns_empty(self):
        assert HttpFilingMixin._normalize_text(None) == ""

    def test_nbsp_normalized(self):
        result = HttpFilingMixin._normalize_text("a b")
        assert " " not in result

    def test_fullwidth_space_normalized(self):
        result = HttpFilingMixin._normalize_text("a　b")
        assert "　" not in result


class TestHttpFilingMixinExtractFilingFormState:
    def test_simple_form(self):
        html = """
        <html><body>
        <form id="aspnetForm" action="/submit">
            <input name="field1" type="text" value="val1" />
            <input name="btnSubmit" type="submit" value="Submit" />
            <select name="dropdown">
                <option value="a">A</option>
                <option value="b" selected>B</option>
            </select>
            <textarea name="notes">Hello World</textarea>
        </form>
        </body></html>
        """
        svc = HttpFilingMixin()
        result = svc._extract_filing_form_state(html_text=html, base_url="http://test.com")
        assert result.payload.get("field1") == "val1"
        assert "btnSubmit" not in result.payload
        assert result.payload.get("dropdown") == "b"
        assert "Hello World" in result.payload.get("notes", "")

    def test_no_form_raises(self):
        html = "<html><body><p>No form here</p></body></html>"
        svc = HttpFilingMixin()
        with pytest.raises(RuntimeError, match="aspnetForm"):
            svc._extract_filing_form_state(html_text=html, base_url="http://test.com")


class TestHttpFilingMixinAssertSubmitSuccess:
    def test_success_marker(self):
        svc = HttpFilingMixin()
        svc._assert_http_submit_success("案件保存未提交成功")

    def test_another_success_marker(self):
        svc = HttpFilingMixin()
        svc._assert_http_submit_success("保存并提交成功")

    def test_alert_raises(self):
        svc = HttpFilingMixin()
        with pytest.raises(RuntimeError, match="HTTP 立案失败"):
            svc._assert_http_submit_success("alert('案件编号已存在')")

    def test_no_marker_raises(self):
        svc = HttpFilingMixin()
        with pytest.raises(RuntimeError, match="未检测到成功标记"):
            svc._assert_http_submit_success("<html>nothing here</html>")


class TestHttpFilingMixinApplyClientPayload:
    def test_apply_single_customer(self):
        svc = HttpFilingMixin()
        payload: dict[str, str] = {}
        customers = [ResolvedCustomer(customer_id="C001", customer_name="TestCo")]
        svc._apply_client_payload(payload=payload, customers=customers)
        assert payload["project_cus_id"] == "C001"
        assert payload["project_cus_name"] == "TestCo"
        assert len([k for k in payload if "pro_customer_id_" in k]) == 1

    def test_apply_empty_customers(self):
        svc = HttpFilingMixin()
        payload: dict[str, str] = {}
        svc._apply_client_payload(payload=payload, customers=[])
        assert payload == {}


class TestHttpFilingMixinApplyConflictPayload:
    def test_apply_conflict(self):
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import ConflictPartyInfo

        svc = HttpFilingMixin()
        payload: dict[str, str] = {}
        parties = [ConflictPartyInfo(name="Opponent", category="B", legal_position="D", customer_type="A", is_payer="0")]
        svc._apply_conflict_payload(payload=payload, parties=parties)
        assert len([k for k in payload if "pro_pci_name_" in k]) == 1


class TestHttpFilingMixinApplyContractPayload:
    def test_apply_contract(self):
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import ContractInfo

        svc = HttpFilingMixin()
        payload: dict[str, str] = {}
        contract = ContractInfo(rec_type="R", currency="CNY", contract_type="L", is_free="0", stamp_count=2)
        svc._apply_contract_payload(payload=payload, contract_info=contract)
        assert len([k for k in payload if "project_stamp_count" in k]) == 1
