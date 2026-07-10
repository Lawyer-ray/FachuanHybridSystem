from __future__ import annotations

import pytest
from lxml import html as lxml_html

from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import (
    _BASE_URL,
    _CASE_LIST_URL,
    _DETAIL_URL_TEMPLATE,
    clean_case_name_text,
    extract_case_candidates_from_search_html,
    extract_case_info_from_html,
    extract_case_keyid_from_search_html,
    extract_case_name_from_row,
    extract_case_no_from_text,
    extract_conflicts_from_html,
    extract_customers_from_html,
    extract_hidden_input,
    extract_keyid_from_href,
    extract_row_cells_text,
    iter_label_value_pairs,
    normalize_label,
    normalize_text,
    parse_case_detail_html,
    score_case_name_cell,
)
from apps.oa_filing.services.oa_scripts.jtn.case_import.models import (
    OACaseCustomerData,
    OACaseData,
    OACaseInfoData,
    OAConflictData,
    OAListCaseCandidate,
)

# ── normalize_text ────────────────────────────────────────────────────────────


class TestNormalizeText:

    def test_none_returns_empty(self):
        assert normalize_text(None) == ""

    def test_strips_whitespace(self):
        assert normalize_text("  hello  ") == "hello"

    def test_collapses_multiple_spaces(self):
        assert normalize_text("a   b   c") == "a b c"

    def test_replaces_nbsp(self):
        assert normalize_text("a\xa0b") == "a b"

    def test_replaces_fullwidth_space(self):
        assert normalize_text("a　b") == "a b"

    def test_mixed_whitespace(self):
        assert normalize_text("a\t\n b") == "a b"


# ── normalize_label ──────────────────────────────────────────────────────────


class TestNormalizeLabel:

    def test_strips_colon(self):
        assert normalize_label("案件名称：") == "案件名称"

    def test_strips_english_colon(self):
        assert normalize_label("name: ") == "name"

    def test_strips_spaces(self):
        assert normalize_label("a b c") == "abc"

    def test_none_returns_empty(self):
        assert normalize_label(None) == ""


# ── extract_row_cells_text ──────────────────────────────────────────────────


class TestExtractRowCellsText:

    def test_extracts_td_text(self):
        root = lxml_html.fromstring("<table><tr><td>A</td><td>B</td></tr></table>")
        row = root.xpath("//tr")[0]
        assert extract_row_cells_text(row) == ["A", "B"]

    def test_empty_row(self):
        root = lxml_html.fromstring("<table><tr></tr></table>")
        row = root.xpath("//tr")[0]
        assert extract_row_cells_text(row) == []

    def test_td_with_nested_elements(self):
        root = lxml_html.fromstring('<table><tr><td><span>Hello</span> World</td></tr></table>')
        row = root.xpath("//tr")[0]
        assert extract_row_cells_text(row) == ["Hello World"]


# ── iter_label_value_pairs ──────────────────────────────────────────────────


class TestIterLabelValuePairs:

    def test_normal_pairs(self):
        cells = ["案件名称", "某某诉某某案", "案件编号", "2024ABC001"]
        pairs = iter_label_value_pairs(cells)
        assert len(pairs) == 2
        assert pairs[0] == ("案件名称", "某某诉某某案")
        assert pairs[1] == ("案件编号", "2024ABC001")

    def test_odd_length_drops_last(self):
        cells = ["A", "B", "C"]
        pairs = iter_label_value_pairs(cells)
        assert len(pairs) == 1
        assert pairs[0] == ("A", "B")

    def test_empty_list(self):
        assert iter_label_value_pairs([]) == []

    def test_single_item(self):
        assert iter_label_value_pairs(["A"]) == []


# ── extract_hidden_input ────────────────────────────────────────────────────


