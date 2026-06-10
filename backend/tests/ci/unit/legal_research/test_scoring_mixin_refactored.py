"""Tests for scoring_mixin module-level pure functions."""

from __future__ import annotations

from types import SimpleNamespace

from apps.legal_research.services.executor_components.scoring_mixin import (
    coarse_threshold,
    keyword_overlap_score,
    merge_dual_review_scores,
    normalize_score,
    should_rerank,
)


class TestNormalizeScore:
    def test_normal_value(self) -> None:
        assert normalize_score(0.75) == 0.75

    def test_clamps_high(self) -> None:
        assert normalize_score(1.5) == 1.0

    def test_clamps_low(self) -> None:
        assert normalize_score(-0.5) == 0.0

    def test_string_number(self) -> None:
        assert normalize_score("0.6") == 0.6

    def test_invalid_returns_zero(self) -> None:
        assert normalize_score(None) == 0.0
        assert normalize_score("abc") == 0.0

    def test_zero(self) -> None:
        assert normalize_score(0) == 0.0

    def test_one(self) -> None:
        assert normalize_score(1) == 1.0


class TestKeywordOverlapScore:
    def test_basic_match(self) -> None:
        score = keyword_overlap_score(
            keyword="买卖合同 违约",
            title="买卖合同违约纠纷",
            case_digest="",
        )
        assert score > 0

    def test_no_match(self) -> None:
        score = keyword_overlap_score(
            keyword="劳动争议",
            title="买卖合同纠纷",
            case_digest="",
        )
        assert score == 0.0

    def test_empty_keyword(self) -> None:
        score = keyword_overlap_score(keyword="", title="任何标题", case_digest="")
        assert score == 0.0

    def test_partial_match(self) -> None:
        score = keyword_overlap_score(
            keyword="买卖合同 违约 赔偿",
            title="买卖合同违约纠纷",
            case_digest="",
        )
        assert 0 < score < 1.0

    def test_content_text_included(self) -> None:
        score = keyword_overlap_score(
            keyword="特定术语",
            title="无关标题",
            case_digest="无关摘要",
            content_text="这里包含特定术语",
        )
        assert score > 0

    def test_short_tokens_filtered(self) -> None:
        score = keyword_overlap_score(keyword="a b", title="a b c d e", case_digest="")
        assert score == 0.0


class TestCoarseThreshold:
    def test_default_params(self) -> None:
        result = coarse_threshold(0.8)
        assert result <= 0.52
        assert result > 0

    def test_low_min_similarity(self) -> None:
        result = coarse_threshold(0.1)
        assert result == min(0.52, max(0.1, 0.1 * 0.6))

    def test_custom_ratio(self) -> None:
        result = coarse_threshold(0.8, ratio=0.5, ceil=0.4)
        assert result <= 0.4

    def test_zero_input(self) -> None:
        result = coarse_threshold(0.0)
        assert result >= 0.1 * 0.6


class TestShouldRerank:
    def test_above_threshold(self) -> None:
        assert should_rerank(coarse_score=0.5, threshold=0.3, rerank_used=0, rerank_budget=5) is True

    def test_below_threshold_under_budget(self) -> None:
        assert should_rerank(coarse_score=0.3, threshold=0.5, rerank_used=0, rerank_budget=5) is True

    def test_below_threshold_over_budget(self) -> None:
        assert should_rerank(coarse_score=0.3, threshold=0.5, rerank_used=5, rerank_budget=5) is False

    def test_very_low_score_always_false(self) -> None:
        assert should_rerank(coarse_score=0.19, threshold=0.0, rerank_used=0, rerank_budget=10) is False


class TestMergeDualReviewScores:
    def test_basic_merge(self) -> None:
        score, reason, model, meta = merge_dual_review_scores(
            primary_score=0.8,
            primary_reason="高相似",
            primary_model="qwen",
            review_score=0.7,
            reviewed_reason="中等",
            reviewed_model="gpt4",
            primary_weight=0.7,
            secondary_weight=0.3,
            gap_tolerance=0.15,
            required_min=0.3,
        )
        assert 0 <= score <= 1
        assert "高相似" in reason
        assert "qwen" in model
        assert "dual_review" in meta

    def test_gap_clamp(self) -> None:
        score, _, _, _ = merge_dual_review_scores(
            primary_score=0.9,
            primary_reason="高",
            primary_model="m1",
            review_score=0.4,
            reviewed_reason="低",
            reviewed_model="m2",
            primary_weight=0.7,
            secondary_weight=0.3,
            gap_tolerance=0.1,
            required_min=0.3,
        )
        assert score <= 0.4 + 0.04

    def test_required_min_clamp(self) -> None:
        score, _, _, _ = merge_dual_review_scores(
            primary_score=0.9,
            primary_reason="高",
            primary_model="m1",
            review_score=0.2,
            reviewed_reason="低",
            reviewed_model="m2",
            primary_weight=0.7,
            secondary_weight=0.3,
            gap_tolerance=0.5,
            required_min=0.3,
        )
        assert score <= 0.2

    def test_reason_truncated(self) -> None:
        _, reason, _, _ = merge_dual_review_scores(
            primary_score=0.8,
            primary_reason="x" * 200,
            primary_model="m",
            review_score=0.7,
            reviewed_reason="y" * 200,
            reviewed_model="n",
            primary_weight=0.5,
            secondary_weight=0.5,
            gap_tolerance=0.5,
            required_min=0.0,
        )
        assert len(reason) <= 220

    def test_score_bounded(self) -> None:
        score, _, _, _ = merge_dual_review_scores(
            primary_score=2.0,
            primary_reason="",
            primary_model="m",
            review_score=-1.0,
            reviewed_reason="",
            reviewed_model="n",
            primary_weight=0.5,
            secondary_weight=0.5,
            gap_tolerance=0.5,
            required_min=0.0,
        )
        assert 0 <= score <= 1
