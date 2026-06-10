"""Tests for task/executor module — testing extractable pure logic."""

from __future__ import annotations

from apps.legal_research.services.executor_components.scoring_mixin import (
    coarse_threshold,
    keyword_overlap_score,
    normalize_score,
    should_rerank,
)


class TestExecutorIntegrationPureFunctions:
    """Verify the executor's pure helper functions work independently."""

    def test_normalize_score_boundary(self) -> None:
        assert normalize_score(0.0) == 0.0
        assert normalize_score(1.0) == 1.0

    def test_keyword_overlap_integration(self) -> None:
        score = keyword_overlap_score(
            keyword="买卖合同 违约 价差",
            title="原告与被告买卖合同违约纠纷",
            case_digest="被告未按时交货，造成原告价差损失",
        )
        assert score > 0.5

    def test_should_rerank_boundary(self) -> None:
        # Score >= threshold => True
        assert should_rerank(coarse_score=0.5, threshold=0.5, rerank_used=0, rerank_budget=0) is True
        # Score < 0.20 => always False
        assert should_rerank(coarse_score=0.19, threshold=0.0, rerank_used=0, rerank_budget=0) is False
        # Score < threshold but under budget => True
        assert should_rerank(coarse_score=0.25, threshold=0.5, rerank_used=0, rerank_budget=1) is True
        # Score < threshold, over budget => False
        assert should_rerank(coarse_score=0.25, threshold=0.5, rerank_used=5, rerank_budget=5) is False

    def test_coarse_threshold_integration(self) -> None:
        t = coarse_threshold(0.65)
        assert t > 0.3
        assert t <= 0.52

    def test_keyword_overlap_all_match(self) -> None:
        score = keyword_overlap_score(
            keyword="违约",
            title="违约责任纠纷",
            case_digest="被告违约",
        )
        assert score == 1.0

    def test_normalize_score_string(self) -> None:
        assert normalize_score("0.42") == 0.42

    def test_should_rerank_at_boundary(self) -> None:
        # Score exactly at 0.20 boundary, over budget and under threshold => False
        assert should_rerank(coarse_score=0.20, threshold=1.0, rerank_used=5, rerank_budget=5) is False
        # Score exactly at 0.20 boundary, under budget => True
        assert should_rerank(coarse_score=0.20, threshold=1.0, rerank_used=0, rerank_budget=5) is True
        # Score below 0.20 boundary => always False
        assert should_rerank(coarse_score=0.19, threshold=0.0, rerank_used=0, rerank_budget=100) is False

    def test_keyword_overlap_mixed_case(self) -> None:
        score = keyword_overlap_score(
            keyword="合同 纠纷",
            title="合同纠纷案",
            case_digest="合同纠纷",
        )
        assert score == 1.0
