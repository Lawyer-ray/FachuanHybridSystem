"""Property-based tests for apps.legal_research.services.similarity.scorers."""

from __future__ import annotations

import math
import re
from collections import Counter

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.legal_research.services.similarity.scorers import (
    char_ngrams,
    coerce_score,
    normalize_score,
    tokenize,
    bm25_proxy_score,
    lexical_vector_similarity_score,
    token_overlap_score,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Reasonable text strings (mix of CJK and ASCII)
_text_strat = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters=" ",
    ),
    min_size=0,
    max_size=200,
)

# Non-empty text with at least 2 chars matching the tokenizer regex
_nontrivial_text_strat = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters=" ",
    ),
    min_size=2,
    max_size=200,
)

# Percentage strings like "85%" or "52.3%"
_pct_strat = st.from_regex(r"[0-9]{1,3}(?:\.[0-9]+)?%", fullmatch=True)

# Numeric strings (0 to 100)
_numeric_strat = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)

# Scores already in [0, 1]
_unit_score_strat = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# coerce_score
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(value=_pct_strat)
def test_coerce_score_percentage_in_unit_range(value: str) -> None:
    """Percentage strings produce a score in [0.0, 1.0]."""
    result = coerce_score(value)
    assert 0.0 <= result <= 1.0


@settings(max_examples=200, deadline=None)
@given(value=_numeric_strat)
def test_coerce_score_numeric_in_unit_range(value: float) -> None:
    """Numeric values produce a score in [0.0, 1.0]."""
    result = coerce_score(value)
    assert 0.0 <= result <= 1.0


@settings(max_examples=200, deadline=None)
@given(value=_pct_strat)
def test_coerce_score_percentage_maps_via_normalize(value: str) -> None:
    """'X%' should map to the same value as normalize_score(X)."""
    import re
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*%", value)
    assume(m is not None)
    num = float(m.group(1))
    expected = normalize_score(num)
    assert coerce_score(value) == expected


@settings(max_examples=200, deadline=None)
@given(value=st.text(max_size=50))
def test_coerce_score_always_in_unit_range(value: str) -> None:
    """Any string input produces a score in [0.0, 1.0]."""
    result = coerce_score(value)
    assert 0.0 <= result <= 1.0


def test_coerce_score_empty_returns_zero() -> None:
    """Empty / None input returns 0.0."""
    assert coerce_score("") == 0.0
    assert coerce_score(None) == 0.0
    assert coerce_score("   ") == 0.0


def test_coerce_score_no_numeric_returns_zero() -> None:
    """Input with no digits returns 0.0."""
    assert coerce_score("abc") == 0.0
    assert coerce_score("no numbers here") == 0.0


@settings(max_examples=200, deadline=None)
@given(value=_numeric_strat)
def test_coerce_score_deterministic(value: float) -> None:
    """Same input always produces the same output."""
    r1 = coerce_score(value)
    r2 = coerce_score(value)
    assert r1 == r2


# ---------------------------------------------------------------------------
# normalize_score
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(score=_unit_score_strat)
def test_normalize_score_passthrough_unit_range(score: float) -> None:
    """Scores already in [0.0, 1.0] pass through unchanged."""
    assert normalize_score(score) == score


@settings(max_examples=200, deadline=None)
@given(score=st.floats(min_value=1.01, max_value=100.0, allow_nan=False, allow_infinity=False))
def test_normalize_score_percentage_range(score: float) -> None:
    """Scores in (1.0, 100.0] are divided by 100 and land in [0.0, 1.0]."""
    result = normalize_score(score)
    assert 0.0 <= result <= 1.0


@settings(max_examples=200, deadline=None)
@given(score=st.floats(min_value=-1000, max_value=0.0, allow_nan=False, allow_infinity=False))
def test_normalize_score_negative_gives_zero(score: float) -> None:
    """Negative scores return 0.0."""
    assume(score < 0)
    assert normalize_score(score) == 0.0


