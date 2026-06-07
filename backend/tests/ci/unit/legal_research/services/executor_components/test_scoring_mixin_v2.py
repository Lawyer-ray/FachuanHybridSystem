"""Tests for apps.legal_research.services.executor_components.scoring_mixin.ExecutorScoringMixin."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


from apps.legal_research.services.executor_components.scoring_mixin import ExecutorScoringMixin
from apps.legal_research.services.executor_components.policy_mixin import DualReviewPolicy
from apps.legal_research.services.executor_components.query_mixin import ExecutorQueryMixin
from apps.legal_research.services.executor_components.source_gateway import ExecutorSourceGatewayMixin
from apps.legal_research.services.similarity.service import SimilarityResult


# Combined class with all mixin MRO so cls._build_scoring_keyword resolves correctly
class _TestExecutor(ExecutorScoringMixin, ExecutorQueryMixin, ExecutorSourceGatewayMixin):
    """Minimal combined class for testing classmethods that rely on MRO."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(**overrides: Any) -> MagicMock:
    task = MagicMock()
    task.id = overrides.get("id", "task-001")
    task.keyword = overrides.get("keyword", "买卖合同 违约 价差")
    task.case_summary = overrides.get("case_summary", "原告与被告签订买卖合同，被告逾期交货导致价差损失")
    task.target_count = overrides.get("target_count", 3)
    task.llm_model = overrides.get("llm_model", "")
    return task


def _make_detail(**overrides: Any) -> MagicMock:
    detail = MagicMock()
    detail.doc_id_raw = overrides.get("doc_id_raw", "doc-001")
    detail.doc_id_unquoted = overrides.get("doc_id_unquoted", "doc-001")
    detail.title = overrides.get("title", "张三与李四买卖合同纠纷案")
    detail.case_digest = overrides.get("case_digest", "买卖合同纠纷摘要")
    detail.content_text = overrides.get("content_text", "经审理查明...")
    return detail


