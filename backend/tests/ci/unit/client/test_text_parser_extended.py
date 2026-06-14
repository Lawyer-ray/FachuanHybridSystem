"""
Extended tests for client text_parser.

Covers: _normalize_text, _parse_single_party, _clean_name_candidate,
_is_valid_name_candidate, _extract_phone fallback, _extract_address fallback,
_extract_id_number, _extract_credit_code edge cases, _determine_client_type,
_empty_result, and multi-party parsing.
"""

from __future__ import annotations

import pytest

from apps.client.services.text_parser import (
    _BIRTH_DATE_PATTERN,
    _clean_name_candidate,
    _determine_client_type,
    _empty_result,
    _extract_address,
    _extract_credit_code,
    _extract_id_number,
    _extract_name,
    _extract_name_smart,
    _extract_parties,
    _extract_phone,
    _is_valid_name_candidate,
    _normalize_text,
    _parse_single_party,
    parse_client_text,
    parse_multiple_clients_text,
)


# ═══════════════════════════════════════════════════════════════════════════════
# _normalize_text
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeText:
    def test_carriage_return_normalization(self):
        result = _normalize_text("line1\r\nline2\rline3")
        assert "\r" not in result

    def test_semicolon_to_newline(self):
        result = _normalize_text("甲;乙")
        assert "\n" in result

    def test_full_stop_break(self):
        result = _normalize_text("句号。后面")
        assert "\n" in result

    def test_enumeration_prefix_removal(self):
        result = _normalize_text("一、第一项\n二、第二项")
        assert "一、" not in result
        assert "二、" not in result

    def test_bullet_prefix_removal(self):
        result = _normalize_text("- 项目\n* 项目2\n• 项目3")
        assert "- " not in result

    def test_field_keyword_auto_break(self):
        # "名称：xxx" should have newline inserted before "名称"
        result = _normalize_text("text名称：test")
        assert "名称" in result

    def test_multiple_newlines_collapsed(self):
        result = _normalize_text("a\n\n\n\nb")
        assert "\n\n" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# _empty_result
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmptyResult:
    def test_has_all_keys(self):
        result = _empty_result()
        assert set(result.keys()) == {"name", "phone", "address", "client_type", "id_number", "legal_representative"}

    def test_default_values(self):
        result = _empty_result()
        assert result["name"] == ""
        assert result["phone"] == ""
        assert result["address"] == ""
        assert result["client_type"] == "natural"
        assert result["id_number"] == ""
        assert result["legal_representative"] == ""


# ═══════════════════════════════════════════════════════════════════════════════
# _clean_name_candidate
# ═══════════════════════════════════════════════════════════════════════════════


class TestCleanNameCandidate:
    def test_strips_role_prefix(self):
        result = _clean_name_candidate("被告：张三")
        assert "被告" not in result

    def test_strips_ethnicity_info(self):
        result = _clean_name_candidate("张三，汉族，男")
        assert "汉族" not in result

    def test_strips_birth_date(self):
        result = _clean_name_candidate("张三，1990年1月1日出生")
        assert "1990" not in result

    def test_strips_trailing_gender(self):
        result = _clean_name_candidate("张三，男")
        assert result == "张三"

    def test_strips_trailing_comma_and_semicolon(self):
        result = _clean_name_candidate("，张三，，")
        assert result == "张三"


