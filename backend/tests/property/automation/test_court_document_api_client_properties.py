from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.services.document_delivery.court_api import (
    ApiResponseError,
    CourtDocumentApiCoordinator,
    CourtDocumentResponseParser,
    TokenExpiredError,
)
from apps.core.exceptions import NetworkError


@dataclass(frozen=True)
class _Outcome:
    kind: str
    payload: dict[str, Any] | None = None


class _FakeHttpClient:
    def __init__(self, outcomes: list[_Outcome | Exception]):
        self._outcomes = list(outcomes)
        self.calls: int = 0
        self.timeout_seconds: float = 1.0

    def post_json(self, *, url: str, headers: dict[str, str], json_data: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        if not self._outcomes:
            raise NetworkError(message="no more outcomes", errors={})
        item = self._outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item.payload or {}

    def get_bytes(self, *, url: str, timeout_seconds: float | None = None) -> bytes:
        self.calls += 1
        if not self._outcomes:
            raise NetworkError(message="no more outcomes", errors={})
        item = self._outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return (item.payload or {}).get("bytes", b"")  # type: ignore[no-any-return]


@pytest.mark.property_test
@settings(max_examples=120, deadline=None)
@given(
    failures=st.lists(st.sampled_from(["network", "token", "api"]), min_size=0, max_size=5),
    succeed=st.booleans(),
)
def test_coordinator_retry_policy_is_bounded(failures: list[str], succeed: bool): # noqa: C901
    parser = CourtDocumentResponseParser()

    outcomes: list[_Outcome | Exception] = []
    for f in failures:
        if f == "network":
            outcomes.append(NetworkError(message="net", errors={}))
        elif f == "token":
            outcomes.append(TokenExpiredError(message="token", errors={}))
        else:
            outcomes.append(ApiResponseError(message="api", response_code=500, errors={}))

    if succeed:
        outcomes.append(_Outcome(kind="ok", payload={"code": 200, "data": {"total": 0, "data": []}}))
    else:
        outcomes.extend([NetworkError(message="net", errors={})] * 3)

    http_client = _FakeHttpClient(outcomes=outcomes)
    coordinator = CourtDocumentApiCoordinator(http_client=http_client, parser=parser, retry_count=2)  # type: ignore[arg-type]

    max_attempts = 3
    first_three = outcomes[:max_attempts]
    expected_calls = 0
    expected_exception: type | None = None
    for i, o in enumerate(first_three):
        expected_calls = i + 1
        if isinstance(o, NetworkError):
            if i == max_attempts - 1:
                expected_exception = NetworkError
                break
            continue
        if isinstance(o, TokenExpiredError):
            expected_exception = TokenExpiredError
            break
        if isinstance(o, ApiResponseError):
            expected_exception = ApiResponseError
            break
        expected_exception = None
        break

    if expected_exception is None:
        coordinator.fetch_document_list(url="u", token="t", page_num=1, page_size=20)
    else:
        with pytest.raises(expected_exception):
            coordinator.fetch_document_list(url="u", token="t", page_num=1, page_size=20)

    assert http_client.calls == expected_calls
    assert http_client.calls <= 3


@pytest.mark.property_test
@settings(max_examples=120, deadline=None)
@given(
    valid=st.lists(
        st.fixed_dictionaries(
            {
                "ah": st.text(min_size=1, max_size=30),
                "sdbh": st.text(min_size=1, max_size=30),
                "fssj": st.text(min_size=1, max_size=30),
            }
        ),
        min_size=1,
        max_size=10,
    ),
    invalid=st.lists(st.dictionaries(keys=st.text(min_size=0, max_size=5), values=st.integers()), max_size=10),
)
def test_parser_document_list_is_monotonic_under_invalid_additions(
    valid: list[dict[str, Any]], invalid: list[dict[str, Any]]
):
    parser = CourtDocumentResponseParser()

    base = {"code": 200, "data": {"total": len(valid), "data": valid}}
    extended = {"code": 200, "data": {"total": len(valid) + len(invalid), "data": valid + invalid}}

    base_result = parser.parse_document_list(base)
    ext_result = parser.parse_document_list(extended)

    base_ids = {(d.ah, d.sdbh, d.fssj) for d in base_result.documents}
    ext_ids = {(d.ah, d.sdbh, d.fssj) for d in ext_result.documents}

    assert base_ids.issubset(ext_ids)


@pytest.mark.property_test
@settings(max_examples=120, deadline=None)
@given(
    weird_items=st.lists(
        st.one_of(
            st.none(),
            st.integers(),
            st.text(),
            st.lists(st.integers()),
            st.dictionaries(keys=st.text(min_size=0, max_size=5), values=st.integers()),
        ),
        max_size=30,
    ),
)
def test_parser_never_raises_on_weird_document_items(weird_items: list[Any]):
    parser = CourtDocumentResponseParser()
    response = {"code": 200, "data": {"total": 0, "data": weird_items}}
    result = parser.parse_document_list(response)
    assert result.total == 0
