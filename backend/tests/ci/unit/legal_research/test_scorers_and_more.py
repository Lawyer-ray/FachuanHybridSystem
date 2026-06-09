"""Tests for legal_research scorers, case_download_service, and signals."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── scorers ────────────────────────────────────────────────────────────────


class TestScorers:
    def test_tokenize_basic(self) -> None:
        from apps.legal_research.services.similarity.scorers import tokenize

        tokens = tokenize("合同纠纷违约责任")
        assert len(tokens) > 0

    def test_tokenize_empty(self) -> None:
        from apps.legal_research.services.similarity.scorers import tokenize

        assert tokenize("") == []
        assert tokenize(None) == []  # type: ignore[arg-type]

    def test_tokenize_removes_stopwords(self) -> None:
        from apps.legal_research.services.similarity.scorers import tokenize

        tokens = tokenize("原告被告本院认为应当")
        # all tokens are stopword-filtered (length >=2 check applies first)
        for t in tokens:
            assert t not in {"原告", "被告", "本院认为"}

    def test_tokenize_mixed_language(self) -> None:
        from apps.legal_research.services.similarity.scorers import tokenize

        tokens = tokenize("contract纠纷Case2024")
        assert len(tokens) > 0

    def test_dedupe_tokens(self) -> None:
        from apps.legal_research.services.similarity.scorers import dedupe_tokens

        result = dedupe_tokens(["abc", "ABC", "def"], max_tokens=10)
        assert len(result) == 2  # "abc" and "ABC" deduped to "abc"

    def test_dedupe_tokens_max(self) -> None:
        from apps.legal_research.services.similarity.scorers import dedupe_tokens

        result = dedupe_tokens(["a", "b", "c", "d"], max_tokens=2)
        assert len(result) == 2

    def test_dedupe_tokens_empty(self) -> None:
        from apps.legal_research.services.similarity.scorers import dedupe_tokens

        result = dedupe_tokens(["", "  ", "abc"], max_tokens=10)
        assert result == ["abc"]

    def test_char_ngrams_basic(self) -> None:
        from apps.legal_research.services.similarity.scorers import char_ngrams

        grams = char_ngrams("hello world")
        assert len(grams) > 0
        # Should have bigrams and trigrams
        assert "he" in grams or "el" in grams

    def test_char_ngrams_empty(self) -> None:
        from apps.legal_research.services.similarity.scorers import char_ngrams

        assert len(char_ngrams("")) == 0
        assert len(char_ngrams("a")) == 0  # too short for ngrams

    def test_char_ngrams_truncates(self) -> None:
        from apps.legal_research.services.similarity.scorers import char_ngrams

        grams = char_ngrams("x" * 5000)
        # Should not crash, truncated at 2000
        assert len(grams) > 0

    def test_bm25_proxy_score_basic(self) -> None:
        from apps.legal_research.services.similarity.scorers import bm25_proxy_score

        score = bm25_proxy_score(
            query_text="合同纠纷",
            document_text="本案系合同纠纷案件被告应承担违约责任。",
        )
        assert score >= 0.0
        assert score <= 1.0

    def test_bm25_proxy_score_no_overlap(self) -> None:
        from apps.legal_research.services.similarity.scorers import bm25_proxy_score

        score = bm25_proxy_score(
            query_text="完全不同的内容",
            document_text="unrelated english text only",
        )
        assert score >= 0.0

    def test_bm25_proxy_score_empty_query(self) -> None:
        from apps.legal_research.services.similarity.scorers import bm25_proxy_score

        assert bm25_proxy_score(query_text="", document_text="test") == 0.0

    def test_bm25_proxy_score_empty_doc(self) -> None:
        from apps.legal_research.services.similarity.scorers import bm25_proxy_score

        assert bm25_proxy_score(query_text="test", document_text="") == 0.0

    def test_lexical_vector_similarity_score(self) -> None:
        from apps.legal_research.services.similarity.scorers import lexical_vector_similarity_score

        score = lexical_vector_similarity_score("hello world", "hello world")
        assert score > 0.9  # identical

    def test_lexical_vector_similarity_score_no_overlap(self) -> None:
        from apps.legal_research.services.similarity.scorers import lexical_vector_similarity_score

        score = lexical_vector_similarity_score("abc", "xyz")
        assert score >= 0.0

    def test_lexical_vector_similarity_score_empty(self) -> None:
        from apps.legal_research.services.similarity.scorers import lexical_vector_similarity_score

        assert lexical_vector_similarity_score("", "test") == 0.0
        assert lexical_vector_similarity_score("test", "") == 0.0

    def test_token_overlap_score(self) -> None:
        from apps.legal_research.services.similarity.scorers import token_overlap_score

        score = token_overlap_score("合同 违约", "本案合同违约")
        assert score > 0

    def test_token_overlap_score_empty(self) -> None:
        from apps.legal_research.services.similarity.scorers import token_overlap_score

        assert token_overlap_score("", "test") == 0.0

    def test_metadata_hint_score_basic(self) -> None:
        from apps.legal_research.services.similarity.scorers import metadata_hint_score

        score = metadata_hint_score(
            keyword="买卖合同 违约",
            title="买卖合同纠纷",
            case_digest="被告违约应赔偿",
            content_text="损失赔偿",
        )
        assert score > 0

    def test_metadata_hint_score_no_match(self) -> None:
        from apps.legal_research.services.similarity.scorers import metadata_hint_score

        score = metadata_hint_score(
            keyword="other",
            title="other",
            case_digest="other",
            content_text="other",
        )
        assert score == 0.0

    def test_keyword_overlap_score_basic(self) -> None:
        from apps.legal_research.services.similarity.scorers import keyword_overlap_score

        score = keyword_overlap_score(
            keyword="合同 违约",
            title="买卖合同纠纷违约案",
            case_digest="",
            content_text="",
        )
        assert score > 0

    def test_keyword_overlap_score_empty(self) -> None:
        from apps.legal_research.services.similarity.scorers import keyword_overlap_score

        assert keyword_overlap_score(keyword="", title="", case_digest="", content_text="") == 0.0

    def test_keyword_overlap_score_short_tokens(self) -> None:
        from apps.legal_research.services.similarity.scorers import keyword_overlap_score

        # Single-char tokens are filtered out
        assert keyword_overlap_score(keyword="a b c", title="a b c", case_digest="", content_text="") == 0.0

    def test_summary_overlap_score_basic(self) -> None:
        from apps.legal_research.services.similarity.scorers import summary_overlap_score

        score = summary_overlap_score(
            case_summary="合同违约赔偿",
            title="合同违约案件",
            case_digest="",
            content_text="",
        )
        assert score >= 0.0

    def test_summary_overlap_score_empty(self) -> None:
        from apps.legal_research.services.similarity.scorers import summary_overlap_score

        assert summary_overlap_score(case_summary="", title="", case_digest="", content_text="") == 0.0

    def test_summary_overlap_score_stopwords_only(self) -> None:
        from apps.legal_research.services.similarity.scorers import summary_overlap_score

        # "以及或者如果" are all stopwords, and also < 2 chars won't match regex for 2+ chars
        score = summary_overlap_score(
            case_summary="以及或者如果",
            title="以及或者如果",
            case_digest="",
            content_text="",
        )
        # After filtering stopwords and digit-only tokens, may be 0
        assert score >= 0.0

    def test_coerce_score_basic(self) -> None:
        from apps.legal_research.services.similarity.scorers import coerce_score

        assert coerce_score("0.8") == 0.8
        assert coerce_score("80%") == 0.8
        assert coerce_score("80％") == 0.8
        assert coerce_score("") == 0.0
        assert coerce_score(None) == 0.0  # type: ignore[arg-type]
        assert coerce_score("abc") == 0.0

    def test_coerce_score_over_100(self) -> None:
        from apps.legal_research.services.similarity.scorers import coerce_score

        assert coerce_score("150") == 1.0  # normalized via normalize_score

    def test_coerce_score_negative(self) -> None:
        from apps.legal_research.services.similarity.scorers import coerce_score

        # "-5" extracts "5" via regex, normalizes to 5/100=0.05
        result = coerce_score("-5")
        assert result >= 0.0

    def test_normalize_score(self) -> None:
        from apps.legal_research.services.similarity.scorers import normalize_score

        assert normalize_score(80) == 0.8  # > 1, <= 100 -> / 100
        assert normalize_score(-1) == 0.0
        assert normalize_score(0.5) == 0.5
        # 1.5 > 1.0 and <= 100 -> 1.5/100 = 0.015
        assert normalize_score(1.5) == pytest.approx(0.015)
        assert normalize_score(200) == 1.0  # > 100 -> min(1.0, 200)

    def test_extract_score_from_text(self) -> None:
        from apps.legal_research.services.similarity.scorers import extract_score_from_text

        assert extract_score_from_text('"score": 0.85') > 0
        assert extract_score_from_text("相似度85%") > 0
        assert extract_score_from_text("") == 0.0

    def test_extract_score_from_text_no_score(self) -> None:
        from apps.legal_research.services.similarity.scorers import extract_score_from_text

        assert extract_score_from_text("no score here") == 0.0

    def test_build_candidate_excerpt_short(self) -> None:
        from apps.legal_research.services.similarity.scorers import build_candidate_excerpt

        text = "本案经审理查明，被告应赔偿原告损失。"
        result = build_candidate_excerpt(text, max_len=5000)
        assert len(result) <= 5000

    def test_build_candidate_excerpt_long(self) -> None:
        from apps.legal_research.services.similarity.scorers import build_candidate_excerpt

        text = "本院经审理查明" + "x" * 5000
        result = build_candidate_excerpt(text, max_len=3200)
        assert len(result) <= 3200 + 100  # some margin for separators
        assert "..." in result

    def test_focus_content_after_fact_marker_found(self) -> None:
        from apps.legal_research.services.similarity.scorers import focus_content_after_fact_marker

        text = "首部内容。本院经审理查明被告应赔偿原告损失共计人民币十万元。"
        result = focus_content_after_fact_marker(text)
        assert result.startswith("本院")

    def test_focus_content_after_fact_marker_not_found(self) -> None:
        from apps.legal_research.services.similarity.scorers import focus_content_after_fact_marker

        text = "没有查明标记的普通文本"
        result = focus_content_after_fact_marker(text)
        assert result == text

    def test_focus_content_after_fact_marker_empty(self) -> None:
        from apps.legal_research.services.similarity.scorers import focus_content_after_fact_marker

        assert focus_content_after_fact_marker("") == ""
        assert focus_content_after_fact_marker(None) == ""  # type: ignore[arg-type]

    def test_heuristic_idf_weight(self) -> None:
        from apps.legal_research.services.similarity.scorers import _heuristic_idf_weight

        assert _heuristic_idf_weight("ab") == 0.4
        assert _heuristic_idf_weight("abc") == 0.7
        assert _heuristic_idf_weight("abcd") == 1.0
        assert _heuristic_idf_weight("abcde") == 1.0


# ── case_download_service ──────────────────────────────────────────────────


class TestCaseDownloadService:
    def test_parse_case_numbers_empty(self) -> None:
        from apps.legal_research.services.task.case_download_service import CaseDownloadService

        assert CaseDownloadService.parse_case_numbers("") == []
        assert CaseDownloadService.parse_case_numbers(None) == []  # type: ignore[arg-type]

    def test_parse_case_numbers_newline(self) -> None:
        from apps.legal_research.services.task.case_download_service import CaseDownloadService

        result = CaseDownloadService.parse_case_numbers("2024-001\n2024-002\n2024-003")
        assert len(result) == 3

    def test_parse_case_numbers_comma(self) -> None:
        from apps.legal_research.services.task.case_download_service import CaseDownloadService

        result = CaseDownloadService.parse_case_numbers("2024-001,2024-002,2024-003")
        assert len(result) == 3

    def test_parse_case_numbers_chinese_comma(self) -> None:
        from apps.legal_research.services.task.case_download_service import CaseDownloadService

        result = CaseDownloadService.parse_case_numbers("2024-001，2024-002")
        assert len(result) == 2

    def test_parse_case_numbers_semicolons(self) -> None:
        from apps.legal_research.services.task.case_download_service import CaseDownloadService

        result = CaseDownloadService.parse_case_numbers("2024-001;2024-002")
        assert len(result) == 2

    def test_parse_case_numbers_mixed(self) -> None:
        from apps.legal_research.services.task.case_download_service import CaseDownloadService

        result = CaseDownloadService.parse_case_numbers("2024-001\n2024-002, 2024-003；2024-004")
        assert len(result) == 4

    def test_parse_case_numbers_whitespace(self) -> None:
        from apps.legal_research.services.task.case_download_service import CaseDownloadService

        result = CaseDownloadService.parse_case_numbers("  2024-001  ,  2024-002  ")
        assert result == ["2024-001", "2024-002"]


# ── signals ────────────────────────────────────────────────────────────────


class TestSignals:
    def test_signal_handler_with_pdf(self) -> None:
        from apps.legal_research.signals import _cleanup_legal_research_pdf

        instance = MagicMock()
        instance.pdf_file = MagicMock()
        instance.pk = 1

        _cleanup_legal_research_pdf(sender=None, instance=instance)
        instance.pdf_file.delete.assert_called_once_with(save=False)

    def test_signal_handler_no_pdf(self) -> None:
        from apps.legal_research.signals import _cleanup_legal_research_pdf

        instance = MagicMock()
        instance.pdf_file = None
        instance.pk = 1

        # Should not raise
        _cleanup_legal_research_pdf(sender=None, instance=instance)

    def test_signal_handler_delete_fails(self) -> None:
        from apps.legal_research.signals import _cleanup_legal_research_pdf

        instance = MagicMock()
        instance.pdf_file = MagicMock()
        instance.pdf_file.delete.side_effect = OSError("permission denied")
        instance.pk = 1

        # Should not raise (catches exception)
        _cleanup_legal_research_pdf(sender=None, instance=instance)
