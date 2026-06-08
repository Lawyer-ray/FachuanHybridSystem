"""相似度评分函数单元测试。"""
from __future__ import annotations

import pytest

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
    token_overlap_score,
    tokenize,
)


# ── tokenize ───────────────────────────────────────────────────────────────

def test_tokenize_basic() -> None:
    """基本中文分词。"""
    tokens = tokenize("买卖合同纠纷")
    assert len(tokens) > 0


def test_tokenize_removes_stopwords() -> None:
    """停用词被过滤。"""
    tokens = tokenize("因此法院认为原告应当赔偿")
    assert "因此" not in tokens
    assert "法院认为" not in tokens
    assert "原告" not in tokens


def test_tokenize_empty() -> None:
    """空字符串返回空列表。"""
    assert tokenize("") == []


def test_tokenize_english() -> None:
    """英文分词。"""
    tokens = tokenize("hello world test")
    assert "hello" in tokens


# ── dedupe_tokens ──────────────────────────────────────────────────────────

def test_dedupe_removes_duplicates() -> None:
    """去重。"""
    result = dedupe_tokens(["a", "b", "a", "c"], max_tokens=10)
    assert result == ["a", "b", "c"]


def test_dedupe_respects_max_tokens() -> None:
    """限制最大 token 数。"""
    result = dedupe_tokens(["a", "b", "c", "d"], max_tokens=2)
    assert len(result) == 2


def test_dedupe_case_insensitive() -> None:
    """大小写不敏感去重。"""
    result = dedupe_tokens(["ABC", "abc"], max_tokens=10)
    assert len(result) == 1


def test_dedupe_empty() -> None:
    """空列表返回空。"""
    assert dedupe_tokens([], max_tokens=10) == []


# ── char_ngrams ────────────────────────────────────────────────────────────

def test_char_ngrams_basic() -> None:
    """基本字符 n-gram 生成。"""
    counter = char_ngrams("买卖合同")
    assert len(counter) > 0
    assert counter["买卖"] >= 1


def test_char_ngrams_short_text() -> None:
    """太短的文本返回空。"""
    assert len(char_ngrams("a")) == 0


def test_char_ngrams_empty() -> None:
    """空字符串返回空。"""
    assert len(char_ngrams("")) == 0


# ── bm25_proxy_score ───────────────────────────────────────────────────────

def test_bm25_basic_match() -> None:
    """基本匹配得分 > 0。"""
    score = bm25_proxy_score(query_text="买卖 合同 纠纷", document_text="买卖 合同 纠纷 案件 赔偿")
    assert score > 0


def test_bm25_no_match() -> None:
    """无匹配得分 = 0。"""
    score = bm25_proxy_score(query_text="专利侵权", document_text="本案系买卖合同纠纷案件")
    assert score == 0.0


def test_bm25_empty_query() -> None:
    """空查询返回 0。"""
    assert bm25_proxy_score(query_text="", document_text="some text") == 0.0


def test_bm25_empty_document() -> None:
    """空文档返回 0。"""
    assert bm25_proxy_score(query_text="some text", document_text="") == 0.0


def test_bm25_clamp_range() -> None:
    """得分在 [0, 1] 范围内。"""
    score = bm25_proxy_score(query_text="合同 违约 赔偿", document_text="合同违约应当赔偿损失")
    assert 0.0 <= score <= 1.0


# ── lexical_vector_similarity_score ────────────────────────────────────────

def test_lexical_sim_identical() -> None:
    """相同文本相似度 = 1。"""
    score = lexical_vector_similarity_score("买卖合同纠纷", "买卖合同纠纷")
    assert score == pytest.approx(1.0)


def test_lexical_sim_different() -> None:
    """完全不同文本相似度低。"""
    score = lexical_vector_similarity_score("买卖合同", "专利侵权")
    assert score < 0.5


def test_lexical_sim_empty() -> None:
    """空文本返回 0。"""
    assert lexical_vector_similarity_score("", "text") == 0.0
    assert lexical_vector_similarity_score("text", "") == 0.0


# ── token_overlap_score ────────────────────────────────────────────────────

def test_token_overlap_all_present() -> None:
    """所有 token 都出现。"""
    score = token_overlap_score("买卖 合同", "本案系买卖合同纠纷")
    assert score == 1.0


def test_token_overlap_partial() -> None:
    """部分 token 出现。"""
    score = token_overlap_score("买卖 专利", "本案系买卖合同纠纷")
    assert score == pytest.approx(0.5)


def test_token_overlap_empty_query() -> None:
    """空查询返回 0。"""
    assert token_overlap_score("", "text") == 0.0


# ── metadata_hint_score ────────────────────────────────────────────────────

def test_metadata_hint_no_relevant_terms() -> None:
    """无相关术语返回 0。"""
    score = metadata_hint_score(keyword="unrelated", title="title", case_digest="digest", content_text="content")
    assert score == 0.0


