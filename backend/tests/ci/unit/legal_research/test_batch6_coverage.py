"""Batch 6 coverage tests for legal_research module."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ── keywords.py ──────────────────────────────────────────────────────────────


class TestNormalizeKeywordQuery:
    def test_empty_string(self):
        from apps.legal_research.services.keywords import normalize_keyword_query

        assert normalize_keyword_query("") == ""

    def test_none_input(self):
        from apps.legal_research.services.keywords import normalize_keyword_query

        assert normalize_keyword_query(None) == ""

    def test_whitespace_only(self):
        from apps.legal_research.services.keywords import normalize_keyword_query

        assert normalize_keyword_query("   ") == ""

    def test_single_keyword(self):
        from apps.legal_research.services.keywords import normalize_keyword_query

        assert normalize_keyword_query("合同纠纷") == "合同纠纷"

    def test_multiple_comma_separated(self):
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同纠纷,违约,损害赔偿")
        assert result == "合同纠纷 违约 损害赔偿"

    def test_deduplication(self):
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同 合同 违约 违约")
        assert result == "合同 违约"

    def test_mixed_separators(self):
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同;违约，损害\t赔偿")
        assert result == "合同 违约 损害 赔偿"

    def test_chinese_separators(self):
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("关键词1、关键词2；关键词3")
        assert result == "关键词1 关键词2 关键词3"


# ── similarity/tuning_config.py ─────────────────────────────────────────────


class TestLegalResearchTuningConfig:
    def test_default_values(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        cfg = LegalResearchTuningConfig()
        assert cfg.recall_weight_keyword == 0.18
        assert cfg.recall_weight_summary == 0.22
        assert cfg.passage_top_k == 5
        assert cfg.dual_review_enabled is True
        assert cfg.reranker_enabled is False

    def test_normalized_recall_weights_defaults(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        cfg = LegalResearchTuningConfig()
        weights = cfg.normalized_recall_weights
        assert len(weights) == 6
        total = sum(weights)
        assert abs(total - 1.0) < 0.001

    def test_normalized_recall_weights_all_zero_fallback(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        cfg = LegalResearchTuningConfig(
            recall_weight_keyword=0.0,
            recall_weight_summary=0.0,
            recall_weight_bm25=0.0,
            recall_weight_vector=0.0,
            recall_weight_passage=0.0,
            recall_weight_metadata=0.0,
        )
        weights = cfg.normalized_recall_weights
        assert len(weights) == 6
        assert abs(sum(weights) - 1.0) < 0.001

    def test_normalized_recall_weights_custom(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        cfg = LegalResearchTuningConfig(
            recall_weight_keyword=1.0,
            recall_weight_summary=1.0,
            recall_weight_bm25=1.0,
            recall_weight_vector=1.0,
            recall_weight_passage=1.0,
            recall_weight_metadata=1.0,
        )
        weights = cfg.normalized_recall_weights
        for w in weights:
            assert abs(w - 1 / 6) < 0.001

    def test_load_with_no_config_service(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        with patch(
            "apps.legal_research.services.similarity.tuning_config._get_config_service",
            return_value=None,
        ):
            cfg = LegalResearchTuningConfig.load()
            assert cfg.reranker_enabled is False

    def test_load_with_exception(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        with patch(
            "apps.legal_research.services.similarity.tuning_config._get_config_service",
            side_effect=RuntimeError("fail"),
        ):
            cfg = LegalResearchTuningConfig.load()
            assert cfg.reranker_enabled is False

    def test_load_with_config_service(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        mock_config = MagicMock()
        mock_config.get_value.return_value = "true"
        with patch(
            "apps.legal_research.services.similarity.tuning_config._get_config_service",
            return_value=mock_config,
        ):
            cfg = LegalResearchTuningConfig.load()
            assert cfg.semantic_vector_always_on is True

    def test_get_int_clamping(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        mock_config = MagicMock()
        mock_config.get_value.return_value = "999"
        result = LegalResearchTuningConfig._get_int(mock_config, "KEY", 5, 1, 50)
        assert result == 50

    def test_get_int_invalid(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        mock_config = MagicMock()
        mock_config.get_value.return_value = "abc"
        result = LegalResearchTuningConfig._get_int(mock_config, "KEY", 5, 1, 50)
        assert result == 5

    def test_get_float_clamping(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        mock_config = MagicMock()
        mock_config.get_value.return_value = "99.9"
        result = LegalResearchTuningConfig._get_float(mock_config, "KEY", 0.5, 0.0, 1.0)
        assert result == 1.0

    def test_get_bool_various(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        mock_config = MagicMock()
        for val in ("1", "true", "yes", "on", "y"):
            mock_config.get_value.return_value = val
            assert LegalResearchTuningConfig._get_bool(mock_config, "KEY", False) is True

        for val in ("0", "false", "no", "off", "n"):
            mock_config.get_value.return_value = val
            assert LegalResearchTuningConfig._get_bool(mock_config, "KEY", True) is False

    def test_get_text_truncation(self):
        from apps.legal_research.services.similarity.tuning_config import (
            LegalResearchTuningConfig,
        )

        mock_config = MagicMock()
        mock_config.get_value.return_value = "a" * 200
        result = LegalResearchTuningConfig._get_text(mock_config, "KEY", "default", max_len=10)
        assert len(result) == 10


# ── similarity/cache.py ─────────────────────────────────────────────────────


class TestSimilarityCache:
    def test_build_similarity_cache_key(self):
        from apps.legal_research.services.similarity.cache import (
            build_similarity_cache_key,
        )

        key = build_similarity_cache_key(
            mode="test",
            model="gpt-4",
            keyword="合同",
            case_summary="违约",
            title="案例标题",
            case_digest="摘要",
            candidate_excerpt="候选",
        )
        assert key.startswith("legal_research:similarity:")
        assert len(key) > 30

    def test_build_cache_key_with_first_score(self):
        from apps.legal_research.services.similarity.cache import (
            build_similarity_cache_key,
        )

        key = build_similarity_cache_key(
            mode="test",
            model=None,
            keyword="合同",
            case_summary="违约",
            title="标题",
            case_digest="摘要",
            candidate_excerpt="候选",
            first_score=0.85,
            first_reason="高度相似",
        )
        assert "legal_research:similarity:" in key

    def test_build_semantic_embedding_cache_key(self):
        from apps.legal_research.services.similarity.cache import (
            build_semantic_embedding_cache_key,
        )

        key = build_semantic_embedding_cache_key(model="bge", text="测试文本")
        assert key.startswith("legal_research:semantic_embedding:")

    def test_normalize_embedding_text(self):
        from apps.legal_research.services.similarity.cache import (
            normalize_embedding_text,
        )

        assert normalize_embedding_text("") == ""
        assert normalize_embedding_text(None) == ""
        assert normalize_embedding_text("  hello  world  ") == "hello world"

    def test_normalize_embedding_text_truncation(self):
        from apps.legal_research.services.similarity.cache import (
            SEMANTIC_EMBEDDING_TEXT_MAX_CHARS,
            normalize_embedding_text,
        )

        long_text = "a" * 2000
        result = normalize_embedding_text(long_text)
        assert len(result) == SEMANTIC_EMBEDDING_TEXT_MAX_CHARS

    def test_serialize_deserialize_similarity_result(self):
        from apps.legal_research.services.similarity.cache import (
            deserialize_similarity_result,
            serialize_similarity_result,
        )

        obj = SimpleNamespace(score=0.85, reason="相似", model="gpt", metadata={"key": "val"})
        payload = serialize_similarity_result(obj)
        assert payload["score"] == 0.85
        assert payload["reason"] == "相似"

        restored = deserialize_similarity_result(payload, result_class=SimpleNamespace)
        assert restored.score == 0.85

    def test_deserialize_invalid_score(self):
        from apps.legal_research.services.similarity.cache import (
            deserialize_similarity_result,
        )

        result = deserialize_similarity_result({"score": "abc"}, result_class=SimpleNamespace)
        assert result is None

    def test_coerce_float_list(self):
        from apps.legal_research.services.similarity.cache import coerce_float_list

        assert coerce_float_list([1, 2, 3]) == [1.0, 2.0, 3.0]
        assert coerce_float_list("not a list") == []
        assert coerce_float_list([1, "abc", 3]) == []

    def test_similarity_cache_manager_load_empty_key(self):
        from apps.legal_research.services.similarity.cache import (
            SimilarityCacheManager,
        )

        mgr = SimilarityCacheManager(cache_ttl=3600, result_class=SimpleNamespace)
        result, meta = mgr.load("")
        assert result is None
        assert meta["source"] == "none"

    def test_similarity_cache_manager_save_and_load_local(self):
        from apps.legal_research.services.similarity.cache import (
            SimilarityCacheManager,
        )

        mgr = SimilarityCacheManager(cache_ttl=3600, result_class=SimpleNamespace)
        obj = SimpleNamespace(score=0.9, reason="test", model="m", metadata={})
        mgr.save(cache_key="test_key", result=obj)
        loaded, meta = mgr.load("test_key")
        assert loaded is not None
        assert meta["source"] == "local"

    def test_similarity_cache_manager_eviction(self):
        from apps.legal_research.services.similarity.cache import (
            SimilarityCacheManager,
        )

        # min local_cache_max_size is 32 (enforced by constructor)
        mgr = SimilarityCacheManager(cache_ttl=3600, local_cache_max_size=32, result_class=SimpleNamespace)
        obj = SimpleNamespace(score=0.5, reason="", model="", metadata={})
        for i in range(35):
            mgr._write_local(cache_key=f"k{i}", result=obj)
        assert len(mgr._local_cache) == 32
        assert mgr._read_local("k0") is None  # evicted from local
        assert mgr._read_local("k34") is not None  # still in local

    def test_semantic_vector_cache_manager(self):
        from apps.legal_research.services.similarity.cache import (
            SemanticVectorCacheManager,
        )

        mgr = SemanticVectorCacheManager(cache_ttl=3600)
        mgr.write_local(cache_key="vec1", vector=[0.1, 0.2, 0.3])
        assert mgr.read_local("vec1") == [0.1, 0.2, 0.3]
        assert mgr.read_local("") is None
        assert mgr.read_local("nonexistent") is None


# ── similarity/json_utils.py ────────────────────────────────────────────────


class TestJsonUtils:
    def test_extract_json_plain(self):
        from apps.legal_research.services.similarity.json_utils import extract_json

        result = extract_json('{"score": 0.8, "reason": "test"}')
        assert result == {"score": 0.8, "reason": "test"}

    def test_extract_json_code_block(self):
        from apps.legal_research.services.similarity.json_utils import extract_json

        text = '```json\n{"score": 0.8}\n```'
        result = extract_json(text)
        assert result == {"score": 0.8}

    def test_extract_json_with_surrounding_text(self):
        from apps.legal_research.services.similarity.json_utils import extract_json

        text = 'Here is the result: {"score": 0.9} done.'
        result = extract_json(text)
        assert result == {"score": 0.9}

    def test_extract_json_empty(self):
        from apps.legal_research.services.similarity.json_utils import extract_json

        assert extract_json("") is None
        assert extract_json(None) is None

    def test_extract_json_invalid(self):
        from apps.legal_research.services.similarity.json_utils import extract_json

        assert extract_json("no json here") is None

    def test_normalize_text_list(self):
        from apps.legal_research.services.similarity.json_utils import (
            normalize_text_list,
        )

        assert normalize_text_list(["a", "b"]) == ["a", "b"]
        assert normalize_text_list("hello") == ["hello"]
        assert normalize_text_list(123) == []
        assert normalize_text_list([]) == []

    def test_normalize_match_text(self):
        from apps.legal_research.services.similarity.json_utils import (
            normalize_match_text,
        )

        assert normalize_match_text("") == ""
        assert normalize_match_text(None) == ""
        result = normalize_match_text("合同纠纷，违约。")
        assert "，" not in result
        assert "。" not in result

    def test_evidence_span_hit_count(self):
        from apps.legal_research.services.similarity.json_utils import (
            evidence_span_hit_count,
        )

        hits, total = evidence_span_hit_count(
            evidence_spans=["合同签订", "违约行为"],
            context_text="本案中存在合同签订和违约行为的事实",
        )
        assert total == 2
        assert hits == 2

    def test_evidence_span_hit_count_partial(self):
        from apps.legal_research.services.similarity.json_utils import (
            evidence_span_hit_count,
        )

        hits, total = evidence_span_hit_count(
            evidence_spans=["合同签订", "不存在的文本"],
            context_text="本案中存在合同签订的事实",
        )
        assert total == 2
        assert hits == 1

    def test_evidence_span_short_span_skipped(self):
        from apps.legal_research.services.similarity.json_utils import (
            evidence_span_hit_count,
        )

        hits, total = evidence_span_hit_count(
            evidence_spans=["ab"],  # too short
            context_text="some text",
        )
        assert total == 0
        assert hits == 0

    def test_apply_structured_adjustments_reject(self):
        from apps.legal_research.services.similarity.json_utils import (
            apply_structured_adjustments,
        )

        result = apply_structured_adjustments(
            score=0.9,
            payload={"decision": "reject"},
        )
        assert result <= 0.45

    def test_apply_structured_adjustments_low(self):
        from apps.legal_research.services.similarity.json_utils import (
            apply_structured_adjustments,
        )

        result = apply_structured_adjustments(
            score=0.9,
            payload={"decision": "low"},
        )
        assert result <= 0.6

    def test_apply_structured_adjustments_medium(self):
        from apps.legal_research.services.similarity.json_utils import (
            apply_structured_adjustments,
        )

        result = apply_structured_adjustments(
            score=0.95,
            payload={"decision": "medium"},
        )
        assert result <= 0.85

    def test_apply_structured_adjustments_low_component(self):
        from apps.legal_research.services.similarity.json_utils import (
            apply_structured_adjustments,
        )

        result = apply_structured_adjustments(
            score=0.9,
            payload={"facts_match": 0.1},
        )
        assert result <= 0.55

    def test_apply_structured_adjustments_conflict(self):
        from apps.legal_research.services.similarity.json_utils import (
            apply_structured_adjustments,
        )

        result = apply_structured_adjustments(
            score=0.9,
            payload={"key_conflicts": ["主体不一致"]},
        )
        assert result <= 0.62

    def test_apply_structured_adjustments_no_evidence(self):
        from apps.legal_research.services.similarity.json_utils import (
            apply_structured_adjustments,
        )

        result = apply_structured_adjustments(
            score=0.9,
            payload={"evidence_spans": ["single_span"]},
        )
        assert result <= 0.82

    def test_extract_structured_metadata(self):
        from apps.legal_research.services.similarity.json_utils import (
            extract_structured_metadata,
        )

        metadata = extract_structured_metadata(
            payload={
                "score": 0.8,
                "decision": "similar",
                "facts_match": 0.9,
                "key_conflicts": ["无冲突"],
                "evidence_spans": ["合同签订事实"],
            },
            adjusted_score=0.75,
            context_text="本案合同签订事实清楚",
        )
        assert metadata["score_adjusted"] == 0.75
        assert metadata["score_raw"] == 0.8
        assert metadata["decision"] == "similar"

    def test_extract_transaction_tags(self):
        from apps.legal_research.services.similarity.json_utils import (
            extract_transaction_tags,
        )

        assert extract_transaction_tags("") == []
        assert extract_transaction_tags(None) == []
        tags = extract_transaction_tags("被告逾期交货，且质量瑕疵严重")
        assert "交货迟延" in tags
        assert "质量瑕疵" in tags

    def test_extract_transaction_tags_payment_delay(self):
        from apps.legal_research.services.similarity.json_utils import (
            extract_transaction_tags,
        )

        tags = extract_transaction_tags("被告拖欠货款，逾期付款")
        assert "付款迟延" in tags

    def test_extract_transaction_tags_price_dispute(self):
        from apps.legal_research.services.similarity.json_utils import (
            extract_transaction_tags,
        )

        tags = extract_transaction_tags("双方对市场价格产生争议")
        assert "价差争议" in tags


# ── task/state_sync.py ──────────────────────────────────────────────────────


class TestStateSync:
    def test_sync_failed_queue_state_wrong_status(self):
        from apps.legal_research.services.task.state_sync import (
            sync_failed_queue_state,
        )

        task = SimpleNamespace(status="completed", q_task_id="abc")
        assert sync_failed_queue_state(task=task) is False

    def test_sync_failed_queue_state_no_q_task_id(self):
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.task.state_sync import (
            sync_failed_queue_state,
        )

        task = SimpleNamespace(status=LegalResearchTaskStatus.QUEUED, q_task_id="")
        assert sync_failed_queue_state(task=task) is False

    def test_sync_failed_queue_state_exception(self):
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.task.state_sync import (
            sync_failed_queue_state,
        )

        task = SimpleNamespace(status=LegalResearchTaskStatus.QUEUED, q_task_id="q1")
        with patch(
            "apps.core.tasking.TaskQueryService",
            side_effect=RuntimeError("fail"),
        ):
            assert sync_failed_queue_state(task=task) is False

    def test_sync_failed_queue_state_none_info(self):
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.task.state_sync import (
            sync_failed_queue_state,
        )

        mock_tqs_cls = MagicMock()
        mock_tqs_cls.return_value.get_failed_task_info.return_value = None
        task = SimpleNamespace(status=LegalResearchTaskStatus.QUEUED, q_task_id="q1")
        with patch(
            "apps.core.tasking.TaskQueryService",
            mock_tqs_cls,
        ):
            assert sync_failed_queue_state(task=task) is False


# ── task/event_service.py ───────────────────────────────────────────────────


class TestEventService:
    def test_normalize_task_id(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        svc = LegalResearchTaskEventService
        assert svc._normalize_task_id(None) is None
        assert svc._normalize_task_id("") is None
        assert svc._normalize_task_id("abc") is None
        assert svc._normalize_task_id("-1") is None
        assert svc._normalize_task_id("0") is None
        assert svc._normalize_task_id("42") == 42

    def test_normalize_status_code(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        svc = LegalResearchTaskEventService
        assert svc._normalize_status_code(None) is None
        assert svc._normalize_status_code("abc") is None
        assert svc._normalize_status_code(50) is None
        assert svc._normalize_status_code(1000) is None
        assert svc._normalize_status_code(200) == 200

    def test_sanitize_url(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        svc = LegalResearchTaskEventService
        assert svc._sanitize_url("") == ""
        assert svc._sanitize_url(None) == ""
        url = svc._sanitize_url("https://api.example.com?password=secret123&key=abc")
        assert "secret123" not in url
        assert "***" in url

    def test_sanitize_url_truncation(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        svc = LegalResearchTaskEventService
        long_url = "https://example.com/" + "a" * 2000
        result = svc._sanitize_url(long_url)
        assert len(result) <= svc.MAX_URL_CHARS

    def test_sanitize_node_none(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        assert LegalResearchTaskEventService._sanitize_node(value=None, level=0, key_hint="") is None

    def test_sanitize_node_max_depth(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        assert LegalResearchTaskEventService._sanitize_node(value="x", level=5, key_hint="") == "..."

    def test_sanitize_node_dict(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        result = LegalResearchTaskEventService._sanitize_node(
            value={"key": "val", "password": "secret"}, level=0, key_hint=""
        )
        assert result["password"] == "***"

    def test_sanitize_node_list(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        result = LegalResearchTaskEventService._sanitize_node(
            value=["a", "b", "c"], level=0, key_hint=""
        )
        assert len(result) == 3

    def test_sanitize_node_bytes(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        result = LegalResearchTaskEventService._sanitize_node(
            value=b"hello", level=0, key_hint=""
        )
        assert "bytes" in result

    def test_sanitize_node_sensitive_value(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        result = LegalResearchTaskEventService._sanitize_node(
            value="my_secret", level=0, key_hint="api_key"
        )
        assert result == "***"

    def test_sanitize_node_long_string(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        long_str = "a" * 500
        result = LegalResearchTaskEventService._sanitize_node(
            value=long_str, level=0, key_hint=""
        )
        assert len(result) <= LegalResearchTaskEventService.MAX_STRING_CHARS

    def test_sanitize_payload_dict(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        result = LegalResearchTaskEventService._sanitize_payload({"a": "val1", "b": "val2"})
        assert isinstance(result, dict)
        assert result["a"] == "val1"

    def test_sanitize_payload_none(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        result = LegalResearchTaskEventService._sanitize_payload(None)
        assert isinstance(result, dict)

    def test_sanitize_payload_string(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        result = LegalResearchTaskEventService._sanitize_payload("hello")
        assert isinstance(result, dict)

    def test_sanitize_payload_large_truncated(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        large = {"field" + str(i): "x" * 100 for i in range(100)}
        result = LegalResearchTaskEventService._sanitize_payload(large)
        assert isinstance(result, dict)

    def test_is_sensitive_key(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        svc = LegalResearchTaskEventService
        assert svc._is_sensitive_key("password") is True
        assert svc._is_sensitive_key("api_key") is True
        assert svc._is_sensitive_key("my_token_value") is True
        assert svc._is_sensitive_key("") is False
        assert svc._is_sensitive_key("name") is False

    def test_run_orm_safely_sync(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        result = LegalResearchTaskEventService._run_orm_safely(lambda: 42)
        assert result == 42

    def test_dict_truncation(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        big_dict = {f"k{i}": i for i in range(50)}
        result = LegalResearchTaskEventService._sanitize_node(
            value=big_dict, level=0, key_hint=""
        )
        assert result.get("__truncated__") is True

    def test_list_truncation(self):
        from apps.legal_research.services.task.event_service import (
            LegalResearchTaskEventService,
        )

        big_list = list(range(50))
        result = LegalResearchTaskEventService._sanitize_node(
            value=big_list, level=0, key_hint=""
        )
        assert len(result) == LegalResearchTaskEventService.MAX_LIST_ITEMS + 1