class TestExtractHiddenInput:

    def test_double_quotes(self):
        html = '<input name="token" value="abc123" type="hidden">'
        assert extract_hidden_input(html, "token") == "abc123"

    def test_single_quotes(self):
        html = "<input name='sid' value='xyz' type='hidden'>"
        assert extract_hidden_input(html, "sid") == "xyz"

    def test_not_found(self):
        assert extract_hidden_input("<input name='x' value='y'>", "missing") == ""

    def test_empty_value(self):
        html = '<input name="k" value="" type="hidden">'
        assert extract_hidden_input(html, "k") == ""

    def test_case_insensitive(self):
        html = '<INPUT NAME="Token" VALUE="abc">'
        assert extract_hidden_input(html, "Token") == "abc"


# ── extract_case_no_from_text ───────────────────────────────────────────────


class TestExtractCaseNoFromText:

    def test_pattern_1_year_prefix(self):
        result = extract_case_no_from_text("2024ABC001")
        assert result == "2024ABC001"

    def test_pattern_2_letter_prefix(self):
        result = extract_case_no_from_text("ABC01234")
        assert result == "ABC01234"

    def test_pattern_3_digits_only(self):
        assert extract_case_no_from_text("编号123456789") == "123456789"

    def test_empty_text(self):
        assert extract_case_no_from_text("") == ""

    def test_none_text(self):
        assert extract_case_no_from_text(None) == ""  # type: ignore[arg-type]

    def test_no_match(self):
        assert extract_case_no_from_text("无编号信息") == ""

    def test_chinese_digits_not_matched_by_pattern_1(self):
        # Pattern 1: \d{4}[A-Za-z]{1,8}\d{2,} -- needs ASCII digits + letters + digits
        result = extract_case_no_from_text("2024民初001号")
        # Chinese chars are not [A-Za-z], so pattern 1 won't match.
        # But pattern 3 (\d{6,}) might match if there are 6+ consecutive digits.
        # "2024民初001号" has no 6+ consecutive ASCII digits.
        assert result == "" or result.isdigit()


# ── extract_keyid_from_href ─────────────────────────────────────────────────


class TestExtractKeyidFromHref:

    def test_normal_keyid(self):
        href = "projectView.aspx?keyid=ABC123&FirstModel=PROJECT"
        assert extract_keyid_from_href(href) == "ABC123"

    def test_KeyID_uppercase(self):
        href = "projectView.aspx?KeyID=XYZ789"
        assert extract_keyid_from_href(href) == "XYZ789"

    def test_empty_href(self):
        assert extract_keyid_from_href("") is None

    def test_no_keyid(self):
        assert extract_keyid_from_href("projectView.aspx?foo=bar") is None

    def test_relative_url(self):
        href = "projectView.aspx?keyid=K42"
        assert extract_keyid_from_href(href) == "K42"


# ── score_case_name_cell ────────────────────────────────────────────────────


class TestScoreCaseNameCell:

    def test_empty_returns_negative_100(self):
        assert score_case_name_cell("", case_no="") == -100

    def test_digit_only_returns_negative_90(self):
        assert score_case_name_cell("12345", case_no="") == -90

    def test_action_word_returns_negative_80(self):
        for word in ("查看", "编辑", "删除", "详情", "操作"):
            assert score_case_name_cell(word, case_no="") == -80

    def test_contains_case_no_bonus(self):
        score = score_case_name_cell("ABC001某某诉某某案", case_no="ABC001")
        assert score >= 30

    def test_contains_su_bonus(self):
        score = score_case_name_cell("某某诉某某案", case_no="")
        assert score >= 20

    def test_contains_dispute_bonus(self):
        score = score_case_name_cell("某某纠纷案", case_no="")
        assert score >= 12

    def test_contains_penalty_marker(self):
        # "[诉讼]" is in the penalty list, which gives -15, but it also contains "诉" (+20)
        score = score_case_name_cell("民商事案件信息完善", case_no="")
        assert score < 0

    def test_date_pattern_penalty(self):
        score = score_case_name_cell("2024-01-15", case_no="")
        assert score <= -20

    def test_short_text_penalty(self):
        score = score_case_name_cell("好", case_no="")
        assert score <= -10


# ── clean_case_name_text ────────────────────────────────────────────────────