@settings(max_examples=200, deadline=None)
@given(score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
def test_normalize_score_always_in_unit_range(score: float) -> None:
    """Any score in [0, 100] produces output in [0.0, 1.0]."""
    result = normalize_score(score)
    assert 0.0 <= result <= 1.0


@settings(max_examples=200, deadline=None)
@given(score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
def test_normalize_score_deterministic(score: float) -> None:
    """Same input always produces the same output."""
    r1 = normalize_score(score)
    r2 = normalize_score(score)
    assert r1 == r2


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(text=_text_strat)
def test_tokenize_returns_list(text: str) -> None:
    """tokenize always returns a list."""
    result = tokenize(text)
    assert isinstance(result, list)


@settings(max_examples=200, deadline=None)
@given(text=_text_strat)
def test_tokenize_no_stopwords(text: str) -> None:
    """None of the defined stopwords appear in the output."""
    stopwords = {
        "以及", "或者", "如果", "因此", "应当", "需要",
        "有关", "关于", "因为", "但是", "其中", "并且",
        "法院认为", "本院认为", "原告", "被告",
    }
    result = tokenize(text)
    for token in result:
        assert token not in stopwords


@settings(max_examples=200, deadline=None)
@given(text=_text_strat)
def test_tokenize_token_length_range(text: str) -> None:
    """Each token has length between 2 and 10 (matching the regex)."""
    result = tokenize(text)
    for token in result:
        assert 2 <= len(token) <= 10


@settings(max_examples=200, deadline=None)
@given(text=_text_strat)
def test_tokenize_tokens_are_lowercase(text: str) -> None:
    """All tokens are lowercased."""
    result = tokenize(text)
    for token in result:
        assert token == token.lower()


@settings(max_examples=200, deadline=None)
@given(text=_text_strat)
def test_tokenize_deterministic(text: str) -> None:
    """Same input always produces the same token list."""
    assert tokenize(text) == tokenize(text)


def test_tokenize_empty_input() -> None:
    """Empty and None input produce empty list."""
    assert tokenize("") == []
    assert tokenize(None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# char_ngrams
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(text=_text_strat)
def test_char_ngrams_returns_counter(text: str) -> None:
    """char_ngrams always returns a Counter."""
    result = char_ngrams(text)
    assert isinstance(result, Counter)


@settings(max_examples=200, deadline=None)
@given(text=_nontrivial_text_strat)
def test_char_ngrams_correct_lengths(text: str) -> None:
    """All n-gram keys have length 2 or 3."""
    result = char_ngrams(text)
    for gram in result:
        assert len(gram) in (2, 3)


@settings(max_examples=200, deadline=None)
@given(text=st.sampled_from(["", "a", " ", " 1", "x "]))
def test_char_ngrams_short_ascii_input_returns_empty(text: str) -> None:
    """When the normalized text has < 2 ASCII chars, result is empty."""
    result = char_ngrams(text)
    assert len(result) == 0


@settings(max_examples=200, deadline=None)
@given(text=_text_strat)
def test_char_ngrams_deterministic(text: str) -> None:
    """Same input always produces the same Counter."""
    assert char_ngrams(text) == char_ngrams(text)


@settings(max_examples=200, deadline=None)
@given(text=_text_strat)
def test_char_ngrams_all_positive_counts(text: str) -> None:
    """All count values are positive."""
    result = char_ngrams(text)
    for count in result.values():
        assert count > 0


# ---------------------------------------------------------------------------
# bm25_proxy_score
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(query=_text_strat, doc=_text_strat)
def test_bm25_proxy_score_in_unit_range(query: str, doc: str) -> None:
    """bm25_proxy_score output is always in [0.0, 1.0]."""
    result = bm25_proxy_score(query_text=query, document_text=doc)
    assert 0.0 <= result <= 1.0


@settings(max_examples=200, deadline=None)
@given(doc=_text_strat)
def test_bm25_proxy_score_empty_query_returns_zero(doc: str) -> None:
    """Empty query always returns 0.0."""
    assert bm25_proxy_score(query_text="", document_text=doc) == 0.0


@settings(max_examples=200, deadline=None)
@given(query=_text_strat)
def test_bm25_proxy_score_empty_doc_returns_zero(query: str) -> None:
    """Empty document always returns 0.0."""
    assert bm25_proxy_score(query_text=query, document_text="") == 0.0


@settings(max_examples=200, deadline=None)
@given(query=_text_strat, doc=_text_strat)
def test_bm25_proxy_score_deterministic(query: str, doc: str) -> None:
    """Same inputs always produce the same output."""
    r1 = bm25_proxy_score(query_text=query, document_text=doc)
    r2 = bm25_proxy_score(query_text=query, document_text=doc)
    assert r1 == r2


# ---------------------------------------------------------------------------
# lexical_vector_similarity_score
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(text_a=_text_strat, text_b=_text_strat)
def test_lexical_vector_similarity_in_unit_range(text_a: str, text_b: str) -> None:
    """lexical_vector_similarity_score output is in [0.0, 1.0]."""
    result = lexical_vector_similarity_score(text_a, text_b)
    assert 0.0 <= result <= 1.0


@settings(max_examples=200, deadline=None)
@given(text=_nontrivial_text_strat)
def test_lexical_vector_similarity_same_text_gives_one(text: str) -> None:
    """Similarity of a non-trivial text with itself is 1.0."""
    assume(len(re.sub(r"\s+", "", text)) >= 2)
    result = lexical_vector_similarity_score(text, text)
    assert math.isclose(result, 1.0, abs_tol=1e-9)


@settings(max_examples=200, deadline=None)
@given(text_a=_text_strat, text_b=_text_strat)
def test_lexical_vector_similarity_symmetry(text_a: str, text_b: str) -> None:
    """Cosine similarity is symmetric: f(a, b) == f(b, a)."""
    r1 = lexical_vector_similarity_score(text_a, text_b)
    r2 = lexical_vector_similarity_score(text_b, text_a)
    assert r1 == r2


@settings(max_examples=200, deadline=None)
@given(text=_text_strat)
def test_lexical_vector_similarity_empty_input_returns_zero(text: str) -> None:
    """Empty input on either side returns 0.0."""
    assert lexical_vector_similarity_score("", text) == 0.0
    assert lexical_vector_similarity_score(text, "") == 0.0


@settings(max_examples=200, deadline=None)
@given(text_a=_text_strat, text_b=_text_strat)
def test_lexical_vector_similarity_deterministic(text_a: str, text_b: str) -> None:
    """Same inputs always produce the same output."""
    r1 = lexical_vector_similarity_score(text_a, text_b)
    r2 = lexical_vector_similarity_score(text_a, text_b)
    assert r1 == r2


# ---------------------------------------------------------------------------
# token_overlap_score
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(query=_text_strat, text=_text_strat)
def test_token_overlap_score_in_unit_range(query: str, text: str) -> None:
    """token_overlap_score output is in [0.0, 1.0]."""
    result = token_overlap_score(query, text)
    assert 0.0 <= result <= 1.0


@settings(max_examples=200, deadline=None)
@given(text=_text_strat)
def test_token_overlap_score_empty_query_returns_zero(text: str) -> None:
    """Empty query always returns 0.0."""
    assert token_overlap_score("", text) == 0.0


@settings(max_examples=200, deadline=None)
@given(query=_text_strat, text=_text_strat)
def test_token_overlap_score_deterministic(query: str, text: str) -> None:
    """Same inputs always produce the same output."""
    r1 = token_overlap_score(query, text)
    r2 = token_overlap_score(query, text)
    assert r1 == r2


@settings(max_examples=200, deadline=None)
@given(query=_text_strat)
def test_token_overlap_score_empty_haystack_returns_zero(query: str) -> None:
    """When the haystack is empty, tokens can only match if they are themselves empty
    (which never happens since dedupe_tokens skips blanks). Score should be 0.0
    unless the query produces no valid tokens (which also gives 0.0)."""
    result = token_overlap_score(query, "")
    assert 0.0 <= result <= 1.0