# ═══════════════════════════════════════════════════════════════════════════════
# _is_valid_name_candidate
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsValidNameCandidate:
    def test_empty_string(self):
        assert not _is_valid_name_candidate("")

    def test_single_char(self):
        assert not _is_valid_name_candidate("张")

    def test_too_long(self):
        assert not _is_valid_name_candidate("a" * 130)

    def test_contains_non_name_keyword(self):
        assert not _is_valid_name_candidate("统一社会信用代码是")

    def test_keyword_prefix_match(self):
        # "地址" is a prefix of "注册地址"
        assert not _is_valid_name_candidate("地址")

    def test_role_prefix_match(self):
        assert not _is_valid_name_candidate("原告")

    def test_pure_digits(self):
        assert not _is_valid_name_candidate("12345")

    def test_valid_chinese_name(self):
        assert _is_valid_name_candidate("张三")

    def test_valid_company_name(self):
        assert _is_valid_name_candidate("北京测试科技有限公司")

    def test_id_number_format_rejected(self):
        assert not _is_valid_name_candidate("11010119900101123")

    def test_credit_code_with_alpha_rejected(self):
        assert not _is_valid_name_candidate("91110000MA01ABCD12")

    def test_whitespace_only_compact_empty(self):
        assert not _is_valid_name_candidate("   ")


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_id_number
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractIdNumber:
    def test_with_label_colon(self):
        assert _extract_id_number("身份证号码：110101199001011234") == "110101199001011234"

    def test_with_label_keyword(self):
        result = _extract_id_number("身份证号码 110101199001011234")
        assert result == "110101199001011234"

    def test_fallback_15_digit(self):
        result = _extract_id_number("110101900101123")
        assert result == "110101900101123"

    def test_fallback_18_digit_with_x(self):
        result = _extract_id_number("11010119900101123X")
        assert result is not None
        assert result.endswith("X")

    def test_none_when_absent(self):
        assert _extract_id_number("random text") is None

    def test_uppercase_x(self):
        result = _extract_id_number("身份证号：11010119900101123x")
        assert result is not None
        assert result.endswith("X")


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_credit_code
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractCreditCode:
    def test_with_label_colon(self):
        result = _extract_credit_code("统一社会信用代码：91110000MA01ABCD12")
        assert result == "91110000MA01ABCD12"

    def test_with_label_wei(self):
        result = _extract_credit_code("统一社会信用代码为91110000MA01ABCD12")
        assert result == "91110000MA01ABCD12"

    def test_with_label_shi(self):
        result = _extract_credit_code("统一社会信用代码是91110000MA01ABCD12")
        assert result == "91110000MA01ABCD12"

    def test_fallback_with_letters(self):
        result = _extract_credit_code("代码 91110000MA01ABCD12 更多文字")
        assert result == "91110000MA01ABCD12"

    def test_fallback_pure_digits_skipped(self):
        # Pure digit 18-char should not be treated as credit code
        result = _extract_credit_code("身份证号码 110101199001011234")
        # Should either be None or something with alpha
        if result is not None:
            assert any(ch.isalpha() for ch in result)

    def test_fallback_skips_near_id_keyword(self):
        result = _extract_credit_code("身份证91110000MA01ABCD12")
        assert result is None

    def test_none_when_absent(self):
        assert _extract_credit_code("随机文字") is None


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_phone
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractPhone:
    def test_with_label(self):
        assert _extract_phone("联系电话：010-12345678") == "010-12345678"

    def test_with_keyword_shouji(self):
        result = _extract_phone("手机：13900139000")
        assert result == "13900139000"

    def test_with_keyword_lianxifangshi(self):
        result = _extract_phone("联系方式：13900139000")
        assert result == "13900139000"

    def test_fallback_mobile_number(self):
        result = _extract_phone("张某 13900139000 在此")
        assert result == "13900139000"

    def test_fallback_landline_number(self):
        result = _extract_phone("电话 01012345678 详询")
        assert result is not None

    def test_none_when_absent(self):
        assert _extract_phone("张三") is None

    def test_whitespace_removed(self):
        result = _extract_phone("联系电话：010 - 1234 5678")
        assert " " not in result


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_address
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractAddress:
    def test_with_label(self):
        result = _extract_address("地址：北京市朝阳区建国路1号\n联系电话：010-12345678")
        assert result is not None
        assert "北京市朝阳区" in result

    def test_with_keyword_zhusuo(self):
        result = _extract_address("住所地：北京市朝阳区\n电话：010-12345678")
        assert result is not None
        assert "北京市朝阳区" in result

    def test_stops_at_phone_keyword(self):
        result = _extract_address("地址：北京市朝阳区建国路1号\n联系电话：010-12345678")
        assert "010" not in result

    def test_fallback_province_line(self):
        result = _extract_address("北京市朝阳区建国路1号院2号楼301室")
        assert result is not None

    def test_fallback_tianjin(self):
        result = _extract_address("天津市河西区某某路123号")
        assert result is not None

    def test_fallback_shanghai(self):
        result = _extract_address("上海市浦东新区某某路456号")
        assert result is not None

    def test_none_when_no_match(self):
        assert _extract_address("张三，男") is None


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_name (role-based)
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractNameRoleBased:
    def test_plaintiff_label(self):
        result = _extract_name("原告：张三\n地址：北京市")
        assert result == "张三"

    def test_defendant_label(self):
        result = _extract_name("被告：李四\n地址：上海市")
        assert result == "李四"

    def test_applicant_label(self):
        result = _extract_name("申请人：王五\n地址：广州市")
        assert result == "王五"

    def test_party_a_label(self):
        result = _extract_name("甲方：某公司\n地址：深圳市")
        assert result is not None

    def test_role_with_number(self):
        result = _extract_name("被告一：张三\n地址：北京市")
        assert result == "张三"

    def test_role_with_parenthetical(self):
        result = _extract_name("原告（反诉被告）：张三\n地址：北京市")
        assert result == "张三"

    def test_no_role_returns_none(self):
        assert _extract_name("地址：北京市朝阳区") is None


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_name_smart comprehensive
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractNameSmartComprehensive:
    def test_name_field_pattern(self):
        result = _extract_name_smart("名称：北京测试科技有限公司\n地址：北京市")
        assert result is not None
        assert "有限公司" in result

    def test_xingming_field_pattern(self):
        result = _extract_name_smart("姓名：张三\n地址：北京市")
        assert result == "张三"

    def test_smart_pattern_jiafang(self):
        result = _extract_name_smart("甲方：某某律师事务所\n地址：北京市")
        assert result is not None
        assert "律师事务所" in result

    def test_leading_name_before_credit_code(self):
        result = _extract_name_smart("北京测试科技有限公司统一社会信用代码：91110000MA01ABCD12")
        assert result is not None

    def test_role_fallback_no_colon(self):
        result = _extract_name_smart("\n被告 张三\n地址：北京市")
        assert result == "张三"

    def test_leading_person_before_gender(self):
        result = _extract_name_smart("王小明，男，身份证号码：110101199001011234")
        assert result == "王小明"

    def test_legal_entity_pattern_only(self):
        result = _extract_name_smart("深圳某某科技股份有限公司")
        assert result is not None
        assert "有限公司" in result

    def test_natural_person_pattern(self):
        result = _extract_name_smart("赵小明，男")
        assert result == "赵小明"

    def test_first_meaningful_line_fallback(self):
        result = _extract_name_smart("某某律师事务所\n联系电话：010-12345678")
        assert result is not None
        assert "律师事务所" in result


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_single_party
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseSingleParty:
    def test_natural_person_full(self):
        text = "原告：张三\n身份证号码：110101199001011234\n地址：北京市朝阳区\n联系电话：010-12345678"
        result = _parse_single_party(text, use_smart_name=True)
        assert result["name"] == "张三"
        assert result["id_number"] == "110101199001011234"
        assert "北京市" in result["address"]
        assert result["phone"] == "010-12345678"
        assert result["client_type"] == "natural"

    def test_legal_entity_full(self):
        text = "名称：北京测试科技有限公司\n统一社会信用代码：91110000MA01ABCD12\n法定代表人：王五\n地址：北京市海淀区"
        result = _parse_single_party(text, use_smart_name=True)
        assert "有限公司" in result["name"]
        assert result["id_number"] == "91110000MA01ABCD12"
        assert result["legal_representative"] == "王五"
        assert result["client_type"] == "legal"

    def test_credit_code_sets_legal_type(self):
        text = "名称：某公司\n统一社会信用代码：91110000MA01ABCD12"
        result = _parse_single_party(text, use_smart_name=True)
        assert result["client_type"] == "legal"

    def test_id_number_sets_natural_type(self):
        text = "原告：张三\n身份证号码：110101199001011234"
        result = _parse_single_party(text, use_smart_name=True)
        assert result["client_type"] == "natural"

    def test_legal_rep_upgrades_natural_to_legal(self):
        text = "原告：张三\n身份证号码：110101199001011234\n法定代表人：王五"
        result = _parse_single_party(text, use_smart_name=True)
        assert result["client_type"] == "legal"

    def test_no_smart_name(self):
        text = "原告：张三\n身份证号码：110101199001011234"
        result = _parse_single_party(text, use_smart_name=False)
        assert result["name"] == "张三"


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_parties
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractParties:
    def test_two_parties(self):
        text = "原告：张三\n身份证号码：110101199001011234\n被告：李四\n身份证号码：110101199001011235"
        parties = _extract_parties(text)
        names = [p["name"] for p in parties]
        assert "张三" in names
        assert "李四" in names

    def test_three_parties(self):
        text = "原告：张三\n被告：李四\n第三人：王五"
        parties = _extract_parties(text)
        names = [p["name"] for p in parties]
        assert "张三" in names
        assert "李四" in names
        assert "王五" in names

    def test_no_name_excluded(self):
        text = "原告：\n被告：李四"
        parties = _extract_parties(text)
        # Empty name should be excluded
        assert all(p["name"] for p in parties)

    def test_no_role_label_fallback(self):
        text = "张三\n身份证号码：110101199001011234"
        parties = _extract_parties(text)
        assert isinstance(parties, list)

    def test_empty_text(self):
        assert _extract_parties("") == []

    def test_deduplication_same_position(self):
        # Multiple patterns matching at the same start position
        text = "原告：张三\n被告：李四"
        parties = _extract_parties(text)
        # Should not have duplicates
        names = [p["name"] for p in parties]
        assert len(names) == len(set(names))