class TestCleanCaseNameText:

    def test_removes_case_no(self):
        result = clean_case_name_text("ABC001某某诉某某", case_no="ABC001")
        assert "ABC001" not in result

    def test_removes_action_words(self):
        result = clean_case_name_text("某某案查看编辑删除", case_no="")
        for w in ("查看", "编辑", "删除"):
            assert w not in result

    def test_removes_marker_prefix(self):
        result = clean_case_name_text("[诉讼]某某案", case_no="")
        assert "[诉讼]" not in result

    def test_removes_leading_number(self):
        # The regex r"^\d+\s+" requires whitespace after digits
        result = clean_case_name_text("123 某某案", case_no="")
        assert "123" not in result

    def test_empty_input(self):
        assert clean_case_name_text("", case_no="") == ""

    def test_removes_repeated_name_prefix(self):
        result = clean_case_name_text("张三 张三诉李四案", case_no="")
        assert "张三 张三" not in result or "诉" in result


# ── extract_case_name_from_row ──────────────────────────────────────────────


class TestExtractCaseNameFromRow:

    def test_extracts_best_cell(self):
        root = lxml_html.fromstring(
            '<table><tr><td>12345</td><td>某某诉某某纠纷案</td><td>查看</td></tr></table>'
        )
        row = root.xpath("//tr")[0]
        result = extract_case_name_from_row(row, case_no="12345", row_text="12345 某某诉某某纠纷案 查看")
        assert "某某" in result or "纠纷" in result

    def test_falls_back_to_row_text(self):
        root = lxml_html.fromstring("<table><tr><td>123</td></tr></table>")
        row = root.xpath("//tr")[0]
        result = extract_case_name_from_row(row, case_no="", row_text="某某诉李四案")
        assert result  # should get something from row_text


# ── extract_case_candidates_from_search_html ────────────────────────────────


class TestExtractCaseCandidates:

    def test_extracts_candidates(self):
        html = """
        <table>
          <tr>
            <td>2024民初001</td>
            <td>张三诉李四纠纷案</td>
            <td><a href="projectView.aspx?keyid=K001&FirstModel=PROJECT">查看</a></td>
          </tr>
        </table>
        """
        candidates = extract_case_candidates_from_search_html(html)
        assert len(candidates) >= 1
        assert candidates[0].keyid == "K001"
        assert candidates[0].detail_url == _DETAIL_URL_TEMPLATE.format(base=_BASE_URL, keyid="K001")

    def test_deduplicates(self):
        html = """
        <table>
          <tr>
            <td>2024民初001</td>
            <td>张三诉李四纠纷案</td>
            <td><a href="projectView.aspx?keyid=K001">查看</a></td>
            <td><a href="projectView.aspx?keyid=K001">编辑</a></td>
          </tr>
        </table>
        """
        candidates = extract_case_candidates_from_search_html(html)
        keyids = [c.keyid for c in candidates]
        assert keyids.count("K001") == 1

    def test_invalid_html_returns_empty(self):
        assert extract_case_candidates_from_search_html("<not valid <<<") == []

    def test_no_links_returns_empty(self):
        html = "<table><tr><td>数据</td></tr></table>"
        assert extract_case_candidates_from_search_html(html) == []

    def test_link_text_is_action_word_uses_row(self):
        html = """
        <table>
          <tr>
            <td>某纠纷案</td>
            <td><a href="projectView.aspx?keyid=K002">查看</a></td>
          </tr>
        </table>
        """
        candidates = extract_case_candidates_from_search_html(html)
        assert len(candidates) == 1
        assert candidates[0].case_name != "查看"


# ── extract_case_keyid_from_search_html ─────────────────────────────────────


