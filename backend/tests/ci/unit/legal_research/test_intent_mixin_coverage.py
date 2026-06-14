"""Tests for legal_research/services/executor_components/intent_mixin.py"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from apps.legal_research.services.executor_components.intent_mixin import (
    ExecutorIntentMixin,
    _IntentRuleOverrides,
    _IntentSlots,
    collect_intent_terms,
    compact_clause_by_hints,
    contains_any_hint,
    dedupe_tokens,
    is_location_or_court_token,
    looks_like_relation_term,
    normalize_relation_term,
    parse_int_with_bounds,
    parse_rule_items,
    split_intent_clauses,
    split_tokens,
)


# ── split_intent_clauses ──────────────────────────────────────────────────────

def test_split_intent_clauses_basic():
    result = split_intent_clauses("甲方向乙方借款，约定三个月后还款。")
    assert len(result) >= 1
    assert all(len(c) >= 2 for c in result)


def test_split_intent_clauses_empty():
    assert split_intent_clauses("") == []


def test_split_intent_clauses_none():
    assert split_intent_clauses(None) == []  # type: ignore[arg-type]


def test_split_intent_clauses_whitespace_only():
    # whitespace only -> normalized to empty -> filtered
    assert split_intent_clauses("   ") == []


def test_split_intent_clauses_short_segments():
    # segments shorter than 2 chars are filtered out
    result = split_intent_clauses("A。B。甲乙丙。")
    assert "甲乙丙" in result
    assert "A" not in result


def test_split_intent_clauses_multiple_delimiters():
    result = split_intent_clauses("原告起诉被告；被告未履行合同，造成损失")
    assert len(result) >= 2


# ── compact_clause_by_hints ───────────────────────────────────────────────────

def test_compact_clause_empty():
    assert compact_clause_by_hints("", hints=("违约",), max_chars=16) == ""


def test_compact_clause_no_hint_match():
    result = compact_clause_by_hints("被告未按期付款", hints=("停工",), max_chars=16)
    assert isinstance(result, str)
    assert len(result) <= 16


def test_compact_clause_with_hint():
    result = compact_clause_by_hints("被告违约造成原告损失", hints=("违约",), max_chars=16)
    assert "违约" in result
    assert len(result) <= 16


def test_compact_clause_strips_prefix():
    result = compact_clause_by_hints("原告主张违约责任", hints=("违约",), max_chars=16)
    assert "原告" not in result


def test_compact_clause_strips_suffix():
    result = compact_clause_by_hints("被告违约要求赔偿", hints=("违约",), max_chars=16)
    # "要求" is a suffix that gets stripped, but "赔偿" remains
    assert "违约" in result


def test_compact_clause_multiple_hints_picks_first():
    result = compact_clause_by_hints("被告违约造成停工损失", hints=("停工", "违约"), max_chars=20)
    # "违约" appears earlier, should be chosen
    assert "违约" in result


def test_compact_clause_truncates():
    long_clause = "被告违约未按约定时间交付货物造成原告重大经济损失"
    result = compact_clause_by_hints(long_clause, hints=("违约",), max_chars=6)
    assert len(result) <= 6


# ── normalize_relation_term ───────────────────────────────────────────────────

def test_normalize_relation_term_empty():
    assert normalize_relation_term("") == ""
    assert normalize_relation_term(None) == ""  # type: ignore[arg-type]
    assert normalize_relation_term("   ") == ""


def test_normalize_relation_term_strips_punctuation():
    assert normalize_relation_term("合同纠纷，") == "合同纠纷"


def test_normalize_relation_term_contract_suffix():
    result = normalize_relation_term("买卖合同")
    assert result == "买卖合同纠纷"


def test_normalize_relation_term_contract_dispute():
    result = normalize_relation_term("买卖合同纠纷")
    assert result == "买卖合同纠纷"


def test_normalize_relation_term_dispute_case():
    result = normalize_relation_term("劳动纠纷案")
    assert result == "劳动争议"


def test_normalize_relation_term_labor():
    assert normalize_relation_term("劳动") == "劳动争议"
    assert normalize_relation_term("劳动纠纷") == "劳动争议"


def test_normalize_relation_term_generic():
    result = normalize_relation_term("侵权纠纷")
    assert result == "侵权纠纷"


# ── looks_like_relation_term ──────────────────────────────────────────────────

def test_looks_like_relation_empty():
    assert looks_like_relation_term("") is False
    assert looks_like_relation_term(None) is False  # type: ignore[arg-type]


def test_looks_like_relation_dispute():
    assert looks_like_relation_term("合同纠纷") is True


def test_looks_like_relation_争议():
    assert looks_like_relation_term("劳动争议") is True


def test_looks_like_relation_之诉():
    assert looks_like_relation_term("不当得利之诉") is True


def test_looks_like_relation_contract():
    assert looks_like_relation_term("买卖合同") is True


def test_looks_like_relation_no_match():
    assert looks_like_relation_term("违约金") is False


# ── contains_any_hint ─────────────────────────────────────────────────────────

def test_contains_any_hint_empty():
    assert contains_any_hint("", ("违约",)) is False
    assert contains_any_hint(None, ("违约",)) is False  # type: ignore[arg-type]


def test_contains_any_hint_match():
    assert contains_any_hint("被告违约", ("违约", "逾期")) is True


def test_contains_any_hint_no_match():
    assert contains_any_hint("被告已付款", ("违约", "逾期")) is False


# ── dedupe_tokens ─────────────────────────────────────────────────────────────

def test_dedupe_tokens_empty():
    assert dedupe_tokens([], max_tokens=8) == []


def test_dedupe_tokens_removes_duplicates():
    result = dedupe_tokens(["违约", "违约", "逾期"], max_tokens=8)
    assert result == ["违约", "逾期"]


def test_dedupe_tokens_case_insensitive():
    result = dedupe_tokens(["Hello", "hello", "HELLO"], max_tokens=8)
    assert len(result) == 1


def test_dedupe_tokens_max_tokens():
    result = dedupe_tokens(["a", "b", "c", "d"], max_tokens=2)
    assert len(result) == 2


def test_dedupe_tokens_strips_whitespace():
    result = dedupe_tokens(["  违约  ", "违约"], max_tokens=8)
    assert len(result) == 1


def test_dedupe_tokens_filters_empty():
    result = dedupe_tokens(["", "  ", "违约"], max_tokens=8)
    assert result == ["违约"]


# ── split_tokens ──────────────────────────────────────────────────────────────

def test_split_tokens_basic():
    result = split_tokens("违约 逾期 拖欠")
    assert result == ["违约", "逾期", "拖欠"]


def test_split_tokens_comma_separated():
    result = split_tokens("违约,逾期,拖欠")
    assert result == ["违约", "逾期", "拖欠"]


def test_split_tokens_filters_short():
    result = split_tokens("A 违约 B 逾期")
    assert "A" not in result
    assert "B" not in result
    assert "违约" in result


def test_split_tokens_empty():
    assert split_tokens("") == []
    assert split_tokens(None) == []  # type: ignore[arg-type]


# ── is_location_or_court_token ────────────────────────────────────────────────

def test_is_location_empty():
    assert is_location_or_court_token("") is False
    assert is_location_or_court_token(None) is False  # type: ignore[arg-type]


def test_is_location_court():
    assert is_location_or_court_token("北京市朝阳区人民法院") is True
    assert is_location_or_court_token("法院") is True


def test_is_location_city():
    assert is_location_or_court_token("北京市") is True
    assert is_location_or_court_token("朝阳区") is True
    assert is_location_or_court_token("江苏省") is True


def test_is_location_not_location():
    assert is_location_or_court_token("违约") is False


# ── parse_rule_items ──────────────────────────────────────────────────────────

def test_parse_rule_items_empty():
    assert parse_rule_items("", max_items=10, max_len=20) == []
    assert parse_rule_items(None, max_items=10, max_len=20) == []  # type: ignore[arg-type]


def test_parse_rule_items_basic():
    result = parse_rule_items("违约,逾期,拖欠", max_items=10, max_len=20)
    assert result == ["违约", "逾期", "拖欠"]


def test_parse_rule_items_newline_separated():
    result = parse_rule_items("违约\n逾期\n拖欠", max_items=10, max_len=20)
    assert len(result) == 3


def test_parse_rule_items_deduplicates():
    result = parse_rule_items("违约,违约,逾期", max_items=10, max_len=20)
    assert result == ["违约", "逾期"]


def test_parse_rule_items_max_items():
    result = parse_rule_items("a,b,c,d,e", max_items=2, max_len=20)
    assert len(result) == 2


def test_parse_rule_items_max_len():
    result = parse_rule_items("abcdefghijklmnopqrstuv", max_items=10, max_len=5)
    assert len(result[0]) == 5


def test_parse_rule_items_pipe_separated():
    result = parse_rule_items("违约|逾期|拖欠", max_items=10, max_len=20)
    assert len(result) == 3


# ── parse_int_with_bounds ─────────────────────────────────────────────────────

def test_parse_int_with_bounds_basic():
    assert parse_int_with_bounds("5", default=2, min_value=1, max_value=10) == 5


def test_parse_int_with_bounds_below_min():
    assert parse_int_with_bounds("0", default=2, min_value=1, max_value=10) == 1


def test_parse_int_with_bounds_above_max():
    assert parse_int_with_bounds("100", default=2, min_value=1, max_value=10) == 10


def test_parse_int_with_bounds_invalid():
    assert parse_int_with_bounds("abc", default=2, min_value=1, max_value=10) == 2
    assert parse_int_with_bounds("", default=2, min_value=1, max_value=10) == 2
    assert parse_int_with_bounds(None, default=2, min_value=1, max_value=10) == 2  # type: ignore[arg-type]


def test_parse_int_with_bounds_whitespace():
    assert parse_int_with_bounds("  5  ", default=2, min_value=1, max_value=10) == 5


# ── collect_intent_terms ──────────────────────────────────────────────────────

def test_collect_intent_terms_basic():
    mapping = (
        (("违约",), "违约责任"),
        (("逾期",), "逾期付款"),
    )
    result = collect_intent_terms("被告违约未付款", mapping)
    assert "违约责任" in result


def test_collect_intent_terms_no_match():
    mapping = ((("违约",), "违约责任"),)
    result = collect_intent_terms("被告已付款", mapping)
    assert result == []


def test_collect_intent_terms_multiple_matches():
    mapping = (
        (("违约",), "违约责任"),
        (("逾期",), "逾期付款"),
    )
    result = collect_intent_terms("被告违约逾期未付款", mapping)
    assert "违约责任" in result
    assert "逾期付款" in result


# ── ExecutorIntentMixin._extract_intent_slots ─────────────────────────────────

def _mock_overrides():
    """Return empty overrides to avoid DB access."""
    return {
        "relation_regex_extra": [],
        "relation_term_extra": [],
        "breach_hint_extra": [],
        "damage_hint_extra": [],
        "remedy_hint_extra": [],
        "low_conf_limit": 2,
    }


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_intent_slots_empty():
    relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots("")
    assert relation == []
    assert breach == []
    assert damage == []
    assert remedy == []


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_intent_slots_none():
    relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots(None)  # type: ignore[arg-type]
    assert relation == []
    assert breach == []
    assert damage == []
    assert remedy == []


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_intent_slots_with_relation():
    relation, _, _, _ = ExecutorIntentMixin._extract_intent_slots("买卖合同纠纷")
    assert any("买卖" in r for r in relation)


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_intent_slots_with_breach():
    _, breach, _, _ = ExecutorIntentMixin._extract_intent_slots("被告违约未交货")
    assert len(breach) > 0


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_intent_slots_with_damage():
    _, _, damage, _ = ExecutorIntentMixin._extract_intent_slots("造成原告损失10万元")
    assert len(damage) > 0


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_intent_slots_with_remedy():
    _, _, _, remedy = ExecutorIntentMixin._extract_intent_slots("要求被告赔偿损失")
    assert len(remedy) > 0


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_intent_slots_full_case():
    text = (
        "原告与被告签订买卖合同，被告违约未交货，"
        "造成原告价差损失5万元，请求被告赔偿损失"
    )
    relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots(text)
    assert len(relation) > 0
    assert len(breach) > 0
    assert len(damage) > 0
    assert len(remedy) > 0


# ── ExecutorIntentMixin._extract_intent_slots_with_confidence ─────────────────

@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_intent_slots_with_confidence_empty():
    result = ExecutorIntentMixin._extract_intent_slots_with_confidence("")
    assert result["relation_high"] == []
    assert result["breach_high"] == []
    assert result["low_conf_limit"] == 2


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_intent_slots_with_confidence_contract_dispute():
    result = ExecutorIntentMixin._extract_intent_slots_with_confidence("买卖合同纠纷")
    assert len(result["relation_high"]) > 0


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_intent_slots_with_confidence_multi_hint():
    result = ExecutorIntentMixin._extract_intent_slots_with_confidence("被告违约逾期未付款造成损失")
    # breach should have multiple terms since multiple hints
    assert len(result["breach_high"]) > 0


# ── ExecutorIntentMixin._extract_relation_terms_dynamic ───────────────────────

def test_extract_relation_terms_dynamic_empty():
    assert ExecutorIntentMixin._extract_relation_terms_dynamic("") == []


def test_extract_relation_terms_dynamic_whitespace():
    assert ExecutorIntentMixin._extract_relation_terms_dynamic("   ") == []


def test_extract_relation_terms_dynamic_contract_dispute():
    terms = ExecutorIntentMixin._extract_relation_terms_dynamic("买卖合同纠纷案件")
    assert len(terms) > 0
    assert any("买卖" in t for t in terms)


def test_extract_relation_terms_dynamic_with_extra_regex():
    terms = ExecutorIntentMixin._extract_relation_terms_dynamic(
        "知识产权侵权纠纷",
        extra_regexes=[r"知识产权侵权纠纷"],
    )
    assert any("知识产权" in t for t in terms)


def test_extract_relation_terms_dynamic_invalid_regex():
    # Should not raise on bad regex
    terms = ExecutorIntentMixin._extract_relation_terms_dynamic(
        "买卖合同纠纷",
        extra_regexes=["[invalid"],
    )
    assert len(terms) > 0  # still gets matches from default regexes


def test_extract_relation_terms_dynamic_contract_keyword():
    terms = ExecutorIntentMixin._extract_relation_terms_dynamic("技术服务合同")
    assert any("技术服务合同" in t for t in terms)


# ── ExecutorIntentMixin._extract_slot_terms_by_hints_with_confidence ──────────

def test_extract_slot_terms_empty_hints():
    high, low = ExecutorIntentMixin._extract_slot_terms_by_hints_with_confidence("text", hints=())
    assert high == []
    assert low == []


def test_extract_slot_terms_no_match():
    high, low = ExecutorIntentMixin._extract_slot_terms_by_hints_with_confidence(
        "被告已履行合同", hints=("违约", "逾期")
    )
    assert high == []
    assert low == []


def test_extract_slot_terms_single_hint_short_clause():
    high, low = ExecutorIntentMixin._extract_slot_terms_by_hints_with_confidence(
        "被告违约", hints=("违约", "逾期")
    )
    # Single hint, short clause -> low
    assert len(low) > 0 or len(high) > 0


def test_extract_slot_terms_multi_hint():
    high, low = ExecutorIntentMixin._extract_slot_terms_by_hints_with_confidence(
        "被告违约逾期未付款造成原告重大损失", hints=("违约", "逾期", "损失")
    )
    # Multi-hint clause -> high
    assert len(high) > 0


# ── ExecutorIntentMixin._load_intent_rule_overrides ───────────────────────────

@patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
def test_load_intent_rule_overrides_service_unavailable(mock_locator):
    mock_locator.get_system_config_service.side_effect = Exception("not available")
    result = ExecutorIntentMixin._load_intent_rule_overrides()
    assert result["relation_regex_extra"] == []
    assert result["breach_hint_extra"] == []
    assert result["low_conf_limit"] == 2


@patch("apps.legal_research.services.executor_components.intent_mixin.ServiceLocator")
def test_load_intent_rule_overrides_with_config(mock_locator):
    mock_config = MagicMock()
    mock_config.get_value.side_effect = lambda key, default="": {
        "LEGAL_RESEARCH_INTENT_RELATION_REGEX_EXTRA": "知识产权侵权纠纷",
        "LEGAL_RESEARCH_INTENT_RELATION_TERM_EXTRA": "商标权纠纷",
        "LEGAL_RESEARCH_INTENT_BREACH_HINT_EXTRA": "篡改,伪造",
        "LEGAL_RESEARCH_INTENT_DAMAGE_HINT_EXTRA": "商誉损失",
        "LEGAL_RESEARCH_INTENT_REMEDY_HINT_EXTRA": "停止侵害",
        "LEGAL_RESEARCH_INTENT_LOW_CONF_MAX_TERMS": "4",
    }.get(key, default)
    mock_locator.get_system_config_service.return_value = mock_config
    result = ExecutorIntentMixin._load_intent_rule_overrides()
    assert "知识产权侵权纠纷" in result["relation_regex_extra"]
    assert "商标权纠纷" in result["relation_term_extra"]
    assert "篡改" in result["breach_hint_extra"]
    assert "商誉损失" in result["damage_hint_extra"]
    assert "停止侵害" in result["remedy_hint_extra"]
    assert result["low_conf_limit"] == 4


# ── ExecutorIntentMixin._merge_hint_overrides ─────────────────────────────────

def test_merge_hint_overrides_no_extras():
    defaults = ("违约", "逾期")
    result = ExecutorIntentMixin._merge_hint_overrides(defaults, [])
    assert "违约" in result
    assert "逾期" in result


def test_merge_hint_overrides_with_extras():
    defaults = ("违约", "逾期")
    result = ExecutorIntentMixin._merge_hint_overrides(defaults, ["篡改", "伪造"])
    assert "篡改" in result
    assert "伪造" in result
    assert "违约" in result


def test_merge_hint_overrides_deduplicates():
    defaults = ("违约", "逾期")
    result = ExecutorIntentMixin._merge_hint_overrides(defaults, ["违约"])
    assert result.count("违约") == 1


# ── ExecutorIntentMixin._split_tokens ─────────────────────────────────────────

def test_mixin_split_tokens():
    result = ExecutorIntentMixin._split_tokens("违约 逾期 拖欠")
    assert result == ["违约", "逾期", "拖欠"]


# ── ExecutorIntentMixin._is_location_or_court_token ───────────────────────────

def test_mixin_is_location():
    assert ExecutorIntentMixin._is_location_or_court_token("法院") is True
    assert ExecutorIntentMixin._is_location_or_court_token("违约") is False


# ── ExecutorIntentMixin._extract_summary_terms ────────────────────────────────

def test_extract_summary_terms_empty():
    assert ExecutorIntentMixin._extract_summary_terms("") == []
    assert ExecutorIntentMixin._extract_summary_terms(None) == []  # type: ignore[arg-type]
    assert ExecutorIntentMixin._extract_summary_terms("   ") == []


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_summary_terms_basic():
    terms = ExecutorIntentMixin._extract_summary_terms("买卖合同违约造成损失")
    assert len(terms) > 0


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_summary_terms_filters_stopwords():
    terms = ExecutorIntentMixin._extract_summary_terms("原告要求被告承担违约责任")
    # "原告", "被告", "要求", "承担" are stopwords
    assert "原告" not in terms
    assert "被告" not in terms


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_summary_terms_filters_digit_tokens():
    terms = ExecutorIntentMixin._extract_summary_terms("赔偿12345元")
    assert "12345" not in terms


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_summary_terms_filters_court_tokens():
    terms = ExecutorIntentMixin._extract_summary_terms("朝阳区人民法院判决违约")
    assert "朝阳区人民法院" not in terms


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_extract_summary_terms_includes_phrases():
    terms = ExecutorIntentMixin._extract_summary_terms("被告不当得利应当返还")
    assert "不当得利纠纷" in terms


# ── ExecutorIntentMixin._dedupe_tokens ────────────────────────────────────────

def test_mixin_dedupe_tokens():
    result = ExecutorIntentMixin._dedupe_tokens(["违约", "违约"], max_tokens=8)
    assert result == ["违约"]


# ── Integration: full-text intent extraction ──────────────────────────────────

@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_full_intent_borrowing_dispute():
    text = "原告向被告出借人民币10万元，被告借款后逾期未还款，原告请求被告返还借款并支付利息"
    relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots(text)
    assert any("借款" in r for r in relation)
    assert len(breach) > 0
    assert len(remedy) > 0


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_full_intent_labor_dispute():
    text = "原告在被告公司工作期间受工伤，被告未支付工伤赔偿，要求被告赔偿损失"
    relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots(text)
    assert any("劳动" in r for r in relation)


@patch.object(ExecutorIntentMixin, "_load_intent_rule_overrides", classmethod(lambda cls: _mock_overrides()))
def test_full_intent_construction_dispute():
    text = "建设工程施工合同纠纷，施工方违约未按时完工，导致发包方停工损失"
    relation, breach, damage, remedy = ExecutorIntentMixin._extract_intent_slots(text)
    assert any("建设" in r for r in relation)