def test_metadata_hint_with_relevant_terms() -> None:
    """有相关术语返回 > 0。"""
    score = metadata_hint_score(
        keyword="买卖合同", title="买卖合同纠纷", case_digest="原告违约", content_text="本案"
    )
    assert score > 0.0


# ── keyword_overlap_score ──────────────────────────────────────────────────

def test_keyword_overlap_all_present() -> None:
    """所有关键词都出现。"""
    score = keyword_overlap_score(keyword="买卖 合同", title="买卖合同", case_digest="", content_text="")
    assert score == 1.0


def test_keyword_overlap_empty_keyword() -> None:
    """空关键词返回 0。"""
    assert keyword_overlap_score(keyword="", title="t", case_digest="d", content_text="c") == 0.0


# ── summary_overlap_score ──────────────────────────────────────────────────

def test_summary_overlap_basic() -> None:
    """基本摘要匹配。"""
    score = summary_overlap_score(
        case_summary="买卖 合同 纠纷 赔偿", title="买卖 合同", case_digest="", content_text=""
    )
    assert score > 0.0


def test_summary_overlap_empty_summary() -> None:
    """空摘要返回 0。"""
    assert summary_overlap_score(case_summary="", title="t", case_digest="d", content_text="c") == 0.0


# ── coerce_score ───────────────────────────────────────────────────────────

def test_coerce_score_percentage() -> None:
    """百分比字符串。"""
    assert coerce_score("85%") == pytest.approx(0.85)


def test_coerce_score_percentage_fullwidth() -> None:
    """全角百分号。"""
    assert coerce_score("85％") == pytest.approx(0.85)


def test_coerce_score_decimal() -> None:
    """小数。"""
    assert coerce_score("0.85") == pytest.approx(0.85)


def test_coerce_score_over_100() -> None:
    """> 100 的值除以 100。"""
    assert coerce_score("85") == pytest.approx(0.85)


def test_coerce_score_empty() -> None:
    """空字符串返回 0。"""
    assert coerce_score("") == 0.0


def test_coerce_score_none() -> None:
    """None 返回 0。"""
    assert coerce_score(None) == 0.0


def test_coerce_score_non_numeric() -> None:
    """非数字返回 0。"""
    assert coerce_score("abc") == 0.0


# ── normalize_score ────────────────────────────────────────────────────────

def test_normalize_score_normal() -> None:
    """正常范围不变化。"""
    assert normalize_score(0.5) == 0.5


def test_normalize_score_over_1() -> None:
    """1-100 之间除以 100。"""
    assert normalize_score(85.0) == pytest.approx(0.85)


def test_normalize_score_negative() -> None:
    """负数返回 0。"""
    assert normalize_score(-0.5) == 0.0


def test_normalize_score_gt_100() -> None:
    """超过 100 不做处理。"""
    assert normalize_score(150.0) == min(1.0, 150.0)


# ── extract_score_from_text ────────────────────────────────────────────────

def test_extract_score_json_format() -> None:
    """JSON 格式提取。"""
    score = extract_score_from_text('"score": 0.85')
    assert score == pytest.approx(0.85)


def test_extract_score_similarity_format() -> None:
    """相似度格式提取。"""
    score = extract_score_from_text("相似度为85%")
    assert score == pytest.approx(0.85)


def test_extract_score_empty() -> None:
    """空文本返回 0。"""
    assert extract_score_from_text("") == 0.0


# ── focus_content_after_fact_marker ────────────────────────────────────────

def test_focus_after_marker_found() -> None:
    """找到"本院查明"后截取。"""
    text = "前文部分。本院经审理查明，被告应当赔偿原告因违约造成的经济损失共计人民币伍拾万元整。"
    result = focus_content_after_fact_marker(text)
    assert result.startswith("本院经审理查明")


def test_focus_after_marker_not_found() -> None:
    """未找到标记返回全文。"""
    text = "本案系买卖合同纠纷。"
    result = focus_content_after_fact_marker(text)
    assert result == text


def test_focus_after_marker_short_focused() -> None:
    """截取后太短则返回全文。"""
    text = "前文。本院查明。"
    result = focus_content_after_fact_marker(text)
    # 截取部分 < 24 字符，返回全文
    assert result == text


def test_focus_empty_text() -> None:
    """空文本返回空。"""
    assert focus_content_after_fact_marker("") == ""


# ── build_candidate_excerpt ────────────────────────────────────────────────

def test_excerpt_short_text() -> None:
    """短文本原样返回。"""
    text = "这是测试文本"
    assert build_candidate_excerpt(text, max_len=100) == text


def test_excerpt_long_text() -> None:
    """长文本被截取为 head + middle + tail。"""
    text = "a" * 5000
    result = build_candidate_excerpt(text, max_len=3200)
    assert len(result) < len(text)
    assert "..." in result