def _make_dual_review_policy(**overrides: Any) -> DualReviewPolicy:
    defaults = dict(
        enabled=True,
        review_model="Qwen/Qwen2.5-14B-Instruct",
        primary_weight=0.62,
        secondary_weight=0.38,
        trigger_floor=0.60,
        gap_tolerance=0.18,
        required_min=0.55,
    )
    defaults.update(overrides)
    return DualReviewPolicy(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCoarseRecall:

    def test_with_callable_scorer(self) -> None:
        similarity = MagicMock()
        similarity.coarse_recall_score.return_value = SimilarityResult(
            score=0.72, reason="宽召回", model="coarse"
        )
        detail = _make_detail()
        score, reason = ExecutorScoringMixin._coarse_recall(
            similarity=similarity, keyword="违约", case_summary="纠纷", detail=detail,
        )
        assert score == 0.72
        assert "宽召回" in reason

    def test_with_non_callable_scorer_fallback(self) -> None:
        similarity = MagicMock(spec=[])  # no coarse_recall_score
        detail = _make_detail(title="违约合同纠纷案", case_digest="违约摘要", content_text="违约正文违约内容")
        score, reason = ExecutorScoringMixin._coarse_recall(
            similarity=similarity, keyword="违约", case_summary="纠纷", detail=detail,
        )
        assert score >= 0.0
        assert "fallback" in reason or "关键词重合" in reason

    def test_scorer_raises_fallback(self) -> None:
        similarity = MagicMock()
        similarity.coarse_recall_score.side_effect = RuntimeError("boom")
        detail = _make_detail(title="合同纠纷案", case_digest="合同摘要", content_text="合同正文")
        score, reason = ExecutorScoringMixin._coarse_recall(
            similarity=similarity, keyword="合同", case_summary="纠纷", detail=detail,
        )
        assert score >= 0.0
        assert "fallback" in reason

    def test_zero_score_keyword(self) -> None:
        similarity = MagicMock(spec=[])
        detail = _make_detail(title="无关案", case_digest="无关摘要", content_text="无关正文")
        score, reason = ExecutorScoringMixin._coarse_recall(
            similarity=similarity, keyword="违约", case_summary="纠纷", detail=detail,
        )
        assert score == 0.0


class TestCoarseRerankBudget:

    def test_basic_budget(self) -> None:
        task = _make_task(target_count=5)
        budget = ExecutorScoringMixin._coarse_rerank_budget(task=task, matched=0, batch_size=50)
        assert budget >= ExecutorScoringMixin.COARSE_RECALL_KEEP_MIN
        # remaining=5, budget = max(20, 5*6) = max(20,30) = 30
        assert budget == min(50, 30)

    def test_near_target(self) -> None:
        task = _make_task(target_count=5)
        budget = ExecutorScoringMixin._coarse_rerank_budget(task=task, matched=4, batch_size=50)
        # remaining=1, budget = max(20, 1*6) = 20
        assert budget == min(50, 20)

    def test_target_reached(self) -> None:
        task = _make_task(target_count=3)
        budget = ExecutorScoringMixin._coarse_rerank_budget(task=task, matched=3, batch_size=50)
        # remaining=1 (max(1, 0)), budget = max(20, 6) = 20
        assert budget == min(50, 20)

    def test_batch_size_limit(self) -> None:
        task = _make_task(target_count=10)
        budget = ExecutorScoringMixin._coarse_rerank_budget(task=task, matched=0, batch_size=15)
        # remaining=10, budget = max(20, 60) = 60, but capped at batch_size=15
        assert budget == 15


class TestEffectiveFetchLimit:

    def test_basic(self) -> None:
        ExecutorScoringMixin.DETAIL_FAILURE_BACKFILL_MULTIPLIER = 2
        limit = ExecutorScoringMixin._effective_fetch_limit(max_candidates=100, skipped=0)
        assert limit == 100  # min(200, 100+0)

    def test_with_skipped(self) -> None:
        ExecutorScoringMixin.DETAIL_FAILURE_BACKFILL_MULTIPLIER = 2
        limit = ExecutorScoringMixin._effective_fetch_limit(max_candidates=100, skipped=20)
        assert limit == 120  # min(200, 100+20)

    def test_exceeds_hard_cap(self) -> None:
        ExecutorScoringMixin.DETAIL_FAILURE_BACKFILL_MULTIPLIER = 2
        limit = ExecutorScoringMixin._effective_fetch_limit(max_candidates=100, skipped=200)
        assert limit == 200  # min(200, 300) = 200


class TestCoarseThreshold:

    def test_basic(self) -> None:
        threshold = ExecutorScoringMixin._coarse_threshold(0.75)
        # base = max(0.1, 0.75 * 0.6) = max(0.1, 0.45) = 0.45
        # result = min(0.52, 0.45) = 0.45
        assert abs(threshold - 0.45) < 0.01

    def test_very_low_min_similarity(self) -> None:
        threshold = ExecutorScoringMixin._coarse_threshold(0.1)
        # base = max(0.1, 0.1 * 0.6) = 0.1
        # result = min(0.52, 0.1) = 0.1
        assert abs(threshold - 0.1) < 0.01

    def test_ceiling(self) -> None:
        threshold = ExecutorScoringMixin._coarse_threshold(1.0)
        # base = max(0.1, 0.6) = 0.6
        # result = min(0.52, 0.6) = 0.52
        assert abs(threshold - 0.52) < 0.01


class TestShouldRerank:

    def test_below_minimum_always_false(self) -> None:
        assert ExecutorScoringMixin._should_rerank(
            coarse_score=0.15, threshold=0.3, rerank_used=0, rerank_budget=10,
        ) is False

    def test_above_threshold(self) -> None:
        assert ExecutorScoringMixin._should_rerank(
            coarse_score=0.40, threshold=0.3, rerank_used=0, rerank_budget=10,
        ) is True

    def test_below_threshold_but_budget_remaining(self) -> None:
        assert ExecutorScoringMixin._should_rerank(
            coarse_score=0.25, threshold=0.3, rerank_used=5, rerank_budget=10,
        ) is True

    def test_below_threshold_no_budget(self) -> None:
        assert ExecutorScoringMixin._should_rerank(
            coarse_score=0.25, threshold=0.3, rerank_used=10, rerank_budget=10,
        ) is False


class TestDeferredRerankBudget:

    def test_basic(self) -> None:
        task = _make_task(target_count=5)
        budget = ExecutorScoringMixin._deferred_rerank_budget(task=task, matched=0, deferred_count=50)
        # remaining=5, budget = max(15, 30) = 30
        assert budget == min(50, 30)

    def test_deferred_count_limit(self) -> None:
        task = _make_task(target_count=5)
        budget = ExecutorScoringMixin._deferred_rerank_budget(task=task, matched=0, deferred_count=10)
        # budget = max(15, 30) = 30, but capped at 10
        assert budget == 10


class TestNormalizeScore:

    def test_valid_float(self) -> None:
        assert ExecutorScoringMixin._normalize_score(0.75) == 0.75

    def test_above_one(self) -> None:
        assert ExecutorScoringMixin._normalize_score(1.5) == 1.0

    def test_below_zero(self) -> None:
        assert ExecutorScoringMixin._normalize_score(-0.5) == 0.0

    def test_string_number(self) -> None:
        assert ExecutorScoringMixin._normalize_score("0.8") == 0.8

    def test_invalid_string(self) -> None:
        assert ExecutorScoringMixin._normalize_score("abc") == 0.0

    def test_none(self) -> None:
        assert ExecutorScoringMixin._normalize_score(None) == 0.0


class TestKeywordOverlap:

    def test_all_tokens_match(self) -> None:
        detail = _make_detail(
            title="买卖合同纠纷案",
            case_digest="买卖合同违约价差损失",
            content_text="买卖合同签订后违约",
        )
        score = ExecutorScoringMixin._keyword_overlap(keyword="买卖合同 违约 价差", detail=detail)
        assert score == 1.0

    def test_no_tokens_match(self) -> None:
        detail = _make_detail(title="不相关案", case_digest="无关摘要", content_text="无关正文")
        score = ExecutorScoringMixin._keyword_overlap(keyword="买卖合同 违约", detail=detail)
        assert score == 0.0

    def test_partial_tokens_match(self) -> None:
        detail = _make_detail(title="买卖合同纠纷案", case_digest="摘要", content_text="正文")
        score = ExecutorScoringMixin._keyword_overlap(keyword="买卖合同 违约 价差", detail=detail)
        assert 0.0 < score < 1.0

    def test_empty_keyword(self) -> None:
        detail = _make_detail()
        score = ExecutorScoringMixin._keyword_overlap(keyword="", detail=detail)
        assert score == 0.0

    def test_short_tokens_filtered(self) -> None:
        detail = _make_detail(title="买卖合同纠纷", case_digest="违约", content_text="正文")
        # Single-char tokens like "和" are filtered out
        score = ExecutorScoringMixin._keyword_overlap(keyword="买卖合同 和 违约", detail=detail)
        assert score == 1.0  # "和" is filtered, only 2 tokens remain


class TestMergeDualReviewScores:

    def test_equal_weights(self) -> None:
        policy = _make_dual_review_policy(primary_weight=0.5, secondary_weight=0.5, gap_tolerance=0.5)
        primary = SimilarityResult(score=0.8, reason="primary", model="qwen")
        reviewed = SimilarityResult(score=0.6, reason="review", model="gemini")
        score, reason, model, metadata = ExecutorScoringMixin._merge_dual_review_scores(
            primary=primary, reviewed=reviewed, dual_review_policy=policy,
        )
        # blended = 0.5*0.8 + 0.5*0.6 = 0.7
        assert abs(score - 0.7) < 0.01
        assert "primary" in reason
        assert "review" in reason
        assert "dual_review" in metadata

    def test_disagreement_clamps(self) -> None:
        # gap = 0.18, primary=0.90, review=0.60, disagreement=0.30 > 0.18
        policy = _make_dual_review_policy(primary_weight=0.62, secondary_weight=0.38, gap_tolerance=0.18)
        primary = SimilarityResult(score=0.90, reason="p", model="m1")
        reviewed = SimilarityResult(score=0.60, reason="r", model="m2")
        score, reason, model, metadata = ExecutorScoringMixin._merge_dual_review_scores(
            primary=primary, reviewed=reviewed, dual_review_policy=policy,
        )
        # blended initially = 0.62*0.9 + 0.38*0.6 = 0.786 + 0.228 = 0.786
        # disagreement = 0.30 > 0.18, so blended = min(0.786, 0.60 + 0.04) = 0.64
        assert score <= 0.64 + 0.01

    def test_review_below_required_min(self) -> None:
        policy = _make_dual_review_policy(required_min=0.55)
        primary = SimilarityResult(score=0.7, reason="p", model="m1")
        reviewed = SimilarityResult(score=0.45, reason="r", model="m2")
        score, reason, model, metadata = ExecutorScoringMixin._merge_dual_review_scores(
            primary=primary, reviewed=reviewed, dual_review_policy=policy,
        )
        # review_score < required_min, so blended <= review_score
        assert score <= 0.45 + 0.01

    def test_model_string_format(self) -> None:
        policy = _make_dual_review_policy()
        primary = SimilarityResult(score=0.8, reason="p", model="qwen")
        reviewed = SimilarityResult(score=0.7, reason="r", model="gemini")
        _, _, model, _ = ExecutorScoringMixin._merge_dual_review_scores(
            primary=primary, reviewed=reviewed, dual_review_policy=policy,
        )
        assert "qwen" in model
        assert "gemini" in model


class TestScoreCaseWithRetry:

    @patch.object(_TestExecutor, "_build_scoring_keyword", return_value="test keyword")
    @patch.object(_TestExecutor, "_sleep_for_retry")
    def test_success_first_attempt(self, mock_sleep: MagicMock, mock_kw: MagicMock) -> None:
        similarity = MagicMock()
        similarity.score_case.return_value = SimilarityResult(score=0.8, reason="ok", model="m")
        task = _make_task()
        detail = _make_detail()
        result = _TestExecutor._score_case_with_retry(
            similarity=similarity, task=task, detail=detail, task_id="t-1",
        )
        assert result is not None
        assert result.score == 0.8
        mock_sleep.assert_not_called()

    @patch.object(_TestExecutor, "_build_scoring_keyword", return_value="test keyword")
    @patch.object(_TestExecutor, "_sleep_for_retry")
    def test_success_after_retries(self, mock_sleep: MagicMock, mock_kw: MagicMock) -> None:
        similarity = MagicMock()
        similarity.score_case.side_effect = [RuntimeError("fail"), SimilarityResult(score=0.7, reason="ok", model="m")]
        task = _make_task()
        detail = _make_detail()
        result = _TestExecutor._score_case_with_retry(
            similarity=similarity, task=task, detail=detail, task_id="t-1",
        )
        assert result is not None
        assert result.score == 0.7

    @patch.object(_TestExecutor, "_build_scoring_keyword", return_value="test keyword")
    @patch.object(_TestExecutor, "_sleep_for_retry")
    def test_all_retries_fail(self, mock_sleep: MagicMock, mock_kw: MagicMock) -> None:
        similarity = MagicMock()
        similarity.score_case.side_effect = RuntimeError("persistent failure")
        task = _make_task()
        detail = _make_detail()
        result = _TestExecutor._score_case_with_retry(
            similarity=similarity, task=task, detail=detail, task_id="t-1",
        )
        assert result is None
        assert mock_sleep.call_count == ExecutorScoringMixin.SCORE_RETRY_ATTEMPTS - 1


class TestRescoreBorderlineWithRetry:

    @patch.object(_TestExecutor, "_build_scoring_keyword", return_value="kw")
    def test_no_rescore_function(self, mock_kw: MagicMock) -> None:
        similarity = MagicMock(spec=[])  # no rescore_borderline_case
        task = _make_task()
        detail = _make_detail()
        result = _TestExecutor._rescore_borderline_with_retry(
            similarity=similarity, task=task, detail=detail,
            first_score=0.65, first_reason="reason", task_id="t-1",
        )
        assert result is None

    @patch.object(_TestExecutor, "_build_scoring_keyword", return_value="kw")
    @patch.object(_TestExecutor, "_sleep_for_retry")
    def test_success(self, mock_sleep: MagicMock, mock_kw: MagicMock) -> None:
        similarity = MagicMock()
        similarity.rescore_borderline_case.return_value = SimilarityResult(
            score=0.72, reason="rescored", model="m",
        )
        task = _make_task()
        detail = _make_detail()
        result = _TestExecutor._rescore_borderline_with_retry(
            similarity=similarity, task=task, detail=detail,
            first_score=0.65, first_reason="reason", task_id="t-1",
        )
        assert result is not None
        assert result.score == 0.72

    @patch.object(_TestExecutor, "_build_scoring_keyword", return_value="kw")
    @patch.object(_TestExecutor, "_sleep_for_retry")
    def test_all_fail(self, mock_sleep: MagicMock, mock_kw: MagicMock) -> None:
        similarity = MagicMock()
        similarity.rescore_borderline_case.side_effect = RuntimeError("fail")
        task = _make_task()
        detail = _make_detail()
        result = _TestExecutor._rescore_borderline_with_retry(
            similarity=similarity, task=task, detail=detail,
            first_score=0.65, first_reason="reason", task_id="t-1",
        )
        assert result is None


class TestReviewCaseWithRetry:

    @patch.object(_TestExecutor, "_build_scoring_keyword", return_value="kw")
    def test_no_rescore_uses_score_case(self, mock_kw: MagicMock) -> None:
        similarity = MagicMock(spec=["score_case"])  # no rescore_borderline_case
        similarity.score_case.return_value = SimilarityResult(score=0.8, reason="ok", model="review-model")
        task = _make_task()
        detail = _make_detail()
        result = _TestExecutor._review_case_with_retry(
            similarity=similarity, task=task, detail=detail,
            task_id="t-1", review_model="review-model",
            primary_score=0.75, primary_reason="primary",
        )
        assert result is not None
        assert result.score == 0.8

    @patch.object(_TestExecutor, "_build_scoring_keyword", return_value="kw")
    def test_with_rescore(self, mock_kw: MagicMock) -> None:
        similarity = MagicMock()
        similarity.rescore_borderline_case.return_value = SimilarityResult(
            score=0.82, reason="rescored", model="review-model",
        )
        task = _make_task()
        detail = _make_detail()
        result = _TestExecutor._review_case_with_retry(
            similarity=similarity, task=task, detail=detail,
            task_id="t-1", review_model="review-model",
            primary_score=0.75, primary_reason="primary",
        )
        assert result is not None
        similarity.rescore_borderline_case.assert_called()


class TestBatchRerankCandidates:

    def test_empty_candidates(self) -> None:
        executor = MagicMock()
        executor._score_case_with_retry = MagicMock()
        executor._apply_reranker = MagicMock(return_value=[])
        result = ExecutorScoringMixin._batch_rerank_candidates(
            executor, candidates=[], similarity=MagicMock(),
            task=_make_task(), task_id="t-1", concurrency=3,
        )
        assert result == []

    def test_scores_and_sorts(self) -> None:
        detail1 = _make_detail(doc_id_raw="d1", title="案1")
        detail2 = _make_detail(doc_id_raw="d2", title="案2")
        sim1 = SimilarityResult(score=0.6, reason="r1", model="m")
        sim2 = SimilarityResult(score=0.9, reason="r2", model="m")

        executor = MagicMock()
        executor._score_case_with_retry = MagicMock(side_effect=[sim1, sim2])
        executor._apply_reranker = MagicMock(side_effect=lambda results, **kw: results)

        result = ExecutorScoringMixin._batch_rerank_candidates(
            executor,
            candidates=[(detail1, 0.5, "reason1"), (detail2, 0.6, "reason2")],
            similarity=MagicMock(),
            task=_make_task(),
            task_id="t-1",
            concurrency=2,
        )
        assert len(result) == 2
        # Should be sorted by score descending
        scores = [getattr(r[1], "score", 0) for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_score_failure_skips_candidate(self) -> None:
        detail1 = _make_detail(doc_id_raw="d1")
        detail2 = _make_detail(doc_id_raw="d2")
        sim = SimilarityResult(score=0.8, reason="ok", model="m")

        executor = MagicMock()
        executor._score_case_with_retry = MagicMock(side_effect=[None, sim])
        executor._apply_reranker = MagicMock(side_effect=lambda results, **kw: results)

        result = ExecutorScoringMixin._batch_rerank_candidates(
            executor,
            candidates=[(detail1, 0.5, "r1"), (detail2, 0.6, "r2")],
            similarity=MagicMock(),
            task=_make_task(),
            task_id="t-1",
            concurrency=2,
        )
        assert len(result) == 1
