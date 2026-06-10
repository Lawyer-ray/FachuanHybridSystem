"""legal_research 模块真实执行测试 - 覆盖 keywords, scorers, passage, tuning_config, similarity 等。"""
from __future__ import annotations

import pytest


# ============================================================
# legal_research/services/keywords.py
# ============================================================


class TestNormalizeKeywordQuery:
    def test_empty(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        assert normalize_keyword_query("") == ""
        assert normalize_keyword_query("   ") == ""

    def test_none(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        assert normalize_keyword_query(None) == ""

    def test_single_keyword(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        assert normalize_keyword_query("买卖合同") == "买卖合同"

    def test_multiple_comma_separated(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("买卖合同,违约责任")
        assert "买卖合同" in result
        assert "违约责任" in result

    def test_chinese_comma(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("买卖合同，违约责任")
        assert "买卖合同" in result
        assert "违约责任" in result

    def test_semicolon_separated(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("买卖合同;违约责任")
        assert "买卖合同" in result

    def test_space_separated(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("买卖合同 违约责任")
        assert "买卖合同" in result
        assert "违约责任" in result

    def test_deduplication(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("买卖合同,买卖合同,违约")
        parts = result.split()
        assert len(parts) == 2

    def test_newline_separated(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("买卖合同\n违约责任")
        assert "买卖合同" in result
        assert "违约责任" in result


# ============================================================
# legal_research/services/similarity/scorers.py
# ============================================================


class TestTokenize:
    def test_tokenize_chinese(self) -> None:
        from apps.legal_research.services.similarity.scorers import tokenize

        tokens = tokenize("买卖合同纠纷一案")
        assert len(tokens) > 0
        assert all(isinstance(t, str) for t in tokens)

    def test_tokenize_empty(self) -> None:
        from apps.legal_research.services.similarity.scorers import tokenize

        assert tokenize("") == []
        assert tokenize(None) == []

    def test_tokenize_removes_stopwords(self) -> None:
        from apps.legal_research.services.similarity.scorers import tokenize

        tokens = tokenize("原告和被告以及或者如果因此")
        # Most should be filtered as stopwords
        assert len(tokens) == 0 or all(t not in {"以及", "或者", "如果", "因此", "原告", "被告"} for t in tokens)


class TestDedupeTokens:
    def test_dedupe_basic(self) -> None:
        from apps.legal_research.services.similarity.scorers import dedupe_tokens

        result = dedupe_tokens(["a", "b", "a", "c"], max_tokens=10)
        assert result == ["a", "b", "c"]

    def test_dedupe_max_limit(self) -> None:
        from apps.legal_research.services.similarity.scorers import dedupe_tokens

        result = dedupe_tokens(["a", "b", "c", "d"], max_tokens=2)
        assert len(result) == 2

    def test_dedupe_case_insensitive(self) -> None:
        from apps.legal_research.services.similarity.scorers import dedupe_tokens

        result = dedupe_tokens(["Abc", "abc", "ABC"], max_tokens=10)
        assert len(result) == 1


class TestCharNgrams:
    def test_basic(self) -> None:
        from apps.legal_research.services.similarity.scorers import char_ngrams

        result = char_ngrams("买卖合同纠纷")
        assert len(result) > 0

    def test_empty(self) -> None:
        from apps.legal_research.services.similarity.scorers import char_ngrams

        result = char_ngrams("")
        assert len(result) == 0

    def test_short_text(self) -> None:
        from apps.legal_research.services.similarity.scorers import char_ngrams

        result = char_ngrams("a")
        assert len(result) == 0


class TestBM25ProxyScore:
    def test_score_range(self) -> None:
        from apps.legal_research.services.similarity.scorers import bm25_proxy_score

        score = bm25_proxy_score(
            query_text="买卖合同",
            document_text="本案系买卖合同纠纷一案，原告主张被告违约",
        )
        assert 0.0 <= score <= 1.0

    def test_no_match(self) -> None:
        from apps.legal_research.services.similarity.scorers import bm25_proxy_score

        score = bm25_proxy_score(
            query_text="知识产权侵权",
            document_text="本案系买卖合同纠纷一案",
        )
        assert 0.0 <= score <= 1.0

    def test_empty_query(self) -> None:
        from apps.legal_research.services.similarity.scorers import bm25_proxy_score

        score = bm25_proxy_score(query_text="", document_text="some text")
        assert score == 0.0

    def test_empty_document(self) -> None:
        from apps.legal_research.services.similarity.scorers import bm25_proxy_score

        score = bm25_proxy_score(query_text="test", document_text="")
        assert score == 0.0


class TestLexicalVectorSimilarity:
    def test_identical_texts(self) -> None:
        from apps.legal_research.services.similarity.scorers import lexical_vector_similarity_score

        score = lexical_vector_similarity_score("买卖合同纠纷案", "买卖合同纠纷案")
        assert score > 0.9

    def test_different_texts(self) -> None:
        from apps.legal_research.services.similarity.scorers import lexical_vector_similarity_score

        score = lexical_vector_similarity_score("买卖合同", "知识产权侵权")
        assert 0.0 <= score <= 1.0

    def test_empty_texts(self) -> None:
        from apps.legal_research.services.similarity.scorers import lexical_vector_similarity_score

        assert lexical_vector_similarity_score("", "") == 0.0


class TestTokenOverlapScore:
    def test_full_overlap(self) -> None:
        from apps.legal_research.services.similarity.scorers import token_overlap_score

        score = token_overlap_score("买卖合同", "本案系买卖合同纠纷")
        assert score > 0

    def test_no_overlap(self) -> None:
        from apps.legal_research.services.similarity.scorers import token_overlap_score

        score = token_overlap_score("知识产权", "本案系买卖合同纠纷")
        assert 0.0 <= score <= 1.0

    def test_empty_query(self) -> None:
        from apps.legal_research.services.similarity.scorers import token_overlap_score

        assert token_overlap_score("", "text") == 0.0


class TestCoerceScore:
    def test_percentage_string(self) -> None:
        from apps.legal_research.services.similarity.scorers import coerce_score

        assert coerce_score("85%") == 0.85

    def test_fullwidth_percentage(self) -> None:
        from apps.legal_research.services.similarity.scorers import coerce_score

        assert coerce_score("85％") == 0.85

    def test_numeric_string(self) -> None:
        from apps.legal_research.services.similarity.scorers import coerce_score

        assert coerce_score("0.85") == 0.85

    def test_empty(self) -> None:
        from apps.legal_research.services.similarity.scorers import coerce_score

        assert coerce_score("") == 0.0
        assert coerce_score(None) == 0.0

    def test_non_numeric(self) -> None:
        from apps.legal_research.services.similarity.scorers import coerce_score

        assert coerce_score("abc") == 0.0


class TestNormalizeScore:
    def test_score_in_range(self) -> None:
        from apps.legal_research.services.similarity.scorers import normalize_score

        assert normalize_score(0.5) == 0.5
        assert normalize_score(1.0) == 1.0

    def test_score_above_one_below_hundred(self) -> None:
        from apps.legal_research.services.similarity.scorers import normalize_score

        assert normalize_score(85) == 0.85

    def test_score_negative(self) -> None:
        from apps.legal_research.services.similarity.scorers import normalize_score

        assert normalize_score(-0.5) == 0.0


class TestExtractScoreFromText:
    def test_json_score(self) -> None:
        from apps.legal_research.services.similarity.scorers import extract_score_from_text

        score = extract_score_from_text('"score": 0.85')
        assert score > 0

    def test_similarity_text(self) -> None:
        from apps.legal_research.services.similarity.scorers import extract_score_from_text

        score = extract_score_from_text("相似度为 0.85")
        assert score > 0

    def test_empty_text(self) -> None:
        from apps.legal_research.services.similarity.scorers import extract_score_from_text

        assert extract_score_from_text("") == 0.0


class TestBuildCandidateExcerpt:
    def test_short_text(self) -> None:
        from apps.legal_research.services.similarity.scorers import build_candidate_excerpt

        text = "本案经审理查明，原告主张的事实成立。"
        result = build_candidate_excerpt(text, max_len=3200)
        assert len(result) <= len(text) + 10

    def test_long_text(self) -> None:
        from apps.legal_research.services.similarity.scorers import build_candidate_excerpt

        text = "本院经审理查明" + "x" * 10000
        result = build_candidate_excerpt(text, max_len=3200)
        assert len(result) <= 3300


class TestFocusContentAfterFactMarker:
    def test_with_marker(self) -> None:
        from apps.legal_research.services.similarity.scorers import focus_content_after_fact_marker

        text = "判决书全文\n本院经审理查明：原告与被告签订合同。" + "x" * 100
        result = focus_content_after_fact_marker(text)
        assert "本院" in result

    def test_without_marker(self) -> None:
        from apps.legal_research.services.similarity.scorers import focus_content_after_fact_marker

        text = "普通文本没有标记"
        result = focus_content_after_fact_marker(text)
        assert result == text

    def test_empty_text(self) -> None:
        from apps.legal_research.services.similarity.scorers import focus_content_after_fact_marker

        assert focus_content_after_fact_marker("") == ""
        assert focus_content_after_fact_marker(None) == ""


class TestMetadataHintScore:
    def test_with_relevant_terms(self) -> None:
        from apps.legal_research.services.similarity.scorers import metadata_hint_score

        score = metadata_hint_score(
            keyword="买卖合同违约",
            title="买卖合同纠纷一案",
            case_digest="原告主张被告违约",
            content_text="本案系买卖合同纠纷，被告应承担违约责任",
        )
        assert score > 0

    def test_no_relevant_terms(self) -> None:
        from apps.legal_research.services.similarity.scorers import metadata_hint_score

        score = metadata_hint_score(
            keyword="test",
            title="test",
            case_digest="test",
            content_text="",
        )
        assert score == 0.0


# ============================================================
# legal_research/services/similarity/passage.py
# ============================================================


class TestPassage:
    def test_split_paragraphs_basic(self) -> None:
        from apps.legal_research.services.similarity.passage import split_paragraphs

        text = "本院经审理查明：原告与被告签订合同。\n被告未按时付款。\n原告提起诉讼。"
        result = split_paragraphs(text, passage_max_chars=5000)
        assert isinstance(result, list)

    def test_split_paragraphs_empty(self) -> None:
        from apps.legal_research.services.similarity.passage import split_paragraphs

        assert split_paragraphs("", passage_max_chars=5000) == []

    def test_dedupe_passages(self) -> None:
        from apps.legal_research.services.similarity.passage import dedupe_passages

        passages = ["paragraph one text", "paragraph one text", "paragraph two text"]
        result = dedupe_passages(passages)
        assert len(result) == 2

    def test_compose_passage_excerpt(self) -> None:
        from apps.legal_research.services.similarity.passage import compose_passage_excerpt

        result = compose_passage_excerpt(passages=["p1", "p2"], preview_max_chars=100)
        assert "[片段1]" in result
        assert "[片段2]" in result

    def test_compose_passage_excerpt_empty(self) -> None:
        from apps.legal_research.services.similarity.passage import compose_passage_excerpt

        assert compose_passage_excerpt(passages=[], preview_max_chars=100) == ""


# ============================================================
# legal_research/services/similarity/tuning_config.py
# ============================================================


class TestTuningConfig:
    def test_default_values(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        cfg = LegalResearchTuningConfig()
        assert cfg.recall_weight_keyword == 0.18
        assert cfg.passage_top_k == 5
        assert cfg.dual_review_enabled is True

    def test_normalized_recall_weights(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        cfg = LegalResearchTuningConfig()
        weights = cfg.normalized_recall_weights
        assert len(weights) == 6
        assert abs(sum(weights) - 1.0) < 0.01

    def test_normalized_recall_weights_zero_total(self) -> None:
        from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

        cfg = LegalResearchTuningConfig(
            recall_weight_keyword=0,
            recall_weight_summary=0,
            recall_weight_bm25=0,
            recall_weight_vector=0,
            recall_weight_passage=0,
            recall_weight_metadata=0,
        )
        weights = cfg.normalized_recall_weights
        assert abs(sum(weights) - 1.0) < 0.01
