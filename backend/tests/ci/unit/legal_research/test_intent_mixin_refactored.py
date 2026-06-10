"""Tests for intent_mixin module-level pure functions."""

from __future__ import annotations

from apps.legal_research.services.executor_components.intent_mixin import (
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


class TestSplitIntentClauses:
    def test_basic_split(self) -> None:
        result = split_intent_clauses("原告违约，被告损失。")
        assert len(result) == 2

    def test_filters_short(self) -> None:
        result = split_intent_clauses("一，二，原告违约")
        assert all(len(c) >= 2 for c in result)

    def test_empty(self) -> None:
        assert split_intent_clauses("") == []

    def test_none(self) -> None:
        assert split_intent_clauses(None) == []  # type: ignore[arg-type]


class TestCompactClauseByHints:
    def test_with_hint(self) -> None:
        result = compact_clause_by_hints("原告主张被告逾期交货", hints=("逾期",), max_chars=16)
        assert "逾期" in result

    def test_no_hint(self) -> None:
        result = compact_clause_by_hints("被告已按时交货", hints=("逾期",), max_chars=16)
        assert len(result) <= 16

    def test_empty_clause(self) -> None:
        assert compact_clause_by_hints("", hints=("x",), max_chars=10) == ""

    def test_removes_prefix_noise(self) -> None:
        result = compact_clause_by_hints("原告请求赔偿损失", hints=("赔偿",), max_chars=20)
        assert not result.startswith("原告")


class TestNormalizeRelationTerm:
    def test_append_dispute(self) -> None:
        assert normalize_relation_term("买卖合同") == "买卖合同纠纷"

    def test_already_has_dispute(self) -> None:
        assert normalize_relation_term("买卖合同纠纷") == "买卖合同纠纷"

    def test_labor_special_case(self) -> None:
        assert normalize_relation_term("劳动") == "劳动争议"
        assert normalize_relation_term("劳动纠纷") == "劳动争议"

    def test_empty(self) -> None:
        assert normalize_relation_term("") == ""

    def test_strip_punctuation(self) -> None:
        assert normalize_relation_term("，买卖合同，") == "买卖合同纠纷"

    def test_removes_case_suffix(self) -> None:
        result = normalize_relation_term("买卖合同纠纷案")
        assert result == "买卖合同纠纷"


class TestLooksLikeRelationTerm:
    def test_dispute_suffix(self) -> None:
        assert looks_like_relation_term("买卖合同纠纷") is True

    def test_controversy_suffix(self) -> None:
        assert looks_like_relation_term("劳动争议") is True

    def test_contract_in_text(self) -> None:
        assert looks_like_relation_term("买卖合同") is True

    def test_unrelated(self) -> None:
        assert looks_like_relation_term("赔偿") is False

    def test_empty(self) -> None:
        assert looks_like_relation_term("") is False


class TestContainsAnyHint:
    def test_match(self) -> None:
        assert contains_any_hint("被告逾期交货", ("逾期", "违约")) is True

    def test_no_match(self) -> None:
        assert contains_any_hint("按时交货", ("逾期", "违约")) is False

    def test_empty_text(self) -> None:
        assert contains_any_hint("", ("x",)) is False

    def test_empty_hints(self) -> None:
        assert contains_any_hint("text", ()) is False


class TestDedupeTokens:
    def test_basic(self) -> None:
        assert dedupe_tokens(["a", "b", "a"], max_tokens=10) == ["a", "b"]

    def test_max_tokens(self) -> None:
        assert len(dedupe_tokens(["a", "b", "c"], max_tokens=2)) == 2

    def test_case_insensitive(self) -> None:
        assert len(dedupe_tokens(["Hello", "hello"], max_tokens=10)) == 1

    def test_empty(self) -> None:
        assert dedupe_tokens([], max_tokens=10) == []


class TestSplitTokens:
    def test_basic(self) -> None:
        assert split_tokens("买卖合同 违约") == ["买卖合同", "违约"]

    def test_short_filtered(self) -> None:
        result = split_tokens("a b 买卖合同")
        assert "a" not in result
        assert "b" not in result

    def test_comma_separated(self) -> None:
        result = split_tokens("买卖合同，违约")
        assert len(result) == 2


class TestIsLocationOrCourtToken:
    def test_court(self) -> None:
        assert is_location_or_court_token("北京市朝阳区人民法院") is True

    def test_city(self) -> None:
        assert is_location_or_court_token("北京市") is True

    def test_province(self) -> None:
        assert is_location_or_court_token("广东省") is True

    def test_not_location(self) -> None:
        assert is_location_or_court_token("买卖合同") is False

    def test_empty(self) -> None:
        assert is_location_or_court_token("") is False


class TestParseRuleItems:
    def test_comma_separated(self) -> None:
        result = parse_rule_items("a,b,c", max_items=10, max_len=20)
        assert result == ["a", "b", "c"]

    def test_deduplication(self) -> None:
        result = parse_rule_items("a,a,b", max_items=10, max_len=20)
        assert result == ["a", "b"]

    def test_max_items(self) -> None:
        result = parse_rule_items("a,b,c,d", max_items=2, max_len=20)
        assert len(result) == 2

    def test_max_len(self) -> None:
        result = parse_rule_items("abcdefghijklmnop", max_items=10, max_len=5)
        assert result[0] == "abcde"

    def test_empty(self) -> None:
        assert parse_rule_items("", max_items=10, max_len=20) == []


class TestParseIntWithBounds:
    def test_normal(self) -> None:
        assert parse_int_with_bounds("5", default=2, min_value=1, max_value=10) == 5

    def test_below_min(self) -> None:
        assert parse_int_with_bounds("0", default=2, min_value=1, max_value=10) == 1

    def test_above_max(self) -> None:
        assert parse_int_with_bounds("100", default=2, min_value=1, max_value=10) == 10

    def test_invalid(self) -> None:
        assert parse_int_with_bounds("abc", default=2, min_value=1, max_value=10) == 2

    def test_empty(self) -> None:
        assert parse_int_with_bounds("", default=7, min_value=1, max_value=10) == 7


class TestCollectIntentTerms:
    def test_match(self) -> None:
        mapping = ((("买卖",), "买卖合同纠纷"),)
        result = collect_intent_terms("原告与被告签订买卖合同", mapping)
        assert "买卖合同纠纷" in result

    def test_no_match(self) -> None:
        mapping = ((("不存在",), "不匹配"),)
        result = collect_intent_terms("原告违约", mapping)
        assert result == []