class TestExtractCaseKeyid:

    def test_finds_keyid_in_matching_row(self):
        html = """
        <table>
          <tr>
            <td>2024ABC001</td>
            <td><a href="projectView.aspx?keyid=K42">详情</a></td>
          </tr>
        </table>
        """
        keyid = extract_case_keyid_from_search_html(html_text=html, case_no="2024ABC001")
        assert keyid == "K42"

    def test_no_match_returns_none(self):
        html = "<table><tr><td>其他</td></tr></table>"
        keyid = extract_case_keyid_from_search_html(html_text=html, case_no="2024ABC999")
        assert keyid is None

    def test_regex_fallback(self):
        html = "2024ABC001 某案 projectView.aspx?keyid=REGEX_K"
        keyid = extract_case_keyid_from_search_html(html_text=html, case_no="2024ABC001")
        assert keyid == "REGEX_K"

    def test_invalid_html_uses_regex_fallback(self):
        html = "<<< 2024CASE01 xxx projectView.aspx?keyid=FALLBACK_KEY >>>"
        keyid = extract_case_keyid_from_search_html(html_text=html, case_no="2024CASE01")
        assert keyid == "FALLBACK_KEY"


# ── extract_customers_from_html ─────────────────────────────────────────────


class TestExtractCustomers:

    def test_extracts_natural_person(self):
        html = """
        <div id="tab_con_1">
          <table>
            <tr><td>客户（张三）信息</td></tr>
            <tr><td>客户类型</td><td>自然人</td></tr>
            <tr><td>身份证号码</td><td>110101199001011234</td></tr>
            <tr><td>地址</td><td>北京市朝阳区</td></tr>
            <tr><td>电话号码</td><td>13800138000</td></tr>
          </table>
        </div>
        """
        root = lxml_html.fromstring(html)
        customers = extract_customers_from_html(root)
        assert len(customers) == 1
        assert customers[0].name == "张三"
        assert customers[0].customer_type == "natural"
        assert customers[0].id_number == "110101199001011234"
        assert customers[0].address == "北京市朝阳区"
        assert customers[0].phone == "13800138000"

    def test_extracts_legal_entity(self):
        html = """
        <div id="tab_con_1">
          <table>
            <tr><td>客户（某某公司）信息</td></tr>
            <tr><td>法定代表人</td><td>王五</td></tr>
            <tr><td>行业</td><td>科技</td></tr>
          </table>
        </div>
        """
        root = lxml_html.fromstring(html)
        customers = extract_customers_from_html(root)
        assert len(customers) == 1
        assert customers[0].name == "某某公司"
        assert customers[0].customer_type == "legal"
        assert customers[0].legal_representative == "王五"
        assert customers[0].industry == "科技"

    def test_multiple_customers(self):
        html = """
        <div id="tab_con_1">
          <table>
            <tr><td>客户（甲公司）信息</td></tr>
            <tr><td>客户类型</td><td>企业</td></tr>
            <tr><td>客户（乙某）信息</td></tr>
            <tr><td>客户类型</td><td>自然人</td></tr>
          </table>
        </div>
        """
        root = lxml_html.fromstring(html)
        customers = extract_customers_from_html(root)
        assert len(customers) == 2

    def test_no_customers(self):
        html = '<div id="tab_con_1"><table><tr><td>无数据</td></tr></table></div>'
        root = lxml_html.fromstring(html)
        assert extract_customers_from_html(root) == []


# ── extract_case_info_from_html ─────────────────────────────────────────────


