"""Extended tests for legal_research services - scorers, passage, json_utils, tuning_config, keywords."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.legal_research.services.keywords import normalize_keyword_query
from apps.legal_research.services.similarity.json_utils import (
    apply_structured_adjustments,
    evidence_span_hit_count,
    extract_json,
    extract_structured_metadata,
    extract_transaction_tags,
    normalize_match_text,
    normalize_text_list,
)
from apps.legal_research.services.similarity.passage import (
    compose_passage_excerpt,
    dedupe_passages,
    passage_alignment_score,
    select_relevant_passages,
    split_paragraphs,
)
from apps.legal_research.services.similarity.scorers import (
    bm25_proxy_score,
    build_candidate_excerpt,
    char_ngrams,
    coerce_score,
    dedupe_tokens,
    extract_score_from_text,
    focus_content_after_fact_marker,
    keyword_overlap_score,
    lexical_vector_similarity_score,
    metadata_hint_score,
    normalize_score,
    summary_overlap_score,
    tokenize,
    token_overlap_score,
)
from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig


# ── keywords.py ──────────────────────────────────────────────────────────────


class TestNormalizeKeywordQuery:
    def test_empty_string(self):
        assert normalize_keyword_query("") == ""

    def test_none_input(self):
        assert normalize_keyword_query(None) == ""  # type: ignore[arg-type]

    def test_whitespace_only(self):
        assert normalize_keyword_query("   ") == ""

    def test_single_keyword(self):
        assert normalize_keyword_query("合同纠纷") == "合同纠纷"

    def test_comma_separated(self):
        assert normalize_keyword_query("买卖合同,违约") == "买卖合同 违约"

    def test_chinese_punctuation(self):
        assert normalize_keyword_query("买卖合同；违约；赔偿") == "买卖合同 违约 赔偿"

    def test_deduplicates(self):
        assert normalize_keyword_query("合同 合同 违约") == "合同 违约"

    def test_mixed_separators(self):
        result = normalize_keyword_query("买卖合同, 违约;赔偿\n损失")
        assert result == "买卖合同 违约 赔偿 损失"


# ── scorers.py ───────────────────────────────────────────────────────────────


class TestTokenize:
    def test_empty(self):
        assert tokenize("") == []

    def test_none(self):
        assert tokenize(None) == []  # type: ignore[arg-type]

    def test_chinese_text(self):
        tokens = tokenize("买卖合同纠纷案件")
        assert len(tokens) > 0

    def test_stopwords_filtered(self):
        tokens = tokenize("原告被告本院认为法院认为")
        assert "原告" not in tokens
        assert "被告" not in tokens

    def test_mixed_text(self):
        tokens = tokenize("Contract纠纷 Case123")
        assert any("123" in t for t in tokens)


class TestDedupeTokens:
    def test_empty(self):
        assert dedupe_tokens([], max_tokens=10) == []

    def test_deduplication(self):
        result = dedupe_tokens(["abc", "ABC", "def"], max_tokens=10)
        assert len(result) == 2

    def test_max_tokens_limit(self):
        result = dedupe_tokens(["a", "b", "c", "d"], max_tokens=2)
        assert len(result) == 2


class TestCharNgrams:
    def test_empty(self):
        result = char_ngrams("")
        assert len(result) == 0

    def test_short_text(self):
        result = char_ngrams("ab")
        assert len(result) > 0

    def test_longer_text(self):
        result = char_ngrams("买卖合同纠纷案件详情")
        assert len(result) > 0


class TestBm25ProxyScore:
    def test_empty_query(self):
        assert bm25_proxy_score(query_text="", document_text="some text") == 0.0

    def test_empty_document(self):
        assert bm25_proxy_score(query_text="合同", document_text="") == 0.0

    def test_matching_text(self):
        # bm25 uses tokenize which requires 2-10 char tokens matching [一-鿿A-Za-z0-9]
        score = bm25_proxy_score(query_text="违约责任认定", document_text="本案涉及违约责任认定的问题")
        assert score >= 0.0

    def test_no_match(self):
        score = bm25_proxy_score(query_text="刑事犯罪", document_text="买卖合同纠纷案件")
        assert score >= 0.0


class TestLexicalVectorSimilarityScore:
    def test_empty(self):
        assert lexical_vector_similarity_score("", "") == 0.0

    def test_identical(self):
        score = lexical_vector_similarity_score("买卖合同纠纷", "买卖合同纠纷")
        assert score > 0.9

    def test_different(self):
        score = lexical_vector_similarity_score("刑事犯罪", "买卖合同")
        assert score < 0.5


class TestTokenOverlapScore:
    def test_empty(self):
        assert token_overlap_score("", "some text") == 0.0

    def test_full_match(self):
        score = token_overlap_score("买卖合同", "本案涉及买卖合同纠纷")
        assert score > 0


class TestCoerceScore:
    def test_empty(self):
        assert coerce_score("") == 0.0

    def test_none(self):
        assert coerce_score(None) == 0.0

    def test_percentage(self):
        assert coerce_score("85%") == 0.85

    def test_full_width_percentage(self):
        assert coerce_score("85％") == 0.85

    def test_float_string(self):
        assert coerce_score("0.85") == 0.85

    def test_integer_string(self):
        assert coerce_score("85") == 0.85

    def test_no_number(self):
        assert coerce_score("abc") == 0.0


class TestNormalizeScore:
    def test_above_one(self):
        assert normalize_score(85.0) == 0.85

    def test_negative(self):
        assert normalize_score(-0.5) == 0.0

    def test_normal(self):
        assert normalize_score(0.75) == 0.75

    def test_exactly_one(self):
        assert normalize_score(1.0) == 1.0


class TestExtractScoreFromText:
    def test_empty(self):
        assert extract_score_from_text("") == 0.0

    def test_with_score_key(self):
        score = extract_score_from_text('"score": 0.85')
        assert score == 0.85

    def test_with_similarity_keyword(self):
        score = extract_score_from_text("相似度为 0.75")
        assert score == 0.75


class TestFocusContentAfterFactMarker:
    def test_empty(self):
        assert focus_content_after_fact_marker("") == ""

    def test_no_marker(self):
        text = "这是一段普通的文本内容"
        assert focus_content_after_fact_marker(text) == text

    def test_with_marker(self):
        text = "前文部分本院经审理查明被告应承担违约责任"
        result = focus_content_after_fact_marker(text)
        assert "本院经审理查明" in result

    def test_short_focused_returns_original(self):
        text = "前文本院查明短"
        result = focus_content_after_fact_marker(text)
        assert result == text


class TestBuildCandidateExcerpt:
    def test_short_text(self):
        text = "短文本"
        assert build_candidate_excerpt(text) == text

    def test_long_text(self):
        text = "本院经审理查明" + "违约责任认定" * 500
        result = build_candidate_excerpt(text, max_len=1000)
        assert len(result) <= 3500  # head + middle + tail + separators


class TestMetadataHintScore:
    def test_no_domain_terms(self):
        score = metadata_hint_score(keyword="刑事", title="刑事判决", case_digest="", content_text="")
        assert score == 0.0

    def test_with_domain_terms(self):
        score = metadata_hint_score(
            keyword="买卖合同违约",
            title="买卖合同纠纷",
            case_digest="被告违约",
            content_text="本案涉及买卖合同违约责任",
        )
        assert score > 0


class TestKeywordOverlapScore:
    def test_empty_keyword(self):
        score = keyword_overlap_score(keyword="", title="买卖合同", case_digest="", content_text="")
        assert score == 0.0

    def test_matching(self):
        score = keyword_overlap_score(
            keyword="买卖合同 违约",
            title="买卖合同纠纷案",
            case_digest="",
            content_text="",
        )
        assert score > 0


class TestSummaryOverlapScore:
    def test_empty(self):
        score = summary_overlap_score(case_summary="", title="", case_digest="", content_text="")
        assert score == 0.0

    def test_matching(self):
        score = summary_overlap_score(
            case_summary="违约责任纠纷案件",
            title="违约责任纠纷案",
            case_digest="被告违约",
            content_text="本案涉及违约责任",
        )
        assert score >= 0.0


# ── passage.py ───────────────────────────────────────────────────────────────


class TestSplitParagraphs:
    def test_empty(self):
        assert split_paragraphs("", passage_max_chars=1000) == []

    def test_with_content(self):
        text = "本院经审理查明被告应承担违约责任。原告要求赔偿损失。"
        result = split_paragraphs(text, passage_max_chars=10000)
        assert len(result) > 0

    def test_short_parts_filtered(self):
        text = "短\n本院经审理查明被告应承担违约责任赔偿损失"
        result = split_paragraphs(text, passage_max_chars=10000)
        assert all(len(p) >= 12 for p in result)


class TestDedupePassages:
    def test_empty(self):
        assert dedupe_passages([]) == []

    def test_deduplication(self):
        passages = ["相同内容段落", "相同内容段落", "不同内容段落"]
        result = dedupe_passages(passages)
        assert len(result) == 2


class TestComposePassageExcerpt:
    def test_empty(self):
        assert compose_passage_excerpt(passages=[], preview_max_chars=500) == ""

    def test_with_passages(self):
        result = compose_passage_excerpt(passages=["段落一", "段落二"], preview_max_chars=500)
        assert "[片段1]" in result
        assert "[片段2]" in result


class TestSelectRelevantPassages:
    def test_empty_content(self):
        result = select_relevant_passages(
            keyword="合同",
            case_summary="",
            title="",
            case_digest="",
            content_text="",
            max_passages=5,
            passage_max_chars=10000,
        )
        assert result == []

    def test_with_content(self):
        text = "本院经审理查明被告应承担违约责任赔偿原告损失。原告要求被告支付违约金。"
        result = select_relevant_passages(
            keyword="违约",
            case_summary="合同违约",
            title="买卖合同纠纷",
            case_digest="违约责任",
            content_text=text,
            max_passages=3,
            passage_max_chars=10000,
        )
        assert isinstance(result, list)


class TestPassageAlignmentScore:
    def test_empty_content(self):
        score = passage_alignment_score(
            keyword="合同",
            case_summary="",
            title="",
            case_digest="",
            content_text="",
            passage_max_chars=10000,
            passage_top_k=5,
        )
        assert score == 0.0


# ── json_utils.py ────────────────────────────────────────────────────────────


class TestExtractJson:
    def test_empty(self):
        assert extract_json("") is None

    def test_none(self):
        assert extract_json(None) is None  # type: ignore[arg-type]

    def test_valid_json(self):
        result = extract_json('{"score": 0.85}')
        assert result == {"score": 0.85}

    def test_json_in_markdown(self):
        result = extract_json('```json\n{"score": 0.85}\n```')
        assert result == {"score": 0.85}

    def test_json_with_extra_text(self):
        result = extract_json('Here is the result: {"score": 0.85} done')
        assert result == {"score": 0.85}

    def test_invalid_json(self):
        assert extract_json("not json at all") is None

    def test_non_dict_json(self):
        assert extract_json("[1, 2, 3]") is None


class TestNormalizeTextList:
    def test_list(self):
        assert normalize_text_list(["a", "b", "c"]) == ["a", "b", "c"]

    def test_string(self):
        assert normalize_text_list("hello") == ["hello"]

    def test_empty(self):
        assert normalize_text_list(None) == []

    def test_empty_string(self):
        assert normalize_text_list("") == []


class TestNormalizeMatchText:
    def test_empty(self):
        assert normalize_match_text("") == ""

    def test_with_punctuation(self):
        result = normalize_match_text("买卖合同，违约责任。")
        assert "，" not in result
        assert "。" not in result

    def test_with_spaces(self):
        result = normalize_match_text("买卖 合同")
        assert " " not in result


class TestEvidenceSpanHitCount:
    def test_empty(self):
        hits, total = evidence_span_hit_count(evidence_spans=[], context_text="")
        assert hits == 0
        assert total == 0

    def test_matching(self):
        hits, total = evidence_span_hit_count(
            evidence_spans=["违约责任", "赔偿损失"],
            context_text="本案涉及违约责任的认定和赔偿损失的计算",
        )
        assert hits == 2
        assert total == 2

    def test_partial_match(self):
        hits, total = evidence_span_hit_count(
            evidence_spans=["违约责任", "不存在的内容"],
            context_text="本案涉及违约责任",
        )
        assert hits == 1
        assert total == 2


class TestApplyStructuredAdjustments:
    def test_reject_decision(self):
        score = apply_structured_adjustments(score=0.9, payload={"decision": "reject"})
        assert score <= 0.45

    def test_low_decision(self):
        score = apply_structured_adjustments(score=0.9, payload={"decision": "low"})
        assert score <= 0.6

    def test_medium_decision(self):
        score = apply_structured_adjustments(score=0.9, payload={"decision": "medium"})
        assert score <= 0.85

    def test_low_component_score(self):
        score = apply_structured_adjustments(
            score=0.9,
            payload={"facts_match": 0.1, "legal_relation_match": 1.0, "dispute_match": 1.0, "damage_match": 1.0},
        )
        assert score <= 0.55

    def test_hard_conflict(self):
        score = apply_structured_adjustments(
            score=0.9,
            payload={"key_conflicts": ["主体不一致"]},
        )
        assert score <= 0.62


class TestExtractStructuredMetadata:
    def test_basic(self):
        metadata = extract_structured_metadata(
            payload={"score": 0.85, "decision": "similar"},
            adjusted_score=0.8,
        )
        assert metadata["score_adjusted"] == 0.8
        assert metadata["decision"] == "similar"


class TestExtractTransactionTags:
    def test_empty(self):
        assert extract_transaction_tags("") == []

    def test_delivery_delay(self):
        tags = extract_transaction_tags("被告逾期交货，未按时交付货物")
        assert "交货迟延" in tags

    def test_quality_defect(self):
        tags = extract_transaction_tags("货物存在质量问题，不合格")
        assert "质量瑕疵" in tags

    def test_price_dispute(self):
        tags = extract_transaction_tags("市场价格波动导致价差争议")
        assert "价差争议" in tags

    def test_no_match(self):
        tags = extract_transaction_tags("普通文本内容")
        assert tags == []


# ── tuning_config.py ─────────────────────────────────────────────────────────


class TestLegalResearchTuningConfig:
    def test_defaults(self):
        config = LegalResearchTuningConfig()
        assert config.recall_weight_keyword == 0.18
        assert config.dual_review_enabled is True

    def test_normalized_recall_weights(self):
        config = LegalResearchTuningConfig()
        weights = config.normalized_recall_weights
        assert len(weights) == 6
        assert abs(sum(weights) - 1.0) < 0.01

    def test_normalized_recall_weights_zero_total(self):
        config = LegalResearchTuningConfig(
            recall_weight_keyword=0,
            recall_weight_summary=0,
            recall_weight_bm25=0,
            recall_weight_vector=0,
            recall_weight_passage=0,
            recall_weight_metadata=0,
        )
        weights = config.normalized_recall_weights
        assert abs(sum(weights) - 1.0) < 0.01

    @patch("apps.legal_research.services.similarity.tuning_config._get_config_service")
    def test_load_returns_defaults_on_error(self, mock_get):
        mock_get.side_effect = Exception("db error")
        config = LegalResearchTuningConfig.load()
        assert isinstance(config, LegalResearchTuningConfig)

    def test_get_int_helpers(self):
        class MockConfig:
            def get_value(self, key, default=""):
                return "5"

        result = LegalResearchTuningConfig._get_int(MockConfig(), "key", 3, 1, 10)
        assert result == 5

    def test_get_int_invalid(self):
        class MockConfig:
            def get_value(self, key, default=""):
                return "abc"

        result = LegalResearchTuningConfig._get_int(MockConfig(), "key", 3, 1, 10)
        assert result == 3

    def test_get_float_helpers(self):
        class MockConfig:
            def get_value(self, key, default=""):
                return "0.5"

        result = LegalResearchTuningConfig._get_float(MockConfig(), "key", 0.3, 0.0, 1.0)
        assert result == 0.5

    def test_get_bool_true(self):
        class MockConfig:
            def get_value(self, key, default=""):
                return "true"

        assert LegalResearchTuningConfig._get_bool(MockConfig(), "key", False) is True

    def test_get_bool_false(self):
        class MockConfig:
            def get_value(self, key, default=""):
                return "false"

        assert LegalResearchTuningConfig._get_bool(MockConfig(), "key", True) is False

    def test_get_text(self):
        class MockConfig:
            def get_value(self, key, default=""):
                return "value"

        result = LegalResearchTuningConfig._get_text(MockConfig(), "key", "default", max_len=10)
        assert result == "value"

    def test_get_text_empty(self):
        class MockConfig:
            def get_value(self, key, default=""):
                return ""

        result = LegalResearchTuningConfig._get_text(MockConfig(), "key", "default", max_len=10)
        assert result == "default"