# ═══════════════════════════════════════════════════════════════════════════════
# _determine_client_type
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetermineClientType:
    def test_credit_code_makes_legal(self):
        assert _determine_client_type("某公司", "统一社会信用代码：91110000MA01ABCD12") == "legal"

    def test_legal_rep_makes_legal(self):
        assert _determine_client_type("某公司", "法定代表人：王五") == "legal"

    def test_company_keyword_makes_legal(self):
        assert _determine_client_type("北京测试有限公司", "") == "legal"

    def test_factory_keyword(self):
        assert _determine_client_type("某某工厂", "") == "legal"

    def test_school_keyword(self):
        assert _determine_client_type("某某学校", "") == "legal"

    def test_hospital_keyword(self):
        assert _determine_client_type("某某医院", "") == "legal"

    def test_bank_keyword(self):
        assert _determine_client_type("某某银行", "") == "legal"

    def test_id_number_makes_natural(self):
        assert _determine_client_type("张三", "身份证号码：110101199001011234") == "natural"

    def test_default_natural(self):
        assert _determine_client_type("张三", "") == "natural"


# ═══════════════════════════════════════════════════════════════════════════════
# parse_client_text and parse_multiple_clients_text
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseClientText:
    def test_none_input(self):
        result = parse_client_text(None)
        assert result["name"] == ""

    def test_with_semicolon_separator(self):
        result = parse_client_text("姓名：张三；地址：北京市")
        assert result["name"] == "张三"

    def test_with_full_stop_separator(self):
        result = parse_client_text("姓名：张三。地址：北京市")
        assert result["name"] == "张三"

    def test_inline_field_break(self):
        # Fields inline without separator should be broken
        result = parse_client_text("原告：张三 身份证号码：110101199001011234")
        assert result["name"] == "张三"

    def test_company_with_address(self):
        result = parse_client_text(
            "名称：北京测试科技有限公司\n"
            "统一社会信用代码：91110000MA01ABCD12\n"
            "地址：北京市海淀区中关村大街1号"
        )
        assert "有限公司" in result["name"]
        assert result["client_type"] == "legal"


class TestParseMultipleClientsText:
    def test_none_input(self):
        assert parse_multiple_clients_text(None) == []

    def test_multiple_plaintiff_defendant(self):
        text = "原告：张三\n被告：北京测试科技有限公司"
        results = parse_multiple_clients_text(text)
        assert len(results) >= 2

    def test_with_role_number(self):
        text = "被告一：张三\n被告二：李四"
        results = parse_multiple_clients_text(text)
        assert len(results) >= 2

    def test_with_parenthetical_role(self):
        text = "原告（反诉被告）：张三\n被告（反诉原告）：李四"
        results = parse_multiple_clients_text(text)
        assert len(results) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# Edge cases: _BIRTH_DATE_PATTERN and _ETHNICITY_PATTERN
# ═══════════════════════════════════════════════════════════════════════════════


class TestPatterns:
    def test_birth_date_pattern_matches(self):
        assert _BIRTH_DATE_PATTERN.search("，1990年1月1日出生") is not None

    def test_birth_date_pattern_no_match(self):
        assert _BIRTH_DATE_PATTERN.search("张三") is None
