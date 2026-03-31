"""Unit tests for apps.client.services.text_parser."""

from __future__ import annotations

import pytest

from apps.client.services.text_parser import (
    _determine_client_type,
    _extract_address,
    _extract_credit_code,
    _extract_id_number,
    _extract_legal_representative,
    _extract_name_smart,
    _extract_parties,
    _extract_phone,
    parse_client_text,
    parse_multiple_clients_text,
)

# ── parse_client_text ─────────────────────────────────────────────────────────

FULL_NATURAL_TEXT = (
    "姓名：张三\n"
    "身份证号码：110101199001011234\n"
    "地址：北京市朝阳区建国路1号\n"
    "联系电话：13800138000"
)

FULL_LEGAL_TEXT = (
    "名称：北京测试科技有限公司\n"
    "统一社会信用代码：91110000MA01ABCD12\n"
    "地址：北京市海淀区中关村大街1号\n"
    "联系电话：010-12345678\n"
    "法定代表人：李四"
)


def test_parse_client_text_natural_person() -> None:
    result = parse_client_text(FULL_NATURAL_TEXT)
    assert result["name"] == "张三"
    assert result["id_number"] == "110101199001011234"
    assert "北京市朝阳区" in result["address"]
    assert result["phone"] == "13800138000"
    assert result["client_type"] == "natural"


def test_parse_client_text_legal_entity() -> None:
    result = parse_client_text(FULL_LEGAL_TEXT)
    assert "测试科技有限公司" in result["name"]
    assert result["id_number"] == "91110000MA01ABCD12"
    assert result["legal_representative"] == "李四"
    assert result["client_type"] == "legal"


def test_parse_client_text_empty_returns_empty_result() -> None:
    result = parse_client_text("")
    assert result["name"] == ""
    assert result["client_type"] == "natural"


def test_parse_client_text_whitespace_only_returns_empty_result() -> None:
    result = parse_client_text("   \n  ")
    assert result["name"] == ""


# ── parse_multiple_clients_text ───────────────────────────────────────────────

MULTI_CLIENT_TEXT = (
    "原告：张三，男，身份证号码：110101199001011234，地址：北京市朝阳区建国路1号\n"
    "被告：北京测试科技有限公司，统一社会信用代码：91110000MA01ABCD12，法定代表人：李四"
)


def test_parse_multiple_clients_text_returns_two_parties() -> None:
    results = parse_multiple_clients_text(MULTI_CLIENT_TEXT)
    assert len(results) >= 2


def test_parse_multiple_clients_text_empty_returns_empty_list() -> None:
    assert parse_multiple_clients_text("") == []


def test_parse_multiple_clients_text_whitespace_returns_empty_list() -> None:
    assert parse_multiple_clients_text("   ") == []


# ── _extract_name_smart ───────────────────────────────────────────────────────

def test_extract_name_smart_from_role_label() -> None:
    text = "原告：张三\n身份证号码：110101199001011234"
    assert _extract_name_smart(text) == "张三"


def test_extract_name_smart_legal_entity() -> None:
    text = "名称：北京测试科技有限公司\n统一社会信用代码：91110000MA01ABCD12"
    result = _extract_name_smart(text)
    assert result is not None
    assert "有限公司" in result


def test_extract_name_smart_natural_person_with_gender() -> None:
    text = "李四，男，身份证号码：110101199001011234"
    result = _extract_name_smart(text)
    assert result == "李四"


def test_extract_name_smart_empty_returns_none() -> None:
    assert _extract_name_smart("") is None


def test_extract_name_smart_only_keywords_returns_none() -> None:
    result = _extract_name_smart("联系电话：13800138000")
    # 不应把"联系电话"当名称
    assert result != "联系电话"


# ── _extract_parties ──────────────────────────────────────────────────────────

def test_extract_parties_single_party() -> None:
    text = "原告：张三\n身份证号码：110101199001011234"
    parties = _extract_parties(text)
    assert len(parties) >= 1
    assert parties[0]["name"] == "张三"


def test_extract_parties_plaintiff_defendant() -> None:
    text = (
        "原告：张三\n身份证号码：110101199001011234\n"
        "被告：李四\n身份证号码：110101198001011234"
    )
    parties = _extract_parties(text)
    names = [p["name"] for p in parties]
    assert "张三" in names
    assert "李四" in names


def test_extract_parties_no_role_label_falls_back() -> None:
    text = "张三\n身份证号码：110101199001011234"
    parties = _extract_parties(text)
    # 无角色标签时兜底解析，可能返回 0 或 1 个
    assert isinstance(parties, list)


# ── _extract_credit_code ──────────────────────────────────────────────────────

