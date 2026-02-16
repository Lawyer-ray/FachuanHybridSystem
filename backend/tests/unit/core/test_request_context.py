import pytest

from apps.core.infrastructure.request_context import (
    clear_request_context,
    get_request_id,
    get_trace_ids,
    set_request_context,
)


@pytest.mark.unit
def test_request_context_get_request_id_generates_and_is_stable():
    clear_request_context()
    assert get_request_id(fallback_generate=False) is None

    first = get_request_id()
    second = get_request_id()
    assert first
    assert second == first


@pytest.mark.unit
def test_request_context_set_and_clear_trace_ids():
    clear_request_context()
    set_request_context(request_id="r1", trace_id="t1", span_id="s1")
    assert get_request_id(fallback_generate=False) == "r1"
    assert get_trace_ids() == ("t1", "s1")

    clear_request_context()
    assert get_request_id(fallback_generate=False) is None
    assert get_trace_ids() == (None, None)
