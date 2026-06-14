"""Property-based guards for text parser robustness."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.client.services.text_parser import (
    _determine_client_type,
    _extract_credit_code,
    _extract_id_number,
    _extract_phone,
    _is_valid_name_candidate,
    parse_client_text,
    parse_multiple_clients_text,
)


@settings(max_examples=40, deadline=None)
@given(st.text(max_size=1024))
def test_text_parser_never_raises_for_arbitrary_input(raw_text: str) -> None:
    parse_client_text(raw_text)
    parse_multiple_clients_text(raw_text)


# ---------- parse_client_text structural invariants ----------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2048))
def test_parse_client_text_output_always_has_required_keys(text: str) -> None:
    result = parse_client_text(text)
    for key in ("name", "phone", "address", "client_type", "id_number", "legal_representative"):
        assert key in result, f"Missing key: {key}"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=2048))
def test_parse_client_text_client_type_is_always_valid(text: str) -> None:
    result = parse_client_text(text)
    assert result["client_type"] in ("legal", "natural", "")


# ---------- _extract_credit_code invariants ----------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1024))
def test_extract_credit_code_length_and_case(text: str) -> None:
    code = _extract_credit_code(text)
    if code is not None:
        assert len(code) == 18, f"Credit code length {len(code)} != 18"
        assert code == code.upper(), f"Credit code not uppercase: {code}"


# ---------- _extract_id_number invariants ----------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1024))
def test_extract_id_number_length(text: str) -> None:
    result = _extract_id_number(text)
    if result is not None:
        assert len(result) in (15, 18), f"ID number length {len(result)} not in (15, 18)"


# ---------- _extract_phone invariants ----------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1024))
def test_extract_phone_no_whitespace(text: str) -> None:
    phone = _extract_phone(text)
    if phone is not None:
        assert phone == phone.replace(" ", "").replace("\t", "").replace("\n", ""), (
            f"Phone contains whitespace: {phone!r}"
        )


# ---------- _determine_client_type invariants ----------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=256), st.text(max_size=1024))
def test_determine_client_type_always_returns_legal_or_natural(name: str, text: str) -> None:
    result = _determine_client_type(name, text)
    assert result in ("legal", "natural"), f"Unexpected client type: {result!r}"


# ---------- _is_valid_name_candidate invariants ----------


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=1024))
def test_is_valid_name_candidate_returns_bool(text: str) -> None:
    result = _is_valid_name_candidate(text)
    assert isinstance(result, bool)


@settings(max_examples=200, deadline=None)
@given(st.text(min_size=0, max_size=1))
def test_is_valid_name_candidate_short_strings_always_false(text: str) -> None:
    assert _is_valid_name_candidate(text) is False