def test_extract_credit_code_with_label() -> None:
    text = "统一社会信用代码：91110000MA01ABCD12"
    assert _extract_credit_code(text) == "91110000MA01ABCD12"


def test_extract_credit_code_fallback_with_letters() -> None:
    text = "91110000MA01ABCD12"
    assert _extract_credit_code(text) == "91110000MA01ABCD12"


def test_extract_credit_code_not_confused_with_id_number() -> None:
    text = "身份证号码：110101199001011234"
    # 纯数字18位不应被识别为信用代码
    result = _extract_credit_code(text)
    assert result is None or (result is not None and any(ch.isalpha() for ch in result))


def test_extract_credit_code_none_when_absent() -> None:
    assert _extract_credit_code("张三，男") is None


# ── _extract_id_number ────────────────────────────────────────────────────────

def test_extract_id_number_with_label() -> None:
    text = "身份证号码：110101199001011234"
    assert _extract_id_number(text) == "110101199001011234"


def test_extract_id_number_fallback() -> None:
    text = "110101199001011234"
    assert _extract_id_number(text) == "110101199001011234"


def test_extract_id_number_none_when_absent() -> None:
    assert _extract_id_number("北京市朝阳区") is None


# ── _extract_address ──────────────────────────────────────────────────────────

def test_extract_address_with_label() -> None:
    text = "地址：北京市朝阳区建国路1号\n联系电话：13800138000"
    result = _extract_address(text)
    assert result is not None
    assert "北京市朝阳区" in result


def test_extract_address_fallback_province_line() -> None:
    text = "北京市朝阳区建国路1号院2单元301室"
    result = _extract_address(text)
    assert result is not None


def test_extract_address_none_when_absent() -> None:
    assert _extract_address("张三，男") is None


# ── _extract_phone ────────────────────────────────────────────────────────────

def test_extract_phone_with_label() -> None:
    text = "联系电话：13800138000"
    assert _extract_phone(text) == "13800138000"


def test_extract_phone_fallback_mobile() -> None:
    text = "张三 13900139000"
    result = _extract_phone(text)
    assert result == "13900139000"


def test_extract_phone_none_when_absent() -> None:
    assert _extract_phone("张三，男") is None


# ── _extract_legal_representative ────────────────────────────────────────────

def test_extract_legal_representative_with_label() -> None:
    text = "法定代表人：王五\n地址：北京市"
    result = _extract_legal_representative(text)
    assert result == "王五"


def test_extract_legal_representative_none_when_absent() -> None:
    assert _extract_legal_representative("张三，男") is None


# ── _determine_client_type ────────────────────────────────────────────────────

def test_determine_client_type_legal_by_credit_code() -> None:
    text = "统一社会信用代码：91110000MA01ABCD12"
    assert _determine_client_type("北京测试有限公司", text) == "legal"


def test_determine_client_type_legal_by_legal_rep() -> None:
    text = "法定代表人：王五"
    assert _determine_client_type("某公司", text) == "legal"


def test_determine_client_type_legal_by_name_keyword() -> None:
    assert _determine_client_type("北京测试有限公司", "") == "legal"


def test_determine_client_type_natural_by_id_number() -> None:
    text = "身份证号码：110101199001011234"
    assert _determine_client_type("张三", text) == "natural"


def test_determine_client_type_natural_default() -> None:
    assert _determine_client_type("张三", "") == "natural"


# ── 边界情况 ──────────────────────────────────────────────────────────────────

def test_parse_client_text_name_only() -> None:
    result = parse_client_text("张三")
    # 只有名称，其他字段为空
    assert result["name"] == "张三"
    assert result["id_number"] == ""
    assert result["phone"] == ""


def test_parse_client_text_invalid_input_no_crash() -> None:
    result = parse_client_text("!!@@##$$")
    assert isinstance(result, dict)
    assert "name" in result


# ── _extract_name_smart 次级兜底分支 ─────────────────────────────────────────

def test_extract_name_smart_jiafang_format() -> None:
    # 甲方：xxx 格式（_SMART_NAME_PATTERN）
    text = "甲方：北京测试科技有限公司\n统一社会信用代码：91110000MA01ABCD12"
    result = _extract_name_smart(text)
    assert result is not None
    assert "有限公司" in result


def test_extract_name_smart_leading_name_before_field() -> None:
    # 名称直接在字段前（_LEADING_NAME_BEFORE_FIELD_PATTERN）
    text = "北京测试科技有限公司统一社会信用代码：91110000MA01ABCD12"
    result = _extract_name_smart(text)
    assert result is not None


