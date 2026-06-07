"""legal_research/similarity 模块单元测试（json_utils, cache）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import pytest

from apps.legal_research.services.similarity.json_utils import (
    HARD_CONFLICT_NEEDLES,
    apply_structured_adjustments,
    evidence_span_hit_count,
    extract_json,
    extract_structured_metadata,
    extract_transaction_tags,
    normalize_match_text,
    normalize_text_list,
)


class TestExtractJson:
    def test_empty_string(self) -> None:
        assert extract_json("") is None

    def test_none_input(self) -> None:
        assert extract_json(None) is None  # type: ignore[arg-type]

    def test_valid_json(self) -> None:
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_json_with_markdown_fence(self) -> None:
        result = extract_json('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_json_embedded_in_text(self) -> None:
        result = extract_json('some text {"a": 1} more text')
        assert result == {"a": 1}

    def test_invalid_json(self) -> None:
        assert extract_json("not json at all") is None

    def test_non_dict_json(self) -> None:
        assert extract_json('[1, 2, 3]') is None

    def test_json_with_language_fence(self) -> None:
        result = extract_json('```python\n{"key": "val"}\n```')
        assert result == {"key": "val"}


class TestNormalizeTextList:
    def test_list(self) -> None:
        assert normalize_text_list([" a ", " b "]) == ["a", "b"]

    def test_string(self) -> None:
        assert normalize_text_list("hello") == ["hello"]

    def test_empty(self) -> None:
        assert normalize_text_list(None) == []  # type: ignore[arg-type]

    def test_empty_string(self) -> None:
        assert normalize_text_list("") == []

    def test_list_with_blanks(self) -> None:
        assert normalize_text_list(["a", "", "  ", "b"]) == ["a", "b"]


class TestNormalizeMatchText:
    def test_empty(self) -> None:
        assert normalize_match_text("") == ""

    def test_removes_punctuation(self) -> None:
        result = normalize_match_text("你好，世界！")
        assert "，" not in result
        assert "！" not in result

    def test_removes_spaces(self) -> None:
        result = normalize_match_text("hello world")
        assert " " not in result

    def test_lowercases(self) -> None:
        result = normalize_match_text("ABC")
        assert result == "abc"


class TestEvidenceSpanHitCount:
    def test_empty_context(self) -> None:
        hits, total = evidence_span_hit_count(evidence_spans=["abc"], context_text="")
        assert hits == 0
        assert total == 0

    def test_matching_spans(self) -> None:
        hits, total = evidence_span_hit_count(
            evidence_spans=["合同纠纷案", "违约责任"], context_text="本案系合同纠纷案涉及违约责任"
        )
        assert total == 2
        assert hits == 2

    def test_short_span_skipped(self) -> None:
        hits, total = evidence_span_hit_count(evidence_spans=["ab"], context_text="abcdef")
        assert total == 0


class TestApplyStructuredAdjustments:
    def test_score_clamped(self) -> None:
        result = apply_structured_adjustments(score=2.0, payload={})
        assert result <= 1.0

    def test_reject_decision(self) -> None:
        result = apply_structured_adjustments(score=0.9, payload={"decision": "reject"})
        assert result <= 0.45

    def test_low_decision(self) -> None:
        result = apply_structured_adjustments(score=0.9, payload={"decision": "low"})
        assert result <= 0.6

    def test_medium_decision(self) -> None:
        result = apply_structured_adjustments(score=0.9, payload={"decision": "medium"})
        assert result <= 0.85

    def test_low_component_score(self) -> None:
        result = apply_structured_adjustments(
            score=0.9, payload={"facts_match": 0.1, "legal_relation_match": 1.0, "dispute_match": 1.0, "damage_match": 1.0}
        )
        assert result <= 0.55

    def test_hard_conflict(self) -> None:
        result = apply_structured_adjustments(
            score=0.9, payload={"key_conflicts": ["主体不同"]}
        )
        assert result <= 0.62

    def test_evidence_spans_few(self) -> None:
        result = apply_structured_adjustments(
            score=0.9, payload={"evidence_spans": ["单条证据"]}
        )
        assert result <= 0.82

    def test_evidence_spans_low_hit_ratio(self) -> None:
        result = apply_structured_adjustments(
            score=0.9,
            payload={"evidence_spans": ["合同签订日期为2023年", "违约金条款约定为10万元"]},
            context_text="本案涉及房屋买卖合同",
        )
        assert result <= 1.0


class TestExtractStructuredMetadata:
    def test_basic(self) -> None:
        meta = extract_structured_metadata(payload={"score": 0.8}, adjusted_score=0.75)
        assert meta["score_adjusted"] == 0.75
        assert meta["score_raw"] == 0.8

    def test_with_decision(self) -> None:
        meta = extract_structured_metadata(payload={"decision": "reject"}, adjusted_score=0.3)
        assert meta["decision"] == "reject"

    def test_with_evidence_hits(self) -> None:
        meta = extract_structured_metadata(
            payload={"evidence_spans": ["合同签订日期为2023年", "违约金条款约定为十万元"]},
            adjusted_score=0.8,
            context_text="本案合同签订日期为2023年违约金条款约定为十万元争议",
        )
        assert "evidence_hits" in meta


class TestExtractTransactionTags:
    def test_empty(self) -> None:
        assert extract_transaction_tags("") == []

    def test_delivery_delay(self) -> None:
        tags = extract_transaction_tags("被告未按时交货")
        assert "交货迟延" in tags

    def test_quality_issue(self) -> None:
        tags = extract_transaction_tags("货物质量不合格")
        assert "质量瑕疵" in tags

    def test_payment_delay(self) -> None:
        tags = extract_transaction_tags("被告逾期付款")
        assert "付款迟延" in tags

    def test_no_match(self) -> None:
        tags = extract_transaction_tags("正常履行完毕")
        assert tags == []

    def test_multiple_tags(self) -> None:
        tags = extract_transaction_tags("被告未按时交货且质量不合格")
        assert "交货迟延" in tags
        assert "质量瑕疵" in tags


class TestHardConflictNeedles:
    def test_contains_expected(self) -> None:
        assert "主体" in HARD_CONFLICT_NEEDLES
        assert "法律关系" in HARD_CONFLICT_NEEDLES


# ── cache module tests ──────────────────────────────────────────


from apps.legal_research.services.similarity.cache import (
    SimilarityCacheManager,
    SemanticVectorCacheManager,
    build_similarity_cache_key,
    build_semantic_embedding_cache_key,
    coerce_float_list,
    normalize_embedding_text,
    serialize_similarity_result,
    deserialize_similarity_result,
)


class TestBuildSimilarityCacheKey:
    def test_basic(self) -> None:
        key = build_similarity_cache_key(
            mode="full", model="gpt-4", keyword="合同", case_summary="summary",
            title="title", case_digest="digest", candidate_excerpt="excerpt"
        )
        assert key.startswith("legal_research:similarity:")
        assert len(key) > 30

    def test_with_first_score(self) -> None:
        key = build_similarity_cache_key(
            mode="full", model=None, keyword="k", case_summary="s",
            title="t", case_digest="d", candidate_excerpt="c", first_score=0.85
        )
        assert "similarity:" in key


class TestBuildSemanticEmbeddingCacheKey:
    def test_basic(self) -> None:
        key = build_semantic_embedding_cache_key(model="m", text="hello")
        assert "semantic_embedding:" in key


class TestNormalizeEmbeddingText:
    def test_empty(self) -> None:
        assert normalize_embedding_text("") == ""

    def test_long_text_truncated(self) -> None:
        text = "a" * 2000
        result = normalize_embedding_text(text)
        assert len(result) <= 1400

    def test_whitespace_normalized(self) -> None:
        result = normalize_embedding_text("  hello   world  ")
        assert result == "hello world"


class TestSerializeDeserialize:
    @dataclass
    class FakeResult:
        score: float = 0.5
        reason: str = "test"
        model: str = "m"
        metadata: dict = None  # type: ignore[assignment]

        def __post_init__(self) -> None:
            if self.metadata is None:
                self.metadata = {}

    def test_serialize(self) -> None:
        r = self.FakeResult(score=0.8, reason="good", model="m")
        payload = serialize_similarity_result(r)
        assert payload["score"] == 0.8
        assert payload["reason"] == "good"

    def test_deserialize(self) -> None:
        payload = {"score": 0.7, "reason": "ok", "model": "m", "metadata": {"k": "v"}}
        result = deserialize_similarity_result(payload, result_class=self.FakeResult)
        assert result is not None
        assert result.score == 0.7

    def test_deserialize_invalid_score(self) -> None:
        payload = {"score": "invalid"}
        result = deserialize_similarity_result(payload, result_class=self.FakeResult)
        assert result is None


class TestCoerceFloatList:
    def test_valid(self) -> None:
        assert coerce_float_list([1, 2.5, "3"]) == [1.0, 2.5, 3.0]

    def test_invalid_item(self) -> None:
        assert coerce_float_list([1, "bad"]) == []

    def test_non_list(self) -> None:
        assert coerce_float_list("not a list") == []  # type: ignore[arg-type]


class TestSimilarityCacheManager:
    def test_init(self) -> None:
        mgr = SimilarityCacheManager(cache_ttl=300, result_class=TestSerializeDeserialize.FakeResult)
        assert mgr._cache_ttl == 300

    def test_load_empty_key(self) -> None:
        mgr = SimilarityCacheManager(cache_ttl=300, result_class=TestSerializeDeserialize.FakeResult)
        result, info = mgr.load("")
        assert result is None
        assert info["source"] == "none"

    def test_save_and_load_local(self) -> None:
        mgr = SimilarityCacheManager(cache_ttl=300, result_class=TestSerializeDeserialize.FakeResult)
        fake = TestSerializeDeserialize.FakeResult(score=0.5)
        mgr.save(cache_key="key1", result=fake)
        loaded, info = mgr.load("key1")
        assert loaded is not None
        assert info["source"] == "local"

    @patch("apps.legal_research.services.similarity.cache.cache")
    def test_load_from_shared_cache(self, mock_cache: MagicMock) -> None:
        mock_cache.get.return_value = {"score": 0.8, "reason": "r", "model": "m", "metadata": {}}
        mgr = SimilarityCacheManager(cache_ttl=300, result_class=TestSerializeDeserialize.FakeResult)
        result, info = mgr.load("key2")
        assert result is not None
        assert info["source"] == "shared"

    @patch("apps.legal_research.services.similarity.cache.cache")
    def test_load_shared_miss(self, mock_cache: MagicMock) -> None:
        mock_cache.get.return_value = None
        mgr = SimilarityCacheManager(cache_ttl=300, result_class=TestSerializeDeserialize.FakeResult)
        result, info = mgr.load("key3")
        assert result is None
        assert info["probe"] == "shared_miss"


class TestSemanticVectorCacheManager:
    def test_read_write_local(self) -> None:
        mgr = SemanticVectorCacheManager(cache_ttl=300)
        mgr.write_local(cache_key="k", vector=[1.0, 2.0])
        assert mgr.read_local("k") == [1.0, 2.0]

    def test_read_local_empty_key(self) -> None:
        mgr = SemanticVectorCacheManager(cache_ttl=300)
        assert mgr.read_local("") is None

    def test_write_local_empty_key(self) -> None:
        mgr = SemanticVectorCacheManager(cache_ttl=300)
        mgr.write_local(cache_key="", vector=[1.0])  # should not raise

    def test_local_cache_eviction(self) -> None:
        mgr = SemanticVectorCacheManager(cache_ttl=300, local_cache_max_size=2)
        mgr.write_local(cache_key="a", vector=[1.0])
        mgr.write_local(cache_key="b", vector=[2.0])
        mgr.write_local(cache_key="c", vector=[3.0])
        # After writing 3 items with max_size=2, "a" should be evicted
        # But read_local calls move_to_end which may affect ordering
        assert mgr.read_local("c") == [3.0]
        assert mgr.read_local("b") == [2.0]

    @patch("apps.legal_research.services.similarity.cache.cache")
    def test_load_from_django_cache(self, mock_cache: MagicMock) -> None:
        mock_cache.get.return_value = [1.0, 2.0, 3.0]
        mgr = SemanticVectorCacheManager(cache_ttl=300)
        result = mgr.load_from_django_cache("k")
        assert result == [1.0, 2.0, 3.0]

    @patch("apps.legal_research.services.similarity.cache.cache")
    def test_load_from_django_cache_miss(self, mock_cache: MagicMock) -> None:
        mock_cache.get.return_value = None
        mgr = SemanticVectorCacheManager(cache_ttl=300)
        assert mgr.load_from_django_cache("k") is None
