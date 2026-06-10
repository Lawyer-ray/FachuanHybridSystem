"""Tests for similarity/service pure functions."""

from __future__ import annotations

from apps.legal_research.services.similarity.scorers import (
    coerce_score,
    keyword_overlap_score,
    normalize_score,
    token_overlap_score,
    tokenize,
    dedupe_tokens,
)


class TestCoerceScore:
    def test_normal(self) -> None:
        assert coerce_score(0.7) == 0.7

    def test_string_number(self) -> None:
        assert coerce_score("0.5") == 0.5

    def test_percentage_format(self) -> None:
        # coerce_score treats values 1-100 as percentages
        assert coerce_score("75%") == 0.75

    def test_value_above_1_normalized(self) -> None:
        # 2.0 is > 1 and <= 100, so normalized as 2.0/100 = 0.02
        assert coerce_score(2.0) == 0.02

    def test_invalid(self) -> None:
        assert coerce_score(None) == 0.0  # type: ignore[arg-type]
        assert coerce_score("abc") == 0.0


class TestNormalizeScore:
    def test_normal(self) -> None:
        assert normalize_score(0.6) == 0.6

    def test_above_1_treated_as_percentage(self) -> None:
        # normalize_score(1.5) returns 1.5/100 = 0.015 since 1 < 1.5 <= 100
        assert normalize_score(1.5) == 0.015

    def test_negative_returns_zero(self) -> None:
        assert normalize_score(-0.5) == 0.0

    def test_at_100(self) -> None:
        assert normalize_score(100.0) == 1.0


class TestTokenize:
    def test_basic(self) -> None:
        result = tokenize("买卖合同纠纷")
        assert len(result) > 0

    def test_empty(self) -> None:
        assert tokenize("") == []


class TestDedupeTokens:
    def test_dedup(self) -> None:
        result = dedupe_tokens(["a", "b", "a", "c"], max_tokens=10)
        assert result == ["a", "b", "c"]

    def test_max_tokens(self) -> None:
        result = dedupe_tokens(["a", "b", "c"], max_tokens=2)
        assert len(result) == 2


class TestKeywordOverlapScore:
    def test_basic(self) -> None:
        score = keyword_overlap_score(
            keyword="买卖合同 违约",
            title="买卖合同违约纠纷",
            case_digest="",
            content_text="",
        )
        assert score > 0

    def test_no_overlap(self) -> None:
        score = keyword_overlap_score(
            keyword="劳动争议",
            title="买卖合同纠纷",
            case_digest="",
            content_text="",
        )
        assert score == 0.0


class TestTokenOverlapScore:
    def test_basic(self) -> None:
        score = token_overlap_score(
            "买卖合同 违约 赔偿",
            "买卖合同违约纠纷案，被告应赔偿原告损失",
        )
        assert 0 <= score <= 1

    def test_empty(self) -> None:
        score = token_overlap_score("", "text")
        assert score == 0.0

    def test_all_match(self) -> None:
        score = token_overlap_score("违约", "被告违约")
        assert score == 1.0
