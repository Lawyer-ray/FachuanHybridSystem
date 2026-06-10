"""CaseSimilarityService tests with mocked LLM."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.legal_research.services.similarity.service import CaseSimilarityService, SimilarityResult


class TestSimilarityResult:
    def test_creation(self):
        r = SimilarityResult(score=0.8, reason="test", model="gpt-4")
        assert r.score == 0.8
        assert r.reason == "test"
        assert r.model == "gpt-4"
        assert r.metadata == {}

    def test_metadata_default_factory(self):
        r1 = SimilarityResult(score=0.5, reason="", model="")
        r2 = SimilarityResult(score=0.5, reason="", model="")
        r1.metadata["key"] = "value"
        assert "key" not in r2.metadata


class TestCaseSimilarityServiceScoring:
    """score_case and rescore_borderline_case with mocked LLM."""

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_score_case_with_json_response(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"score": 0.75, "decision": "medium", "reason": "相似", "facts_match": 0.8, "legal_relation_match": 0.7, "dispute_match": 0.6, "damage_match": 0.5, "key_conflicts": [], "evidence_spans": ["原文1"]}'
        mock_response.model = "test-model"
        mock_llm.chat.return_value = mock_response
        mock_llm_factory.return_value = mock_llm

        svc = CaseSimilarityService()
        result = svc.score_case(
            keyword="买卖合同",
            case_summary="被告未交货，原告要求赔偿价差损失",
            title="买卖合同纠纷判决书",
            case_digest="原告与被告签订买卖合同",
            content_text="本案系买卖合同纠纷案件",
        )
        assert isinstance(result, SimilarityResult)
        assert 0 <= result.score <= 1

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_score_case_with_invalid_json(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "score: 0.6, some text"
        mock_response.model = "test-model"
        mock_llm.chat.return_value = mock_response
        mock_llm_factory.return_value = mock_llm

        svc = CaseSimilarityService()
        result = svc.score_case(
            keyword="买卖合同",
            case_summary="纠纷",
            title="判决书",
            case_digest="摘要",
            content_text="内容",
        )
        assert isinstance(result, SimilarityResult)

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_rescore_borderline_case(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"score": 0.65, "decision": "medium", "reason": "复判相似", "facts_match": 0.7, "legal_relation_match": 0.6, "dispute_match": 0.5, "damage_match": 0.4, "key_conflicts": [], "evidence_spans": ["原文"]}'
        mock_response.model = "test-model"
        mock_llm.chat.return_value = mock_response
        mock_llm_factory.return_value = mock_llm

        svc = CaseSimilarityService()
        result = svc.rescore_borderline_case(
            keyword="买卖合同",
            case_summary="纠纷",
            title="判决书",
            case_digest="摘要",
            content_text="内容",
            first_score=0.55,
            first_reason="首轮理由",
        )
        assert isinstance(result, SimilarityResult)
        assert 0 <= result.score <= 1


class TestCaseSimilarityServiceCoarseRecall:
    """coarse_recall_score tests."""

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_coarse_recall_basic(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_llm_factory.return_value = mock_llm

        svc = CaseSimilarityService()
        result = svc.coarse_recall_score(
            keyword="买卖合同 纠纷",
            case_summary="被告未交货原告要求赔偿",
            title="买卖合同纠纷一案判决书",
            case_digest="原告与被告签订买卖合同被告未按时交货",
            content_text="本案系买卖合同纠纷",
        )
        assert isinstance(result, SimilarityResult)
        assert result.model == "coarse-heuristic"
        assert 0 <= result.score <= 1

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_coarse_recall_empty_content(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_llm_factory.return_value = mock_llm

        svc = CaseSimilarityService()
        result = svc.coarse_recall_score(
            keyword="test",
            case_summary="test",
            title="",
            case_digest="",
            content_text="",
        )
        assert isinstance(result, SimilarityResult)


class TestSemanticVector:
    """Semantic vector similarity tests."""

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_vector_similarity_lexical_only(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_llm_factory.return_value = mock_llm

        svc = CaseSimilarityService()
        score = svc._vector_similarity_score("买卖合同纠纷", "买卖合同纠纷一案", allow_semantic=False)
        assert 0 <= score <= 1

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_should_enable_semantic_vector_recheck_disabled(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_llm_factory.return_value = mock_llm

        svc = CaseSimilarityService()
        svc._semantic_vector_enabled = False
        result = svc._should_enable_semantic_vector_recheck(
            query_text="test", keyword_overlap=0.3, summary_overlap=0.2,
            bm25_score=0.1, lexical_vector_score=0.1, passage_score=0.1, metadata_score=0.1,
        )
        assert result is False


class TestRepairJson:
    """JSON repair tests."""

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_repair_json_success(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"score": 0.5, "reason": "repaired"}'
        mock_llm.chat.return_value = mock_response
        mock_llm_factory.return_value = mock_llm

        svc = CaseSimilarityService()
        result = svc._repair_json_payload(raw_text="broken json", model=None)
        assert isinstance(result, dict)

    @patch("apps.core.interfaces.ServiceLocator.get_llm_service")
    def test_repair_json_empty(self, mock_llm_factory):
        mock_llm = MagicMock()
        mock_llm_factory.return_value = mock_llm

        svc = CaseSimilarityService()
        result = svc._repair_json_payload(raw_text="", model=None)
        assert result is None
