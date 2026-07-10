"""Tests for oa_filing html_parser module-level pure functions."""

from __future__ import annotations

from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import (
    clean_case_name_text,
    extract_case_no_from_text,
    extract_hidden_input,
    extract_keyid_from_href,
    iter_label_value_pairs,
    normalize_label,
    normalize_text,
    score_case_name_cell,
)


class TestNormalizeText:
    def test_whitespace(self) -> None:
        assert normalize_text("  hello  world  ") == "hello world"

    def test_nbsp(self) -> None:
        assert normalize_text("hello\xa0world") == "hello world"

    def test_fullwidth_space(self) -> None:
        assert normalize_text("hello　world") == "hello world"

    def test_none(self) -> None:
        assert normalize_text(None) == ""

    def test_empty(self) -> None:
        assert normalize_text("") == ""


class TestNormalizeLabel:
    def test_removes_colons(self) -> None:
        assert normalize_label("客户名称：") == "客户名称"
        assert normalize_label("案件编号:") == "案件编号"

    def test_removes_spaces(self) -> None:
        assert normalize_label("案 件 编 号") == "案件编号"


class TestIterLabelValuePairs:
    def test_basic(self) -> None:
        result = iter_label_value_pairs(["客户名称：", "张三", "案件编号：", "001"])
        assert len(result) == 2
        assert result[0] == ("客户名称", "张三")
        assert result[1] == ("案件编号", "001")

    def test_odd_length(self) -> None:
        result = iter_label_value_pairs(["label", "value", "extra"])
        assert len(result) == 1

    def test_empty(self) -> None:
        assert iter_label_value_pairs([]) == []


class TestExtractHiddenInput:
    def test_basic(self) -> None:
        html = '<input name="key1" value="val1" type="hidden">'
        result = extract_hidden_input(html, "key1")
        assert result == "val1"

    def test_not_found(self) -> None:
        html = '<input name="other" value="val">'
        result = extract_hidden_input(html, "key1")
        assert result == ""


class TestExtractCaseNoFromText:
    def test_standard_case_no(self) -> None:
        result = extract_case_no_from_text("案件编号：2024JD010512345")
        assert result == "2024JD010512345"

    def test_simple_digits(self) -> None:
        result = extract_case_no_from_text("编号 2024010512345 号")
        assert result == "2024010512345"

    def test_no_match(self) -> None:
        result = extract_case_no_from_text("无编号信息")
        assert result == ""

    def test_empty(self) -> None:
        assert extract_case_no_from_text("") == ""


class TestExtractKeyidFromHref:
    def test_basic(self) -> None:
        result = extract_keyid_from_href("projectView.aspx?keyid=abc123&FirstModel=PROJECT")
        assert result == "abc123"

    def test_no_keyid(self) -> None:
        result = extract_keyid_from_href("other.aspx?id=123")
        assert result is None

    def test_empty(self) -> None:
        assert extract_keyid_from_href("") is None


class TestScoreCaseNameCell:
    def test_with_case_no(self) -> None:
        score = score_case_name_cell("张三诉李四买卖合同纠纷案", case_no="2024京民初1")
        assert score > 0

    def test_action_button(self) -> None:
        score = score_case_name_cell("查看", case_no="")
        assert score < 0

    def test_date_format(self) -> None:
        score = score_case_name_cell("2024-01-15", case_no="")
        assert score < 0

    def test_empty(self) -> None:
        score = score_case_name_cell("", case_no="")
        assert score == -100

    def test_with_lawsuit_marker(self) -> None:
        score = score_case_name_cell("张三诉李四案", case_no="")
        assert score >= 20


class TestCleanCaseNameText:
    def test_removes_case_no(self) -> None:
        result = clean_case_name_text("2024京民初1号张三诉李四", case_no="2024京民初1号")
        assert "2024京民初1号" not in result

    def test_removes_action_words(self) -> None:
        result = clean_case_name_text("案件名称查看编辑删除", case_no="")
        assert "查看" not in result
        assert "编辑" not in result

    def test_removes_status_markers(self) -> None:
        result = clean_case_name_text("张三诉李四[诉讼]民商事案件", case_no="")
        assert "[诉讼]" not in result

    def test_empty(self) -> None:
        assert clean_case_name_text("", case_no="") == ""
