"""Tests for similarity module: tuning_config, cache, json_utils, reranker."""
from __future__ import annotations

from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ── tuning_config ──────────────────────────────────────────────────────────


class TestTuningConfig:
    def test_defaults(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config = LegalResearchTuningConfig()
        assert config.recall_weight_keyword == 0.18
        assert config.passage_top_k == 5
        assert config.dual_review_enabled is True
        assert config.adaptive_threshold_enabled is True

    def test_normalized_recall_weights_defaults(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config = LegalResearchTuningConfig()
        weights = config.normalized_recall_weights
        assert len(weights) == 6
        assert abs(sum(weights) - 1.0) < 1e-6

    def test_normalized_recall_weights_all_zero(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config = LegalResearchTuningConfig(
            recall_weight_keyword=0,
            recall_weight_summary=0,
            recall_weight_bm25=0,
            recall_weight_vector=0,
            recall_weight_passage=0,
            recall_weight_metadata=0,
        )
        weights = config.normalized_recall_weights
        assert abs(sum(weights) - 1.0) < 1e-6

    def test_get_int_valid(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config_service = MagicMock()
        config_service.get_value.return_value = "42"
        result = LegalResearchTuningConfig._get_int(config_service, "key", 10, 1, 100)
        assert result == 42

    def test_get_int_clamped(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config_service = MagicMock()
        config_service.get_value.return_value = "200"
        result = LegalResearchTuningConfig._get_int(config_service, "key", 10, 1, 100)
        assert result == 100

    def test_get_int_invalid(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config_service = MagicMock()
        config_service.get_value.return_value = "abc"
        result = LegalResearchTuningConfig._get_int(config_service, "key", 10, 1, 100)
        assert result == 10

    def test_get_float_valid(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config_service = MagicMock()
        config_service.get_value.return_value = "0.75"
        result = LegalResearchTuningConfig._get_float(config_service, "key", 0.5, 0.0, 1.0)
        assert result == pytest.approx(0.75)

    def test_get_float_clamped(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config_service = MagicMock()
        config_service.get_value.return_value = "2.0"
        result = LegalResearchTuningConfig._get_float(config_service, "key", 0.5, 0.0, 1.0)
        assert result == pytest.approx(1.0)

    def test_get_bool_truthy(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config_service = MagicMock()
        for v in ("1", "true", "yes", "on", "y"):
            config_service.get_value.return_value = v
            assert LegalResearchTuningConfig._get_bool(config_service, "key", False) is True

    def test_get_bool_falsy(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config_service = MagicMock()
        for v in ("0", "false", "no", "off", "n"):
            config_service.get_value.return_value = v
            assert LegalResearchTuningConfig._get_bool(config_service, "key", True) is False

    def test_get_text_valid(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config_service = MagicMock()
        config_service.get_value.return_value = "test_value"
        result = LegalResearchTuningConfig._get_text(config_service, "key", "default", max_len=100)
        assert result == "test_value"

    def test_get_text_empty_returns_default(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config_service = MagicMock()
        config_service.get_value.return_value = ""
        result = LegalResearchTuningConfig._get_text(config_service, "key", "default", max_len=100)
        assert result == "default"

    def test_get_text_truncated(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        config_service = MagicMock()
        config_service.get_value.return_value = "x" * 200
        result = LegalResearchTuningConfig._get_text(config_service, "key", "default", max_len=50)
        assert len(result) == 50


# ── cache ──────────────────────────────────────────────────────────────────


class TestCache:
    def test_build_similarity_cache_key_deterministic(self) -> None:
        from apps.legal_research.services.similarity.cache import build_similarity_cache_key

        key1 = build_similarity_cache_key(
            mode="expanded", model="m", keyword="k", case_summary="s",
            title="t", case_digest="d", candidate_excerpt="c",
        )
        key2 = build_similarity_cache_key(
            mode="expanded", model="m", keyword="k", case_summary="s",
            title="t", case_digest="d", candidate_excerpt="c",
        )
        assert key1 == key2

    def test_build_similarity_cache_key_different_inputs(self) -> None:
        from apps.legal_research.services.similarity.cache import build_similarity_cache_key

        key1 = build_similarity_cache_key(
            mode="expanded", model="m", keyword="k1", case_summary="s",
            title="t", case_digest="d", candidate_excerpt="c",
        )
        key2 = build_similarity_cache_key(
            mode="expanded", model="m", keyword="k2", case_summary="s",
            title="t", case_digest="d", candidate_excerpt="c",
        )
        assert key1 != key2

    def test_build_similarity_cache_key_with_first_score(self) -> None:
        from apps.legal_research.services.similarity.cache import build_similarity_cache_key

        key1 = build_similarity_cache_key(
            mode="expanded", model="m", keyword="k", case_summary="s",
            title="t", case_digest="d", candidate_excerpt="c", first_score=0.8,
        )
        key2 = build_similarity_cache_key(
            mode="expanded", model="m", keyword="k", case_summary="s",
            title="t", case_digest="d", candidate_excerpt="c", first_score=0.9,
        )
        assert key1 != key2

    def test_build_semantic_embedding_cache_key(self) -> None:
        from apps.legal_research.services.similarity.cache import build_semantic_embedding_cache_key

        key = build_semantic_embedding_cache_key(model="m1", text="hello")
        assert "legal_research:semantic_embedding:" in key

    def test_normalize_embedding_text(self) -> None:
        from apps.legal_research.services.similarity.cache import normalize_embedding_text

        assert normalize_embedding_text("  hello  world  ") == "hello world"
        assert normalize_embedding_text("") == ""
        assert normalize_embedding_text(None) == ""  # type: ignore[arg-type]

    def test_normalize_embedding_text_truncates(self) -> None:
        from apps.legal_research.services.similarity.cache import (
            SEMANTIC_EMBEDDING_TEXT_MAX_CHARS,
            normalize_embedding_text,
        )

        text = "x" * 2000
        result = normalize_embedding_text(text)
        assert len(result) == SEMANTIC_EMBEDDING_TEXT_MAX_CHARS

    def test_serialize_similarity_result(self) -> None:
        from apps.legal_research.services.similarity.cache import serialize_similarity_result

        result = SimpleNamespace(score=0.85, reason="good match", model="test", metadata={"k": "v"})
        payload = serialize_similarity_result(result)
        assert payload["score"] == 0.85
        assert payload["reason"] == "good match"

    def test_deserialize_similarity_result(self) -> None:
        from apps.legal_research.services.similarity.cache import deserialize_similarity_result

        payload = {"score": 0.8, "reason": "test", "model": "m", "metadata": {"k": "v"}}
        result = deserialize_similarity_result(payload, result_class=SimpleNamespace)
        assert result.score == 0.8
        assert result.reason == "test"

    def test_deserialize_similarity_result_invalid_score(self) -> None:
        from apps.legal_research.services.similarity.cache import deserialize_similarity_result

        payload = {"score": "abc", "reason": "test", "model": "m", "metadata": {}}
        result = deserialize_similarity_result(payload, result_class=SimpleNamespace)
        assert result is None

    def test_coerce_float_list_valid(self) -> None:
        from apps.legal_research.services.similarity.cache import coerce_float_list

        assert coerce_float_list([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]
        assert coerce_float_list(["1.0", "2.0"]) == [1.0, 2.0]

    def test_coerce_float_list_invalid(self) -> None:
        from apps.legal_research.services.similarity.cache import coerce_float_list

        assert coerce_float_list([1.0, "abc", 3.0]) == []
        assert coerce_float_list("not a list") == []  # type: ignore[arg-type]
        assert coerce_float_list([]) == []

    def test_similarity_cache_manager_save_and_load_local(self) -> None:
        from apps.legal_research.services.similarity.cache import SimilarityCacheManager

        mgr = SimilarityCacheManager(cache_ttl=3600, result_class=SimpleNamespace)
        result = SimpleNamespace(score=0.8, reason="test", model="m", metadata={})
        mgr.save(cache_key="test_key", result=result)
        loaded, info = mgr.load("test_key")
        assert loaded is not None
        assert info["source"] == "local"

    def test_similarity_cache_manager_load_empty_key(self) -> None:
        from apps.legal_research.services.similarity.cache import SimilarityCacheManager

        mgr = SimilarityCacheManager(cache_ttl=3600, result_class=SimpleNamespace)
        loaded, info = mgr.load("")
        assert loaded is None
        assert info["source"] == "none"

    def test_similarity_cache_manager_local_eviction(self) -> None:
        from apps.legal_research.services.similarity.cache import SimilarityCacheManager

        # Minimum local_cache_max_size is 32 (enforced by max(32, ...))
        mgr = SimilarityCacheManager(cache_ttl=3600, local_cache_max_size=32, result_class=SimpleNamespace)
        for i in range(40):
            result = SimpleNamespace(score=0.5, reason="", model="", metadata={})
            mgr._write_local(cache_key=f"key_{i}", result=result)
        assert len(mgr._local_cache) <= 32

    def test_semantic_vector_cache_manager_local(self) -> None:
        from apps.legal_research.services.similarity.cache import SemanticVectorCacheManager

        mgr = SemanticVectorCacheManager(cache_ttl=3600)
        mgr.write_local(cache_key="k1", vector=[1.0, 2.0])
        assert mgr.read_local("k1") == [1.0, 2.0]

    def test_semantic_vector_cache_manager_eviction(self) -> None:
        from apps.legal_research.services.similarity.cache import SemanticVectorCacheManager

        # Minimum local_cache_max_size is 64
        mgr = SemanticVectorCacheManager(cache_ttl=3600, local_cache_max_size=64)
        for i in range(80):
            mgr.write_local(cache_key=f"k{i}", vector=[float(i)])
        assert len(mgr._local_cache) <= 64

    def test_semantic_vector_cache_manager_read_empty_key(self) -> None:
        from apps.legal_research.services.similarity.cache import SemanticVectorCacheManager

        mgr = SemanticVectorCacheManager(cache_ttl=3600)
        assert mgr.read_local("") is None


# ── json_utils ─────────────────────────────────────────────────────────────


class TestJsonUtils:
    def test_extract_json_plain(self) -> None:
        from apps.legal_research.services.similarity.json_utils import extract_json

        result = extract_json('{"score": 0.8}')
        assert result == {"score": 0.8}

    def test_extract_json_code_block(self) -> None:
        from apps.legal_research.services.similarity.json_utils import extract_json

        text = '```json\n{"score": 0.8}\n```'
        result = extract_json(text)
        assert result == {"score": 0.8}

    def test_extract_json_embedded(self) -> None:
        from apps.legal_research.services.similarity.json_utils import extract_json

        text = 'Here is the result: {"score": 0.8} done.'
        result = extract_json(text)
        assert result == {"score": 0.8}

    def test_extract_json_empty(self) -> None:
        from apps.legal_research.services.similarity.json_utils import extract_json

        assert extract_json("") is None
        assert extract_json(None) is None  # type: ignore[arg-type]

    def test_extract_json_invalid(self) -> None:
        from apps.legal_research.services.similarity.json_utils import extract_json

        assert extract_json("no json here") is None

    def test_normalize_text_list_list(self) -> None:
        from apps.legal_research.services.similarity.json_utils import normalize_text_list

        assert normalize_text_list(["a", " b ", ""]) == ["a", "b"]

    def test_normalize_text_list_string(self) -> None:
        from apps.legal_research.services.similarity.json_utils import normalize_text_list

        assert normalize_text_list("hello") == ["hello"]

    def test_normalize_text_list_empty(self) -> None:
        from apps.legal_research.services.similarity.json_utils import normalize_text_list

        assert normalize_text_list(None) == []
        assert normalize_text_list(42) == []  # type: ignore[arg-type]
        assert normalize_text_list([]) == []

    def test_normalize_match_text(self) -> None:
        from apps.legal_research.services.similarity.json_utils import normalize_match_text

        assert normalize_match_text("Hello, World!") == "helloworld"
        assert normalize_match_text("") == ""
        assert normalize_match_text(None) == ""  # type: ignore[arg-type]

    def test_evidence_span_hit_count(self) -> None:
        from apps.legal_research.services.similarity.json_utils import evidence_span_hit_count

        hits, total = evidence_span_hit_count(
            evidence_spans=["合同纠纷", "违约责任"],
            context_text="本案系合同纠纷案件，被告应承担违约责任。",
        )
        assert total == 2
        assert hits == 2

    def test_evidence_span_hit_count_partial(self) -> None:
        from apps.legal_research.services.similarity.json_utils import evidence_span_hit_count

        hits, total = evidence_span_hit_count(
            evidence_spans=["合同纠纷", "不存在的内容"],
            context_text="本案系合同纠纷案件。",
        )
        assert total == 2
        assert hits == 1

    def test_evidence_span_hit_count_short_span(self) -> None:
        from apps.legal_research.services.similarity.json_utils import evidence_span_hit_count

        hits, total = evidence_span_hit_count(
            evidence_spans=["ab"],  # too short
            context_text="abcdefg",
        )
        assert total == 0

    def test_apply_structured_adjustments_reject(self) -> None:
        from apps.legal_research.services.similarity.json_utils import apply_structured_adjustments

        result = apply_structured_adjustments(score=0.9, payload={"decision": "reject"})
        assert result <= 0.45

    def test_apply_structured_adjustments_low(self) -> None:
        from apps.legal_research.services.similarity.json_utils import apply_structured_adjustments

        result = apply_structured_adjustments(score=0.9, payload={"decision": "low"})
        assert result <= 0.6

    def test_apply_structured_adjustments_medium(self) -> None:
        from apps.legal_research.services.similarity.json_utils import apply_structured_adjustments

        result = apply_structured_adjustments(score=0.95, payload={"decision": "medium"})
        assert result <= 0.85

    def test_apply_structured_adjustments_min_component_low(self) -> None:
        from apps.legal_research.services.similarity.json_utils import apply_structured_adjustments

        result = apply_structured_adjustments(
            score=0.9,
            payload={"facts_match": 0.1, "legal_relation_match": 1.0, "dispute_match": 1.0, "damage_match": 1.0},
        )
        assert result <= 0.55

    def test_apply_structured_adjustments_hard_conflict(self) -> None:
        from apps.legal_research.services.similarity.json_utils import apply_structured_adjustments

        result = apply_structured_adjustments(
            score=0.9,
            payload={"key_conflicts": ["主体不一致"]},
        )
        assert result <= 0.62

    def test_apply_structured_adjustments_evidence_single_span(self) -> None:
        from apps.legal_research.services.similarity.json_utils import apply_structured_adjustments

        result = apply_structured_adjustments(
            score=0.95,
            payload={"evidence_spans": ["唯一的证据"]},
        )
        assert result <= 0.82

    def test_extract_structured_metadata_basic(self) -> None:
        from apps.legal_research.services.similarity.json_utils import extract_structured_metadata

        payload = {
            "score": 0.8,
            "decision": "high",
            "facts_match": 0.9,
            "legal_relation_match": 0.8,
            "dispute_match": 0.7,
            "damage_match": 0.6,
            "key_conflicts": ["test conflict"],
            "evidence_spans": ["span1", "span2"],
        }
        meta = extract_structured_metadata(payload=payload, adjusted_score=0.75, context_text="span1 span2")
        assert meta["score_adjusted"] == 0.75
        assert meta["decision"] == "high"
        assert "key_conflicts" in meta
        assert "evidence_hits" in meta

    def test_extract_transaction_tags(self) -> None:
        from apps.legal_research.services.similarity.json_utils import extract_transaction_tags

        tags = extract_transaction_tags("被告逾期交货且质量瑕疵")
        assert "交货迟延" in tags
        assert "质量瑕疵" in tags

    def test_extract_transaction_tags_empty(self) -> None:
        from apps.legal_research.services.similarity.json_utils import extract_transaction_tags

        assert extract_transaction_tags("") == []
        assert extract_transaction_tags(None) == []  # type: ignore[arg-type]

    def test_extract_transaction_tags_no_match(self) -> None:
        from apps.legal_research.services.similarity.json_utils import extract_transaction_tags

        assert extract_transaction_tags("普通的文本描述") == []


# ── reranker ───────────────────────────────────────────────────────────────


class TestReranker:
    def test_rerank_empty_query(self) -> None:
        from apps.legal_research.services.similarity.reranker import RerankerClient

        reranker = RerankerClient(api_key="test")  # pragma: allowlist secret
        assert reranker.rerank(query="", documents=["doc1"]) == []

    def test_rerank_empty_documents(self) -> None:
        from apps.legal_research.services.similarity.reranker import RerankerClient

        reranker = RerankerClient(api_key="test")  # pragma: allowlist secret
        assert reranker.rerank(query="test", documents=[]) == []

    def test_rerank_cooldown(self) -> None:
        from apps.legal_research.services.similarity.reranker import RerankerClient

        reranker = RerankerClient(api_key="test")  # pragma: allowlist secret
        reranker._fail_until = 9999999999.0
        assert reranker.rerank(query="test", documents=["doc1"]) == []

    @patch("apps.legal_research.services.similarity.reranker.httpx.Client")
    def test_rerank_success(self, mock_client_cls) -> None:
        from apps.legal_research.services.similarity.reranker import RerankerClient

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.5},
            ]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        reranker = RerankerClient(api_key="test")  # pragma: allowlist secret
        results = reranker.rerank(query="test query", documents=["doc0", "doc1"])
        assert len(results) == 2
        assert results[0][0] == 1  # highest score first
        assert results[0][1] == 0.9

    @patch("apps.legal_research.services.similarity.reranker.httpx.Client")
    def test_rerank_api_failure(self, mock_client_cls) -> None:
        from apps.legal_research.services.similarity.reranker import RerankerClient

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = RuntimeError("network error")
        mock_client_cls.return_value = mock_client

        reranker = RerankerClient(api_key="test")  # pragma: allowlist secret
        result = reranker.rerank(query="test", documents=["doc1"])
        assert result == []
        assert reranker._fail_until > 0

    def test_create_reranker_disabled(self) -> None:
        from apps.legal_research.services.similarity.reranker import create_reranker_from_tuning

        tuning = MagicMock()
        tuning.reranker_enabled = False
        assert create_reranker_from_tuning(tuning) is None

    @patch("apps.core.interfaces.ServiceLocator")
    def test_create_reranker_no_api_key(self, mock_locator) -> None:
        from apps.legal_research.services.similarity.reranker import create_reranker_from_tuning

        tuning = MagicMock()
        tuning.reranker_enabled = True
        mock_config = MagicMock()
        mock_config.get_value.return_value = ""
        mock_locator.get_system_config_service.return_value = mock_config

        assert create_reranker_from_tuning(tuning) is None

    @patch("apps.core.interfaces.ServiceLocator")
    def test_create_reranker_success(self, mock_locator) -> None:
        from apps.legal_research.services.similarity.reranker import create_reranker_from_tuning

        tuning = MagicMock()
        tuning.reranker_enabled = True
        tuning.reranker_api_base_url = "https://api.test.com"
        tuning.reranker_model = "test-model"
        mock_config = MagicMock()
        mock_config.get_value.return_value = "test-api-key"
        mock_locator.get_system_config_service.return_value = mock_config

        reranker = create_reranker_from_tuning(tuning)
        assert reranker is not None
        assert reranker._api_key == "test-api-key"
