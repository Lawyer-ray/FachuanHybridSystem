"""Property-based guards for text parser robustness."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.client.services.text_parser import parse_client_text, parse_multiple_clients_text


@settings(max_examples=40, deadline=None)
@given(st.text(max_size=1024))
def test_text_parser_never_raises_for_arbitrary_input(raw_text: str) -> None:
    parse_client_text(raw_text)
    parse_multiple_clients_text(raw_text)
