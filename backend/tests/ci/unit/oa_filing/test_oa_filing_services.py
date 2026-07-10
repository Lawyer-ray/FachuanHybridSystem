"""Tests for oa_filing services - HTML parser, client import, case import, http filing."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# ---------------------------------------------------------------------------
# html_parser pure functions
# ---------------------------------------------------------------------------

class TestHtmlParserNormalizeText:
    def test_none_returns_empty(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import normalize_text
        assert normalize_text(None) == ""

    def test_whitespace_collapsed(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import normalize_text
        assert normalize_text("  hello   world  ") == "hello world"

    def test_nbsp_replaced(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import normalize_text
        result = normalize_text("hello\xa0world")
        assert "\xa0" not in result


class TestHtmlParserNormalizeLabel:
    def test_removes_colons(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import normalize_label
        assert normalize_label("案件名称：") == "案件名称"

    def test_removes_spaces(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import normalize_label
        assert normalize_label("案件 名称") == "案件名称"


class TestHtmlParserExtractHiddenInput:
    def test_found(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_hidden_input
        html = '<input name="CSRFToken" value="abc123" />'
        assert extract_hidden_input(html, "CSRFToken") == "abc123"

    def test_not_found(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_hidden_input
        assert extract_hidden_input("<html></html>", "missing") == ""


class TestHtmlParserExtractCaseNo:
    def test_standard_case_no(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_case_no_from_text

        # Pattern: digit year + letters + digits
        result = extract_case_no_from_text("案件编号 2024abc001 号")
        assert result == "2024abc001"

    def test_empty_text(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_case_no_from_text
        assert extract_case_no_from_text("") == ""


class TestHtmlParserExtractKeyid:
    def test_from_href(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_keyid_from_href
        result = extract_keyid_from_href("projectView.aspx?keyid=ABC123&FirstModel=PROJECT")
        assert result == "ABC123"

    def test_empty_href(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_keyid_from_href
        assert extract_keyid_from_href("") is None

    def test_none_href(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_keyid_from_href
        assert extract_keyid_from_href(None) is None


class TestHtmlParserScoreCaseNameCell:
    def test_empty_text(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import score_case_name_cell
        assert score_case_name_cell("", case_no="X") == -100

    def test_digit_only(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import score_case_name_cell
        assert score_case_name_cell("12345", case_no="") == -90

    def test_action_word(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import score_case_name_cell
        assert score_case_name_cell("查看", case_no="") == -80

    def test_contains_sue_boosts_score(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import score_case_name_cell
        score = score_case_name_cell("张某诉李某借款纠纷", case_no="")
        assert score > 0

    def test_case_no_match(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import score_case_name_cell
        score = score_case_name_cell("2024民初001 张某诉李某", case_no="2024民初001")
        assert score >= 30


class TestHtmlParserCleanCaseName:
    def test_removes_markers(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import clean_case_name_text
        result = clean_case_name_text("[诉讼]张某诉李某", case_no="")
        assert "[诉讼]" not in result

    def test_removes_case_no(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import clean_case_name_text
        result = clean_case_name_text("2024民初001 张某诉李某", case_no="2024民初001")
        assert "2024民初001" not in result

    def test_empty(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import clean_case_name_text
        assert clean_case_name_text("", case_no="") == ""


class TestHtmlParserIterLabelValuePairs:
    def test_pairs(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import iter_label_value_pairs
        result = iter_label_value_pairs(["案件名称", "张某诉李某", "阶段", "一审"])
        assert len(result) == 2
        assert result[0][0] == "案件名称"


class TestHtmlParserExtractCustomers:
    def test_extracts_customer(self):
        from lxml import html as lxml_html

        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_customers_from_html
        html = """
        <div id="tab_con_1">
            <tr><td>客户（某公司）信息</td></tr>
            <tr><td>客户类型：</td><td>企业</td></tr>
            <tr><td>地址：</td><td>北京市</td></tr>
        </div>"""
        root = lxml_html.fromstring(html)
        customers = extract_customers_from_html(root)
        assert len(customers) >= 1
        assert customers[0].name == "某公司"

    def test_empty_tab(self):
        from lxml import html as lxml_html

        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_customers_from_html
        root = lxml_html.fromstring('<div id="tab_con_1"></div>')
        assert extract_customers_from_html(root) == []


class TestHtmlParserExtractCaseInfo:
    def test_extracts_fields(self):
        from lxml import html as lxml_html

        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_case_info_from_html
        html = """
        <div id="tab_con_2">
            <tr><td>案件名称：</td><td>张某诉李某</td></tr>
            <tr><td>案件阶段：</td><td>一审</td></tr>
            <tr><td>案件负责人：</td><td>王律师</td></tr>
        </div>"""
        root = lxml_html.fromstring(html)
        info = extract_case_info_from_html(root, fallback_case_no="2024-001")
        assert info.case_name == "张某诉李某"
        assert info.case_stage == "一审"
        assert info.responsible_lawyer == "王律师"


class TestHtmlParserExtractConflicts:
    def test_extracts_conflict(self):
        from lxml import html as lxml_html

        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_conflicts_from_html
        html = """
        <div id="tab_con_3">
            <tr><td>中文名称：</td><td>对方公司</td></tr>
            <tr><td>法律地位：</td><td>被告</td></tr>
        </div>"""
        root = lxml_html.fromstring(html)
        conflicts = extract_conflicts_from_html(root)
        assert len(conflicts) == 1
        assert conflicts[0].name == "对方公司"


class TestHtmlParserExtractKeyidFromSearchHtml:
    def test_finds_keyid(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_case_keyid_from_search_html
        html = '<tr><td>2024民初001</td><td><a href="projectView.aspx?keyid=XYZ789">查看</a></td></tr>'
        result = extract_case_keyid_from_search_html(html_text=html, case_no="2024民初001")
        assert result == "XYZ789"

    def test_not_found(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_case_keyid_from_search_html
        result = extract_case_keyid_from_search_html(html_text="<html></html>", case_no="999")
        assert result is None


class TestHtmlParserExtractCandidates:
    def test_extracts_candidates(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import (
            extract_case_candidates_from_search_html,
        )
        html = """<table><tr>
            <td>1</td><td>2024民初001</td>
            <td><a href="projectView.aspx?keyid=AAA111&FirstModel=PROJECT">张某诉李某</a></td>
        </tr></table>"""
        candidates = extract_case_candidates_from_search_html(html)
        assert len(candidates) >= 1
        assert candidates[0].keyid == "AAA111"

    def test_empty_html(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import (
            extract_case_candidates_from_search_html,
        )
        assert extract_case_candidates_from_search_html("") == []


# ---------------------------------------------------------------------------
# client_import pure functions
# ---------------------------------------------------------------------------

class TestClientImportNormalizeText:
    def test_normalize(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript._normalize_text("  hello  ") == "hello"
        assert JtnClientImportScript._normalize_text(None) == ""


class TestClientImportToInt:
    def test_int_value(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript._to_int(42) == 42

    def test_string_value(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript._to_int("123") == 123

    def test_none_value(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript._to_int(None) == 0

    def test_invalid_string(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript._to_int("abc") == 0


class TestClientImportResolveDetailWorkers:
    def test_single_item(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        script = JtnClientImportScript("user", "pass")
        assert script._resolve_detail_workers(total=1) == 1

    def test_multiple_items(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        script = JtnClientImportScript("user", "pass")
        workers = script._resolve_detail_workers(total=20)
        assert workers >= 1


class TestClientImportResolveTotalPages:
    def test_zero_total(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript("u", "p")._resolve_total_pages(0, 20) == 0

    def test_normal(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript("u", "p")._resolve_total_pages(25, 20) == 2


class TestClientImportParseCustomerDetailText:
    def test_parses_id_number(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        script = JtnClientImportScript("u", "p")
        text = "身份证号码：110101199001011234 性别：男 联系电话：13800138000"
        data = script._parse_customer_detail_text("测试", "natural", text)
        assert data.id_number == "110101199001011234"
        assert data.gender == "男"
        assert data.phone == "13800138000"

    def test_parses_legal_representative(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        script = JtnClientImportScript("u", "p")
        text = "法定代表人：张三\n地址：北京市朝阳区"
        data = script._parse_customer_detail_text("某公司", "legal", text)
        assert data.legal_representative == "张三"
        assert data.address == "北京市朝阳区"

    def test_empty_text(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        data = JtnClientImportScript("u", "p")._parse_customer_detail_text("客户", "natural", "")
        assert data.name == "客户"
        assert data.phone is None


class TestClientImportValidPhone:
    def test_valid(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript("u", "p")._is_valid_phone("13800138000") is True

    def test_short(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript("u", "p")._is_valid_phone("123") is False

    def test_none(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript("u", "p")._is_valid_phone(None) is False


class TestClientImportValidFieldValue:
    def test_invalid_values(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        script = JtnClientImportScript("u", "p")
        for val in ("/", "-", "--", "N/A", "无", None):
            assert script._is_valid_field_value(val) is False

    def test_valid(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript("u", "p")._is_valid_field_value("北京市") is True


class TestClientImportExtractKeyIdFromHref:
    def test_found(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        result = JtnClientImportScript("u", "p")._extract_key_id_from_href("CustomerInfor.aspx?KeyID=ABC&Category=A")
        assert result == "ABC"

    def test_empty(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        assert JtnClientImportScript("u", "p")._extract_key_id_from_href("") is None


class TestClientImportEmitProgress:
    def test_no_callback(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        JtnClientImportScript("u", "p")._emit_progress("test_event", key="value")

    def test_with_callback(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        callback = MagicMock()
        JtnClientImportScript("u", "p", progress_callback=callback)._emit_progress("evt", k="v")
        callback.assert_called_once()


class TestClientImportExtractCustomerRows:
    def test_extracts_rows(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        html = """<table id="table">
            <tr><th>a</th><th>b</th><th>c</th><th>d</th><th>e</th></tr>
            <tr><td>1</td><td>C001</td><td><a href="CustomerInfor.aspx?KeyID=K001&Category=A">某公司</a></td><td>A</td><td>企业</td></tr>
        </table>"""
        items = JtnClientImportScript("u", "p")._extract_customer_rows_from_html(html)
        assert len(items) == 1
        assert items[0].name == "某公司"
        assert items[0].client_type == "legal"
        assert items[0].key_id == "K001"

    def test_empty_table(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        html = '<table id="table"><tr><th>H</th></tr></table>'
        assert JtnClientImportScript("u", "p")._extract_customer_rows_from_html(html) == []


class TestClientImportExtractClientListFormState:
    def test_extracts_form(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        html = """<html><body><form id="aspnetForm" action="/customer/index.aspx">
            <input name="hf" value="v1" type="hidden" />
            <select name="sel"><option value="o1" selected>O1</option></select>
        </form></body></html>"""
        state = JtnClientImportScript("u", "p")._extract_client_list_form_state(
            html_text=html, base_url="https://ims.jtn.com/customer/")
        assert "hf" in state.payload
        assert state.payload["hf"] == "v1"

    def test_missing_form_raises(self):
        from apps.oa_filing.services.oa_scripts.jtn.client_import.service import JtnClientImportScript
        with pytest.raises(RuntimeError, match="aspnetForm"):
            JtnClientImportScript("u", "p")._extract_client_list_form_state(
                html_text="<html></html>", base_url="https://x.com/")


# ---------------------------------------------------------------------------
# case_import_service pure functions
# ---------------------------------------------------------------------------

class TestCaseImportServiceMapCaseType:
    def _make_service(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        session = MagicMock()
        session.credential = MagicMock(account="u", password="p")
        return CaseImportService(session)

    def test_map_civil(self):
        assert self._make_service()._map_oa_case_type("民事", None) == "civil"

    def test_map_criminal(self):
        assert self._make_service()._map_oa_case_type("刑事", None) == "criminal"

    def test_map_administrative(self):
        assert self._make_service()._map_oa_case_type("行政", None) == "administrative"

    def test_map_labor(self):
        assert self._make_service()._map_oa_case_type("劳动仲裁", None) == "labor"

    def test_map_code_01(self):
        assert self._make_service()._map_oa_case_type("01", None) == "advisor"

    def test_map_empty(self):
        assert self._make_service()._map_oa_case_type(None, None) is None

    def test_map_unrecognized(self):
        assert self._make_service()._map_oa_case_type("未知类型", None) is None


class TestCaseImportServiceShouldCreateCase:
    def _make_service(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        session = MagicMock()
        session.credential = MagicMock()
        return CaseImportService(session)

    def test_dispute_type(self):
        svc = self._make_service()
        assert svc._should_create_case_for_contract_type("civil") is True
        assert svc._should_create_case_for_contract_type("criminal") is True

    def test_advisor_type(self):
        assert self._make_service()._should_create_case_for_contract_type("advisor") is False

    def test_none(self):
        assert self._make_service()._should_create_case_for_contract_type(None) is False


class TestCaseImportServiceParseDate:
    def test_iso(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        r = CaseImportService._parse_date("2024-01-15")
        assert r is not None and r.year == 2024

    def test_slash(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        assert CaseImportService._parse_date("2024/01/15") is not None

    def test_chinese(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        assert CaseImportService._parse_date("2024年01月15日") is not None

    def test_empty(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        assert CaseImportService._parse_date("") is None

    def test_invalid(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        assert CaseImportService._parse_date("not-a-date") is None


class TestCaseImportServiceCheckConflicts:
    def test_returns_warnings(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        from apps.oa_filing.services.oa_scripts.jtn.case_import import OAConflictData
        session = MagicMock()
        session.credential = MagicMock()
        svc = CaseImportService(session)
        conflicts = [OAConflictData(name="对方公司", conflict_type="被告")]
        warnings = svc._check_conflicts(conflicts)
        assert len(warnings) == 1
        assert "对方公司" in warnings[0]


class TestCaseImportServiceImportSingleCaseData:
    def test_no_oa_data_returns_error(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        session = MagicMock()
        session.credential = MagicMock()
        svc = CaseImportService(session)
        result = svc._import_single_case_data("2024-001", None)
        assert result.status == "error"

    def test_resolve_search_workers_single(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        session = MagicMock()
        session.credential = MagicMock()
        svc = CaseImportService(session)
        assert svc._resolve_search_workers(1) == 1


# ---------------------------------------------------------------------------
# http_filing mixin pure functions
# ---------------------------------------------------------------------------

class TestHttpFilingMixin:
    def _make_mixin(self):
        from apps.oa_filing.services.oa_scripts.jtn.filing.http_filing import HttpFilingMixin
        return HttpFilingMixin()

    def test_project_field_name(self):
        assert "project_manager_id" in self._make_mixin()._project_field_name("manager_id")

    def test_handler_url(self):
        assert "CustSeachGetList" in self._make_mixin()._handler_url("CustSeachGetList")

    def test_parse_json_object_valid(self):
        assert self._make_mixin()._parse_json_object('{"key": "value"}') == {"key": "value"}

    def test_parse_json_object_invalid(self):
        with pytest.raises(RuntimeError):
            self._make_mixin()._parse_json_object('[1, 2]')

    def test_normalize_text(self):
        assert self._make_mixin()._normalize_text("  hello  ") == "hello"

    def test_assert_success_marker(self):
        self._make_mixin()._assert_http_submit_success("案件保存未提交成功")

    def test_assert_failure_alert(self):
        with pytest.raises(RuntimeError, match="HTTP 立案失败"):
            self._make_mixin()._assert_http_submit_success("alert('失败')")

    def test_assert_failure_no_marker(self):
        with pytest.raises(RuntimeError, match="未检测到成功标记"):
            self._make_mixin()._assert_http_submit_success("<html>random</html>")

    def test_resolve_manager_id_from_form(self):
        mixin = self._make_mixin()
        html = """<select name="ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$project_manager_id">
            <option value="100">王律师</option>
            <option value="200">李律师</option>
        </select>"""
        result = mixin._resolve_manager_id_from_form(html_text=html, manager_name="王律师")
        assert result == "100"

    def test_resolve_manager_id_not_found(self):
        mixin = self._make_mixin()
        html = '<select><option value="100">王律师</option></select>'
        result = mixin._resolve_manager_id_from_form(html_text=html, manager_name="不存在")
        assert result is None

    def test_extract_filing_form_state(self):
        mixin = self._make_mixin()
        html = '<form id="aspnetForm" action="/filing.aspx"><input name="field1" value="v1" /></form>'
        state = mixin._extract_filing_form_state(html_text=html, base_url="https://ims.jtn.com/")
        assert state.action_url == "https://ims.jtn.com/filing.aspx"
        assert state.payload["field1"] == "v1"

    def test_extract_filing_form_state_missing_form(self):
        mixin = self._make_mixin()
        with pytest.raises(RuntimeError, match="aspnetForm"):
            mixin._extract_filing_form_state(html_text="<html></html>", base_url="https://x.com/")


# ---------------------------------------------------------------------------
# http_client mixin pure functions
# ---------------------------------------------------------------------------

class TestHttpClientMixin:
    def test_is_login_failed_stayed_on_login(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.http_client import JtnHttpClientMixin
        mixin = JtnHttpClientMixin()
        response = MagicMock()
        type(response).url = PropertyMock(return_value="https://ims.jtn.com/member/login.aspx")
        response.text = '<input name="userid" /><input name="password" />'
        assert mixin._is_login_failed_response(response) is True

    def test_is_login_failed_error_text(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.http_client import JtnHttpClientMixin
        mixin = JtnHttpClientMixin()
        response = MagicMock()
        type(response).url = PropertyMock(return_value="https://ims.jtn.com/somepage")
        response.text = "账号或密码错误"
        assert mixin._is_login_failed_response(response) is True

    def test_is_login_failed_success(self):
        from apps.oa_filing.services.oa_scripts.jtn.case_import.http_client import JtnHttpClientMixin
        mixin = JtnHttpClientMixin()
        response = MagicMock()
        type(response).url = PropertyMock(return_value="https://ims.jtn.com/dashboard")
        response.text = "<html>Welcome</html>"
        assert mixin._is_login_failed_response(response) is False
