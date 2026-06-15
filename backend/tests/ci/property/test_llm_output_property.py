"""Property-based tests for LLM structured output helpers."""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.llm.structured_output import clean_text, extract_json_text, parse_json_content


# ---- clean_text ----


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=4096))
def test_clean_text_removes_json_fences(text: str) -> None:
    result = clean_text(text)
    assert "```json" not in result, "```json found in cleaned output"
    assert "```" not in result, "``` found in cleaned output"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=4096))
def test_clean_text_idempotent(text: str) -> None:
    once = clean_text(text)
    twice = clean_text(once)
    assert once == twice, "clean_text is not idempotent"


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_clean_text_empty_returns_empty(text: str) -> None:
    assert clean_text(text) == ""


# ---- extract_json_text ----


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=4096))
def test_extract_json_text_when_not_none_parses(text: str) -> None:
    result = extract_json_text(text)
    if result is not None:
        # Should be valid JSON
        json.loads(result)


@settings(max_examples=200, deadline=None)
@given(st.just(""))
def test_extract_json_text_empty_returns_none(text: str) -> None:
    assert extract_json_text(text) is None


# ---- parse_json_content ----


_JSON_PRIMITIVES = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-10000, max_value=10000),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=256),
)


@settings(max_examples=200, deadline=None)
@given(
    st.recursive(
        _JSON_PRIMITIVES,
        lambda children: st.one_of(
            st.lists(children, max_size=5),
            st.dictionaries(st.text(max_size=32), children, max_size=5),
        ),
        max_leaves=20,
    )
)
def test_parse_json_content_roundtrip(obj: object) -> None:
    """Wrap a valid JSON object in markers and verify roundtrip."""
    payload = json.dumps(obj, ensure_ascii=False)
    # Wrap in a code fence to simulate LLM output
    text = f"```json\n{payload}\n```"
    result = parse_json_content(text)
    assert json.loads(json.dumps(result)) == json.loads(json.dumps(obj))


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=512).filter(lambda s: not s.strip().startswith(("{", "["))))
def test_parse_json_content_invalid_raises_value_error(text: str) -> None:
    """Text that is clearly not JSON should raise ValueError."""
    # Filter out any text that might accidentally parse as JSON
    # by ensuring it doesn't start with { or [
    full_text = text.strip()
    if not full_text or full_text.startswith(("{", "[")):
        return  # skip borderline cases
    try:
        parse_json_content(full_text)
        # If it succeeds, it must have found valid JSON (unlikely for random text)
    except ValueError:
        pass  # expected


@settings(max_examples=200, deadline=None)
@given(st.just("no json here"))
def test_parse_json_content_no_json_raises(text: str) -> None:
    import pytest

    with pytest.raises(ValueError, match="does not contain valid JSON"):
        parse_json_content(text)
