"""Property-based tests for FilenamePolicy and naming utilities."""

from __future__ import annotations

import re
from unittest.mock import patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.cases.services.template.unified.filename import FilenameInputs, FilenamePolicy
from apps.documents.services.generation.pipeline.naming import (
    _normalize_version,
    contract_docx_filename,
)


# ---------------------------------------------------------------------------
# FilenamePolicy.safe_name
# ---------------------------------------------------------------------------

policy = FilenamePolicy()


@settings(max_examples=200, deadline=None)
@given(name=st.text(min_size=1, max_size=200))
def test_safe_name_no_slashes(name: str) -> None:
    """Output never contains ASCII '/' or '\\'."""
    result = policy.safe_name(name)
    assert "/" not in result
    assert "\\" not in result


@settings(max_examples=200, deadline=None)
@given(name=st.text(min_size=1, max_size=200))
def test_safe_name_no_newlines(name: str) -> None:
    """Output never contains newlines or carriage returns."""
    result = policy.safe_name(name)
    assert "\n" not in result
    assert "\r" not in result


@settings(max_examples=200, deadline=None)
@given(name=st.just(""))
def test_safe_name_empty_returns_unnamed(name: str) -> None:
    """Empty input returns the fallback '未命名'."""
    result = policy.safe_name("")
    assert result == "未命名"


@settings(max_examples=200, deadline=None)
@given(name=st.text(min_size=1, max_size=200))
def test_safe_name_no_leading_trailing_whitespace(name: str) -> None:
    """Output has no leading/trailing whitespace."""
    result = policy.safe_name(name)
    if result != "未命名":
        assert result == result.strip()


@settings(max_examples=200, deadline=None)
@given(name=st.text(min_size=1, max_size=200))
def test_safe_name_no_tabs(name: str) -> None:
    """Output never contains tab characters."""
    result = policy.safe_name(name)
    assert "\t" not in result


# ---------------------------------------------------------------------------
# FilenamePolicy.build
# ---------------------------------------------------------------------------


class FakeDateProvider:
    def __init__(self, d: str) -> None:
        self._d = d

    def today_yyyymmdd(self) -> str:
        return self._d


@settings(max_examples=200, deadline=None)
@given(
    template_name=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    case_name=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
)
def test_build_ends_with_docx(template_name: str, case_name: str) -> None:
    """build() always returns a filename ending with '.docx'."""
    p = FilenamePolicy(date_provider=FakeDateProvider("20260101"))
    inputs = FilenameInputs(
        template_name=template_name,
        case_name=case_name,
        client_name=None,
        function_code=None,
        mode=None,
        our_party_count=1,
    )
    result = p.build(inputs=inputs, legal_rep_cert_code="REP", power_of_attorney_code="POA")
    assert result.endswith(".docx"), f"expected .docx, got {result!r}"


# ---------------------------------------------------------------------------
# _normalize_version
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(version=st.from_regex(r"[Vv]?\d+(\.\d+)?", fullmatch=True))
def test_normalize_version_no_v_prefix(version: str) -> None:
    """Output never starts with 'V' or 'v'."""
    result = _normalize_version(version)
    assert not result.startswith("V") and not result.startswith("v")


@settings(max_examples=200, deadline=None)
@given(version=st.from_regex(r"[Vv]?\d+(\.\d+)?", fullmatch=True))
def test_normalize_version_idempotent(version: str) -> None:
    """Normalizing twice gives the same result."""
    once = _normalize_version(version)
    twice = _normalize_version(once)
    assert once == twice


# ---------------------------------------------------------------------------
# contract_docx_filename
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    template_name=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    contract_name=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
)
def test_contract_docx_filename_ends_with_docx(template_name: str, contract_name: str) -> None:
    """contract_docx_filename always ends with '.docx'."""
    with patch(
        "apps.core.services.filename_template_service.FilenameTemplateService.get_template",
        return_value="{doc_type}（{case_name}）V{version}_{date}",
    ):
        result = contract_docx_filename(template_name=template_name, contract_name=contract_name)
    assert result.endswith(".docx"), f"expected .docx, got {result!r}"