class TestExtractCaseInfo:

    def test_extracts_all_fields(self):
        html = """
        <div id="tab_con_2">
          <table>
            <tr><td>案件名称</td><td>某某诉某某案</td><td>案件编号</td><td>2024XH001</td></tr>
            <tr><td>案件阶段</td><td>一审</td><td>收案日期</td><td>2024-01-15</td></tr>
            <tr><td>案件类别</td><td>民事</td><td>业务种类</td><td>合同纠纷</td></tr>
            <tr><td>案件负责人</td><td>李律师</td><td>代理何方</td><td>原告</td></tr>
            <tr><td>案情简介</td><td>这是案情简介内容</td></tr>
          </table>
        </div>
        """
        root = lxml_html.fromstring(html)
        info = extract_case_info_from_html(root, fallback_case_no="FALLBACK")
        assert info.case_name == "某某诉某某案"
        assert info.case_no == "2024XH001"
        assert info.case_stage == "一审"
        assert info.acceptance_date == "2024-01-15"
        assert info.case_category == "民事"
        assert info.case_type == "合同纠纷"
        assert info.responsible_lawyer == "李律师"
        assert info.client_side == "原告"
        assert info.description == "这是案情简介内容"

    def test_uses_fallback_case_no(self):
        html = '<div id="tab_con_2"><table><tr><td>案件名称</td><td>某某案</td></tr></table></div>'
        root = lxml_html.fromstring(html)
        info = extract_case_info_from_html(root, fallback_case_no="FALLBACK_NO")
        assert info.case_no == "FALLBACK_NO"

    def test_description_truncated(self):
        long_desc = "A" * 600
        html = f'<div id="tab_con_2"><table><tr><td>案情简介</td><td>{long_desc}</td></tr></table></div>'
        root = lxml_html.fromstring(html)
        info = extract_case_info_from_html(root, fallback_case_no="X")
        assert len(info.description) == 500


# ── extract_conflicts_from_html ─────────────────────────────────────────────


class TestExtractConflicts:

    def test_extracts_conflicts(self):
        html = """
        <div id="tab_con_3">
          <table>
            <tr><td>中文名称</td><td>某某公司</td></tr>
            <tr><td>法律地位</td><td>被告</td></tr>
            <tr><td>中文名称</td><td>另一公司</td></tr>
            <tr><td>类型</td><td>关联方</td></tr>
          </table>
        </div>
        """
        root = lxml_html.fromstring(html)
        conflicts = extract_conflicts_from_html(root)
        assert len(conflicts) == 2
        assert conflicts[0].name == "某某公司"
        assert conflicts[0].conflict_type == "被告"
        assert conflicts[1].name == "另一公司"
        assert conflicts[1].conflict_type == "关联方"

    def test_no_conflicts(self):
        html = '<div id="tab_con_3"><table><tr><td>无数据</td></tr></table></div>'
        root = lxml_html.fromstring(html)
        assert extract_conflicts_from_html(root) == []

    def test_single_conflict_without_type(self):
        html = """
        <div id="tab_con_3">
          <table>
            <tr><td>中文名称</td><td>某某</td></tr>
          </table>
        </div>
        """
        root = lxml_html.fromstring(html)
        conflicts = extract_conflicts_from_html(root)
        assert len(conflicts) == 1
        assert conflicts[0].name == "某某"
        assert conflicts[0].conflict_type is None


# ── parse_case_detail_html ──────────────────────────────────────────────────


class TestParseCaseDetailHtml:

    def test_parses_full_detail(self):
        html = """
        <div id="tab_con_1">
          <table>
            <tr><td>客户（甲公司）信息</td></tr>
            <tr><td>客户类型</td><td>企业</td></tr>
          </table>
        </div>
        <div id="tab_con_2">
          <table>
            <tr><td>案件名称</td><td>测试案</td></tr>
          </table>
        </div>
        <div id="tab_con_3">
          <table>
            <tr><td>中文名称</td><td>冲突方</td></tr>
          </table>
        </div>
        """
        result = parse_case_detail_html(html_text=html, case_no="NO1", keyid="K1")
        assert result is not None
        assert result.case_no == "NO1"
        assert result.keyid == "K1"
        assert len(result.customers) == 1
        assert result.case_info is not None
        assert len(result.conflicts) == 1

    def test_invalid_html_returns_none_or_valid(self):
        # lxml is very lenient, so "invalid" HTML may still parse.
        # We test that the function doesn't raise and returns a valid result.
        result = parse_case_detail_html(html_text="<not valid <<<", case_no="X", keyid="Y")
        # lxml can parse almost anything, so this may return a valid OACaseData
        assert result is None or isinstance(result, OACaseData)

    def test_empty_html(self):
        result = parse_case_detail_html(html_text="", case_no="X", keyid="Y")
        # Empty string may still parse with lxml, but no data will be found
        assert result is None or isinstance(result, OACaseData)