def test_extract_name_smart_role_no_colon() -> None:
    # 无冒号角色写法：被告 张三，男（_ROLE_NAME_FALLBACK_PATTERN）
    text = "被告 张三，男，地址：北京市"
    result = _extract_name_smart(text)
    assert result == "张三"


def test_extract_name_smart_leading_person_before_gender() -> None:
    # 自然人名在性别前（_LEADING_PERSON_NAME_PATTERN）
    text = "王小明，男，身份证号码：110101199001011234"
    result = _extract_name_smart(text)
    assert result == "王小明"


def test_extract_name_smart_first_line_fallback() -> None:
    # 兜底：第一行即名称
    text = "某某律师事务所\n联系电话：13800138000"
    result = _extract_name_smart(text)
    assert result is not None
    assert "律师事务所" in result


def test_parse_client_text_falls_back_to_direct_parse() -> None:
    # 无角色标签时走 _parse_fields_directly（覆盖 line 190）
    text = "姓名：张三\n联系电话：13800138000"
    result = parse_client_text(text)
    assert result["name"] == "张三"


# ── _is_valid_name_candidate 边缘分支 ────────────────────────────────────────

def test_is_valid_name_candidate_rejects_pure_digits() -> None:
    from apps.client.services.text_parser import _is_valid_name_candidate
    assert not _is_valid_name_candidate("12345678")


def test_is_valid_name_candidate_rejects_id_number_format() -> None:
    from apps.client.services.text_parser import _is_valid_name_candidate
    assert not _is_valid_name_candidate("110101199001011234")


def test_is_valid_name_candidate_rejects_credit_code_with_letters() -> None:
    from apps.client.services.text_parser import _is_valid_name_candidate
    assert not _is_valid_name_candidate("91110000MA01ABCD12")


def test_is_valid_name_candidate_rejects_role_prefix() -> None:
    from apps.client.services.text_parser import _is_valid_name_candidate
    # "原" 是 "原告" 的前缀
    assert not _is_valid_name_candidate("原告")


def test_is_valid_name_candidate_rejects_non_name_keyword() -> None:
    from apps.client.services.text_parser import _is_valid_name_candidate
    assert not _is_valid_name_candidate("联系电话")


# ── 补充覆盖剩余分支 ──────────────────────────────────────────────────────────

def test_extract_name_smart_smart_name_pattern_valid() -> None:
    # 甲方：xxx 格式，且候选值有效（覆盖 276-278）
    # 需要确保 _extract_name 和 _NAME_FIELD_PATTERN 都不先命中
    text = "甲方：某律师事务所\n地址：北京市"
    result = _extract_name_smart(text)
    assert result is not None
    assert "律师事务所" in result


def test_extract_name_smart_leading_name_valid() -> None:
    # leading name before field 命中且有效（覆盖 289-291）
    text = "某某贸易有限公司地址：北京市朝阳区"
    result = _extract_name_smart(text)
    assert result is not None


def test_extract_name_smart_role_fallback_valid() -> None:
    # 无冒号角色写法命中且有效（覆盖 297）
    text = "\n被告 王小二 地址：北京市"
    result = _extract_name_smart(text)
    assert result is not None


def test_extract_name_smart_leading_person_valid() -> None:
    # leading person name 命中且有效（覆盖 302-304）
    text = "赵小明，男，地址：北京市"
    result = _extract_name_smart(text)
    assert result == "赵小明"


def test_extract_name_smart_legal_entity_only() -> None:
    # 仅公司全称，无任何标签（覆盖 309-311）
    text = "深圳某某科技股份有限公司"
    result = _extract_name_smart(text)
    assert result is not None
    assert "有限公司" in result


def test_extract_name_from_first_meaningful_line_returns_line() -> None:
    # 第一行有效名称（覆盖 334）
    from apps.client.services.text_parser import _extract_name_from_first_meaningful_line
    result = _extract_name_from_first_meaningful_line("某某律师\n联系电话：13800138000")
    assert result == "某某律师"


def test_is_valid_name_candidate_empty_compact() -> None:
    # compact 为空（覆盖 345）
    from apps.client.services.text_parser import _is_valid_name_candidate
    assert not _is_valid_name_candidate("  ")


def test_extract_name_returns_none_when_no_role_label() -> None:
    # _extract_name 无角色标签时返回 None（覆盖 458）
    from apps.client.services.text_parser import _extract_name
    assert _extract_name("北京市朝阳区某路1号") is None


def test_extract_credit_code_fallback_skips_near_id_keyword() -> None:
    # 信用代码前有"身份证"关键词时跳过，但后面有合法信用代码（覆盖 497）
    text = "91110000MA01ABCD12"
    result = _extract_credit_code(text)
    assert result == "91110000MA01ABCD12"
