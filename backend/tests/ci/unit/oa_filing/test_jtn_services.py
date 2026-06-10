"""JTN OA filing services tests with mocked HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.oa_filing.services.oa_scripts.jtn.html_parser import (
    clean_case_name_text,
    extract_case_candidates_from_search_html,
    extract_case_keyid_from_search_html,
    extract_case_no_from_text,
    extract_hidden_input,
    extract_keyid_from_href,
    extract_row_cells_text,
    iter_label_value_pairs,
    normalize_label,
    normalize_text,
    parse_case_detail_html,
    score_case_name_cell,
)


class TestHtmlParserNormalize:
    def test_normalize_text_basic(self):
        assert normalize_text("  hello  world  ") == "hello world"

    def test_normalize_text_none(self):
        assert normalize_text(None) == ""

    def test_normalize_text_nbsp(self):
        result = normalize_text("hello\xa0world")
        assert "\xa0" not in result

    def test_normalize_label(self):
        assert normalize_label("案件名称：") == "案件名称"
        assert normalize_label("案件名称: ") == "案件名称"


class TestHtmlParserExtraction:
    def test_extract_hidden_input(self):
        html = '<input name="CSRFToken" value="abc123" type="hidden"/>'
        assert extract_hidden_input(html, "CSRFToken") == "abc123"

    def test_extract_hidden_input_not_found(self):
        assert extract_hidden_input("<html></html>", "missing") == ""

    def test_extract_case_no_from_text(self):
        # The regex matches digits-only patterns or letter+digit patterns
        assert extract_case_no_from_text("案号2024123456号") == "2024123456"

    def test_extract_case_no_from_text_empty(self):
        assert extract_case_no_from_text("") == ""

    def test_extract_keyid_from_href(self):
        href = "projectView.aspx?keyid=ABC123&FirstModel=PROJECT"
        result = extract_keyid_from_href(href)
        assert result == "ABC123"

    def test_extract_keyid_from_href_none(self):
        assert extract_keyid_from_href("") is None

    def test_extract_row_cells_text(self):
        from lxml import html as lxml_html

        root = lxml_html.fromstring("<tr><td>A</td><td>B</td></tr>")
        row = root.xpath("//tr")[0]
        result = extract_row_cells_text(row)
        assert result == ["A", "B"]

    def test_iter_label_value_pairs(self):
        result = iter_label_value_pairs(["案件名称", "张三诉李四", "案件阶段", "一审"])
        assert len(result) == 2
        assert result[0] == ("案件名称", "张三诉李四")
        assert result[1] == ("案件阶段", "一审")


class TestScoreCaseNameCell:
    def test_score_case_name_cell_with_case_no(self):
        score = score_case_name_cell("张三诉李四买卖合同纠纷2024京123号", case_no="2024京123")
        assert score > 0

    def test_score_case_name_cell_digit_only(self):
        score = score_case_name_cell("12345", case_no="")
        assert score < 0

    def test_score_case_name_cell_action_word(self):
        score = score_case_name_cell("查看", case_no="")
        assert score < 0

    def test_score_case_name_cell_empty(self):
        score = score_case_name_cell("", case_no="")
        assert score < 0

    def test_score_case_name_cell_dispute(self):
        score = score_case_name_cell("买卖合同纠纷一案", case_no="")
        assert score > 0


class TestCleanCaseNameText:
    def test_clean_case_name_text_basic(self):
        result = clean_case_name_text("张三诉李四买卖合同纠纷", case_no="")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_clean_case_name_text_removes_case_no(self):
        result = clean_case_name_text("2024京123号 张三诉李四", case_no="2024京123")
        assert "2024京123" not in result

    def test_clean_case_name_text_removes_markers(self):
        result = clean_case_name_text("张三诉李四[诉讼]民商事案件已完善", case_no="")
        assert "[诉讼]" not in result
        assert "民商事案件" not in result

    def test_clean_case_name_text_empty(self):
        assert clean_case_name_text("", case_no="") == ""


class TestExtractCaseCandidatesFromSearchHtml:
    def test_extract_candidates_basic(self):
        html = """
        <table><tr>
            <td>2024京0105民初123号</td>
            <td><a href="projectView.aspx?keyid=K001&FirstModel=PROJECT">张三诉李四买卖合同纠纷</a></td>
        </tr></table>
        """
        candidates = extract_case_candidates_from_search_html(html)
        assert len(candidates) >= 1
        assert candidates[0].keyid == "K001"

    def test_extract_candidates_empty_html(self):
        candidates = extract_case_candidates_from_search_html("<html></html>")
        assert candidates == []


class TestExtractCaseKeyidFromSearchHtml:
    def test_extract_keyid_found(self):
        html = '<tr><td>2024京123号</td><td><a href="projectView.aspx?keyid=KEY1">详情</a></td></tr>'
        result = extract_case_keyid_from_search_html(html_text=html, case_no="2024京123")
        assert result == "KEY1"

    def test_extract_keyid_not_found(self):
        result = extract_case_keyid_from_search_html(html_text="<html></html>", case_no="2024京123")
        assert result is None


class TestParseCaseDetailHtml:
    def test_parse_case_detail_basic(self):
        html = """
        <html><body>
        <div id="tab_con_1">
            <tr><td>客户（张三）信息</td></tr>
            <tr><td>客户类型：</td><td>自然人</td><td>身份证：</td><td>110101</td></tr>
        </div>
        <div id="tab_con_2">
            <tr><td>案件名称：</td><td>买卖合同纠纷</td><td>案件阶段：</td><td>一审</td></tr>
        </div>
        <div id="tab_con_3"></div>
        </body></html>
        """
        result = parse_case_detail_html(html_text=html, case_no="2024京123", keyid="K001")
        assert result is not None
        assert result.case_no == "2024京123"
        assert result.keyid == "K001"
        assert len(result.customers) >= 1
        assert result.customers[0].name == "张三"

    def test_parse_case_detail_empty(self):
        result = parse_case_detail_html(html_text="<html></html>", case_no="X", keyid="Y")
        assert result is not None
        assert result.customers == []
