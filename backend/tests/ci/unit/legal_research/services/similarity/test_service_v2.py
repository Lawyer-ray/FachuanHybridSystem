"""Tests for apps.legal_research.services.similarity.service.CaseSimilarityService."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tuning(**overrides: Any) -> LegalResearchTuningConfig:
    return LegalResearchTuningConfig(**overrides)


def _make_llm_response(content: str = '{"score":0.85,"decision":"high","reason":"高度相似","facts_match":0.9,"legal_relation_match":0.85,"dispute_match":0.80,"damage_match":0.88,"key_conflicts":[],"evidence_spans":["合同约定","逾期交货"]}', model: str = "qwen-14b") -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.model = model
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCaseSimilarityServiceInit:

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    def test_init_default_tuning(self, mock_locator: MagicMock) -> None:
        mock_locator.get_llm_service.return_value = MagicMock()
        from apps.legal_research.services.similarity.service import CaseSimilarityService
        svc = CaseSimilarityService()
        assert svc._passage_top_k >= 1
        assert svc._passage_max_chars >= 1000

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    def test_init_with_custom_tuning(self, mock_locator: MagicMock) -> None:
        mock_locator.get_llm_service.return_value = MagicMock()
        tuning = _make_tuning(passage_top_k=3, passage_max_chars=5000)
        from apps.legal_research.services.similarity.service import CaseSimilarityService
        svc = CaseSimilarityService(tuning=tuning)
        assert svc._passage_top_k == 3
        assert svc._passage_max_chars == 5000


class TestScoreCase:

    def _make_svc(self, mock_locator: MagicMock) -> Any:
        mock_locator.get_llm_service.return_value = MagicMock()
        from apps.legal_research.services.similarity.service import CaseSimilarityService
        return CaseSimilarityService(tuning=_make_tuning())

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.passage_mod")
    @patch("apps.legal_research.services.similarity.service.scorers")
    @patch("apps.legal_research.services.similarity.service.json_utils")
    @patch("apps.legal_research.services.similarity.service.cache_mod")
    def test_score_case_returns_cached(
        self, mock_cache: MagicMock, mock_json: MagicMock, mock_scorers: MagicMock,
        mock_passage: MagicMock, mock_locator: MagicMock,
    ) -> None:
        svc = self._make_svc(mock_locator)
        from apps.legal_research.services.similarity.service import SimilarityResult
        cached = SimilarityResult(score=0.9, reason="cached", model="cached-model")
        mock_cache.build_similarity_cache_key.return_value = "cache-key-1"
        svc._similarity_cache.load.return_value = (cached, {"source": "local", "probe": "test"})
        result = svc.score_case(
            keyword="买卖合同", case_summary="违约纠纷", title="张三案",
            case_digest="买卖纠纷摘要", content_text="正文内容",
        )
        assert result.score == 0.9
        assert result.model == "cached-model"
        svc._llm.chat.assert_not_called()

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.passage_mod")
    @patch("apps.legal_research.services.similarity.service.scorers")
    @patch("apps.legal_research.services.similarity.service.json_utils")
    @patch("apps.legal_research.services.similarity.service.cache_mod")
    def test_score_case_parses_json_response(
        self, mock_cache: MagicMock, mock_json: MagicMock, mock_scorers: MagicMock,
        mock_passage: MagicMock, mock_locator: MagicMock,
    ) -> None:
        svc = self._make_svc(mock_locator)
        svc._similarity_cache.load.return_value = (None, {})
        mock_cache.build_similarity_cache_key.return_value = "key-2"
        mock_json.extract_transaction_tags.return_value = []
        mock_json.extract_json.return_value = {
            "score": 0.75, "reason": "事实匹配", "key_conflicts": [], "evidence_spans": []
        }
        mock_json.apply_structured_adjustments.return_value = 0.75
        mock_json.extract_structured_metadata.return_value = {"decision": "high"}
        mock_passage.select_relevant_passages.return_value = []
        mock_passage.compose_passage_excerpt.return_value = "摘要内容"
        svc._llm.chat.return_value = _make_llm_response()

        result = svc.score_case(
            keyword="违约", case_summary="买卖纠纷", title="案例标题",
            case_digest="摘要", content_text="正文",
        )
        assert 0.0 <= result.score <= 1.0
        assert result.reason == "事实匹配"

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.passage_mod")
    @patch("apps.legal_research.services.similarity.service.scorers")
    @patch("apps.legal_research.services.similarity.service.json_utils")
    @patch("apps.legal_research.services.similarity.service.cache_mod")
    def test_score_case_fallback_score_from_text(
        self, mock_cache: MagicMock, mock_json: MagicMock, mock_scorers: MagicMock,
        mock_passage: MagicMock, mock_locator: MagicMock,
    ) -> None:
        svc = self._make_svc(mock_locator)
        svc._similarity_cache.load.return_value = (None, {})
        mock_cache.build_similarity_cache_key.return_value = "key-3"
        mock_json.extract_transaction_tags.return_value = []
        mock_json.extract_json.return_value = "not-a-dict"
        mock_scorers.extract_score_from_text.return_value = 0.55
        mock_passage.select_relevant_passages.return_value = []
        mock_passage.compose_passage_excerpt.return_value = ""
        mock_scorers.build_candidate_excerpt.return_value = "fallback excerpt"
        svc._llm.chat.return_value = _make_llm_response(content="score: 0.55")

        result = svc.score_case(
            keyword="借款", case_summary="民间借贷", title="借贷案",
            case_digest="借贷摘要", content_text="正文",
        )
        assert 0.0 <= result.score <= 1.0

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.passage_mod")
    @patch("apps.legal_research.services.similarity.service.scorers")
    @patch("apps.legal_research.services.similarity.service.json_utils")
    @patch("apps.legal_research.services.similarity.service.cache_mod")
    def test_score_case_keyword_overlap_compensation(
        self, mock_cache: MagicMock, mock_json: MagicMock, mock_scorers: MagicMock,
        mock_passage: MagicMock, mock_locator: MagicMock,
    ) -> None:
        svc = self._make_svc(mock_locator)
        svc._similarity_cache.load.return_value = (None, {})
        mock_cache.build_similarity_cache_key.return_value = "key-4"
        mock_json.extract_transaction_tags.return_value = []
        # LLM returns score=0, fallback also 0
        mock_json.extract_json.return_value = {"score": 0, "reason": ""}
        mock_json.apply_structured_adjustments.return_value = 0.0
        mock_json.extract_structured_metadata.return_value = {}
        mock_scorers.keyword_overlap_score.return_value = 0.6
        mock_passage.select_relevant_passages.return_value = []
        mock_passage.compose_passage_excerpt.return_value = "excerpt"
        svc._llm.chat.return_value = _make_llm_response(content="no score here")

        result = svc.score_case(
            keyword="违约 损失", case_summary="合同纠纷", title="违约案",
            case_digest="违约摘要", content_text="正文",
        )
        # With keyword overlap = 0.6, compensation = min(1.0, 0.6 * 0.75) = 0.45
        assert result.score > 0.0


class TestRescoreBorderline:

    def _make_svc(self, mock_locator: MagicMock) -> Any:
        mock_locator.get_llm_service.return_value = MagicMock()
        from apps.legal_research.services.similarity.service import CaseSimilarityService
        return CaseSimilarityService()

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.passage_mod")
    @patch("apps.legal_research.services.similarity.service.scorers")
    @patch("apps.legal_research.services.similarity.service.json_utils")
    @patch("apps.legal_research.services.similarity.service.cache_mod")
    def test_rescore_borderline_cache_hit(
        self, mock_cache: MagicMock, mock_json: MagicMock, mock_scorers: MagicMock,
        mock_passage: MagicMock, mock_locator: MagicMock,
    ) -> None:
        svc = self._make_svc(mock_locator)
        from apps.legal_research.services.similarity.service import SimilarityResult
        cached = SimilarityResult(score=0.70, reason="cached rescore", model="cached")
        svc._similarity_cache.load.return_value = (cached, {"source": "django"})
        mock_cache.build_similarity_cache_key.return_value = "rescore-key"
        result = svc.rescore_borderline_case(
            keyword="违约", case_summary="纠纷", title="案",
            case_digest="摘要", content_text="正文",
            first_score=0.65, first_reason="首轮",
        )
        assert result.score == 0.70

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.passage_mod")
    @patch("apps.legal_research.services.similarity.service.scorers")
    @patch("apps.legal_research.services.similarity.service.json_utils")
    @patch("apps.legal_research.services.similarity.service.cache_mod")
    def test_rescore_borderline_no_cache(
        self, mock_cache: MagicMock, mock_json: MagicMock, mock_scorers: MagicMock,
        mock_passage: MagicMock, mock_locator: MagicMock,
    ) -> None:
        svc = self._make_svc(mock_locator)
        svc._similarity_cache.load.return_value = (None, {})
        mock_cache.build_similarity_cache_key.return_value = "rescore-key-2"
        mock_json.extract_transaction_tags.return_value = []
        mock_json.extract_json.return_value = {"score": 0.72, "reason": "复判结果"}
        mock_json.apply_structured_adjustments.return_value = 0.72
        mock_json.extract_structured_metadata.return_value = {}
        mock_passage.select_relevant_passages.return_value = []
        mock_passage.compose_passage_excerpt.return_value = "excerpt"
        svc._llm.chat.return_value = _make_llm_response(content='{"score":0.72}')

        result = svc.rescore_borderline_case(
            keyword="违约", case_summary="纠纷", title="案",
            case_digest="摘要", content_text="正文",
            first_score=0.65, first_reason="首轮理由",
        )
        assert 0.0 <= result.score <= 1.0

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.passage_mod")
    @patch("apps.legal_research.services.similarity.service.scorers")
    @patch("apps.legal_research.services.similarity.service.json_utils")
    @patch("apps.legal_research.services.similarity.service.cache_mod")
    def test_rescore_borderline_fallback_to_first_score(
        self, mock_cache: MagicMock, mock_json: MagicMock, mock_scorers: MagicMock,
        mock_passage: MagicMock, mock_locator: MagicMock,
    ) -> None:
        svc = self._make_svc(mock_locator)
        svc._similarity_cache.load.return_value = (None, {})
        mock_cache.build_similarity_cache_key.return_value = "rescore-key-3"
        mock_json.extract_transaction_tags.return_value = []
        # LLM returns unparseable content
        mock_json.extract_json.return_value = "unparseable"
        mock_scorers.extract_score_from_text.return_value = 0.0
        mock_passage.select_relevant_passages.return_value = []
        mock_passage.compose_passage_excerpt.return_value = ""
        mock_scorers.build_candidate_excerpt.return_value = ""
        svc._llm.chat.return_value = _make_llm_response(content="garbage")

        result = svc.rescore_borderline_case(
            keyword="违约", case_summary="纠纷", title="案",
            case_digest="摘要", content_text="正文",
            first_score=0.68, first_reason="首轮理由",
        )
        # When LLM content is non-empty but unparseable, reason comes from content[:100]
        assert result.reason == "garbage"
        # Score falls back to first_score
        assert result.score == 0.68


class TestCoarseRecall:

    def _make_svc(self, mock_locator: MagicMock) -> Any:
        mock_locator.get_llm_service.return_value = MagicMock()
        from apps.legal_research.services.similarity.service import CaseSimilarityService
        return CaseSimilarityService()

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.passage_mod")
    @patch("apps.legal_research.services.similarity.service.scorers")
    def test_coarse_recall_all_zero(self, mock_scorers: MagicMock, mock_passage: MagicMock, mock_locator: MagicMock) -> None:
        svc = self._make_svc(mock_locator)
        mock_scorers.keyword_overlap_score.return_value = 0.0
        mock_scorers.summary_overlap_score.return_value = 0.0
        mock_scorers.bm25_proxy_score.return_value = 0.0
        mock_scorers.lexical_vector_similarity_score.return_value = 0.0
        mock_scorers.metadata_hint_score.return_value = 0.0
        mock_passage.passage_alignment_score.return_value = 0.0
        mock_scorers.tokenize.return_value = ["违约"]
        mock_scorers.dedupe_tokens.return_value = ["违约"]
        svc._semantic_vector_enabled = False

        result = svc.coarse_recall_score(
            keyword="违约", case_summary="纠纷", title="案",
            case_digest="摘要", content_text="正文",
        )
        assert result.score == 0.0
        assert "宽召回混合" in result.reason

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.passage_mod")
    @patch("apps.legal_research.services.similarity.service.scorers")
    def test_coarse_recall_high_keyword(self, mock_scorers: MagicMock, mock_passage: MagicMock, mock_locator: MagicMock) -> None:
        svc = self._make_svc(mock_locator)
        mock_scorers.keyword_overlap_score.return_value = 0.9
        mock_scorers.summary_overlap_score.return_value = 0.1
        mock_scorers.bm25_proxy_score.return_value = 0.1
        mock_scorers.lexical_vector_similarity_score.return_value = 0.1
        mock_scorers.metadata_hint_score.return_value = 0.1
        mock_passage.passage_alignment_score.return_value = 0.1
        svc._semantic_vector_enabled = False

        result = svc.coarse_recall_score(
            keyword="违约 合同", case_summary="纠纷", title="违约合同案",
            case_digest="摘要", content_text="正文",
        )
        assert result.score >= 0.5


class TestSemanticVectorRecheck:

    def _make_svc(self, mock_locator: MagicMock, **tuning_overrides: Any) -> Any:
        mock_locator.get_llm_service.return_value = MagicMock()
        from apps.legal_research.services.similarity.service import CaseSimilarityService
        return CaseSimilarityService(tuning=_make_tuning(**tuning_overrides))

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    def test_disabled_semantic(self, mock_locator: MagicMock) -> None:
        svc = self._make_svc(mock_locator, semantic_vector_enabled=False, semantic_vector_model="")
        result = svc._should_enable_semantic_vector_recheck(
            query_text="test", keyword_overlap=0.3, summary_overlap=0.3,
            bm25_score=0.3, lexical_vector_score=0.3, passage_score=0.3, metadata_score=0.3,
        )
        assert result is False

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    def test_high_strongest_disables(self, mock_locator: MagicMock) -> None:
        svc = self._make_svc(mock_locator, semantic_vector_model="test-model")
        result = svc._should_enable_semantic_vector_recheck(
            query_text="test long query text for tokens", keyword_overlap=0.8,
            summary_overlap=0.3, bm25_score=0.3, lexical_vector_score=0.3,
            passage_score=0.3, metadata_score=0.3,
        )
        assert result is False

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    def test_weak_signals_enable(self, mock_locator: MagicMock) -> None:
        svc = self._make_svc(mock_locator, semantic_vector_model="test-model")
        # All signals below weak threshold (0.45)
        result = svc._should_enable_semantic_vector_recheck(
            query_text="test", keyword_overlap=0.1, summary_overlap=0.1,
            bm25_score=0.1, lexical_vector_score=0.1, passage_score=0.1, metadata_score=0.1,
        )
        assert result is True


class TestLogSimilarityMetrics:

    def test_log_basic(self) -> None:
        from apps.legal_research.services.similarity.service import CaseSimilarityService
        CaseSimilarityService._log_similarity_metrics(
            mode="score", elapsed_ms=120, cache_hit=False,
            model="qwen", score=0.85,
        )

    def test_log_with_metadata(self) -> None:
        from apps.legal_research.services.similarity.service import CaseSimilarityService
        CaseSimilarityService._log_similarity_metrics(
            mode="rescore", elapsed_ms=50, cache_hit=True,
            cache_source="local", cache_probe="test",
            model="qwen", score=0.72,
            metadata={"decision": "high", "key_conflicts": ["主体不一致"]},
        )


class TestRepairJsonPayload:

    def _make_svc(self, mock_locator: MagicMock) -> Any:
        mock_locator.get_llm_service.return_value = MagicMock()
        from apps.legal_research.services.similarity.service import CaseSimilarityService
        return CaseSimilarityService()

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.json_utils")
    def test_repair_empty_text(self, mock_json: MagicMock, mock_locator: MagicMock) -> None:
        svc = self._make_svc(mock_locator)
        result = svc._repair_json_payload(raw_text="", model=None)
        assert result is None

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.json_utils")
    def test_repair_success(self, mock_json: MagicMock, mock_locator: MagicMock) -> None:
        svc = self._make_svc(mock_locator)
        mock_json.extract_json.return_value = {"score": 0.5, "reason": "repaired"}
        svc._llm.chat.return_value = _make_llm_response(content='{"score":0.5}')
        result = svc._repair_json_payload(raw_text="bad json text", model="qwen")
        assert isinstance(result, dict)
        assert result["score"] == 0.5

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.json_utils")
    def test_repair_llm_failure(self, mock_json: MagicMock, mock_locator: MagicMock) -> None:
        svc = self._make_svc(mock_locator)
        svc._llm.chat.side_effect = RuntimeError("LLM down")
        result = svc._repair_json_payload(raw_text="bad json", model="qwen")
        assert result is None

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    @patch("apps.legal_research.services.similarity.service.json_utils")
    def test_repair_non_dict_response(self, mock_json: MagicMock, mock_locator: MagicMock) -> None:
        svc = self._make_svc(mock_locator)
        mock_json.extract_json.return_value = "still not a dict"
        svc._llm.chat.return_value = _make_llm_response(content="not json")
        result = svc._repair_json_payload(raw_text="bad json", model=None)
        assert result is None


class TestVectorSimilarityScore:

    def _make_svc(self, mock_locator: MagicMock) -> Any:
        mock_locator.get_llm_service.return_value = MagicMock()
        from apps.legal_research.services.similarity.service import CaseSimilarityService
        return CaseSimilarityService(tuning=_make_tuning(semantic_vector_enabled=False))

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    def test_lexical_only_when_semantic_disabled(self, mock_locator: MagicMock) -> None:
        svc = self._make_svc(mock_locator)
        svc._semantic_vector_enabled = False
        from apps.legal_research.services.similarity.service import scorers
        with patch.object(scorers, "lexical_vector_similarity_score", return_value=0.7):
            result = svc._vector_similarity_score("hello", "hello")
        assert result == 0.7

    @patch("apps.legal_research.services.similarity.service.ServiceLocator")
    def test_semantic_blended_score(self, mock_locator: MagicMock) -> None:
        mock_locator.get_llm_service.return_value = MagicMock()
        from apps.legal_research.services.similarity.service import CaseSimilarityService
        svc = CaseSimilarityService(tuning=_make_tuning(
            semantic_vector_enabled=True, semantic_vector_model="test-model",
        ))
        with (
            patch.object(svc, "_semantic_vector_similarity_score", return_value=0.9),
            patch("apps.legal_research.services.similarity.service.scorers") as mock_scorers,
        ):
            mock_scorers.lexical_vector_similarity_score.return_value = 0.5
            result = svc._vector_similarity_score("text a", "text b", allow_semantic=True)
        # blended = 0.9 * 0.6 + 0.5 * 0.4 = 0.54 + 0.20 = 0.74
        assert abs(result - 0.74) < 0.01


class TestSimilarityResultDataclass:

    def test_fields(self) -> None:
        from apps.legal_research.services.similarity.service import SimilarityResult
        r = SimilarityResult(score=0.8, reason="test", model="m", metadata={"k": "v"})
        assert r.score == 0.8
        assert r.reason == "test"
        assert r.metadata["k"] == "v"

    def test_default_metadata(self) -> None:
        from apps.legal_research.services.similarity.service import SimilarityResult
        r = SimilarityResult(score=0.5, reason="", model="")
        assert r.metadata == {}


class TestLLMEmbeddingClientAdapter:

    def test_create_with_list_input(self) -> None:
        from apps.legal_research.services.similarity.service import _LLMEmbeddingClientAdapter
        mock_llm = MagicMock()
        mock_llm.embed_texts.return_value = [[0.1, 0.2], [0.3, 0.4]]
        adapter = _LLMEmbeddingClientAdapter(mock_llm)
        result = adapter.embeddings.create(input=["hello", "world"], model="test")
        assert len(result.data) == 2
        assert result.data[0].embedding == [0.1, 0.2]
        mock_llm.embed_texts.assert_called_once_with(
            texts=["hello", "world"], backend="openai_compatible", model="test", fallback=False,
        )

    def test_create_with_string_input(self) -> None:
        from apps.legal_research.services.similarity.service import _LLMEmbeddingClientAdapter
        mock_llm = MagicMock()
        mock_llm.embed_texts.return_value = [[0.5, 0.6]]
        adapter = _LLMEmbeddingClientAdapter(mock_llm)
        result = adapter.embeddings.create(input="hello world", model="test")
        assert len(result.data) == 1
        mock_llm.embed_texts.assert_called_once_with(
            texts=["hello world"], backend="openai_compatible", model="test", fallback=False,
        )
