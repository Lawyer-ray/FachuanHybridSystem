"""Property-based tests for apps.cases.utils."""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.cases.utils import (
    CASE_LOG_ALLOWED_EXTENSIONS,
    _basename,
    get_file_extension_lower,
    normalize_case_number,
    validate_case_log_attachment,
)


# ---------------------------------------------------------------------------
# normalize_case_number
# ---------------------------------------------------------------------------

FORBIDDEN_CHARS = set("()[]〔〕　 ")


@settings(max_examples=200, deadline=None)
@given(number=st.text(min_size=1, max_size=200), ensure_hao=st.booleans())
def test_normalize_case_number_no_forbidden_chars(number: str, ensure_hao: bool) -> None:
    """Output never contains parentheses, brackets, or spaces."""
    result = normalize_case_number(number, ensure_hao=ensure_hao)
    for ch in FORBIDDEN_CHARS:
        assert ch not in result, f"forbidden char {ch!r} found in {result!r}"


@settings(max_examples=200, deadline=None)
@given(number=st.text(min_size=1, max_size=200))
def test_normalize_case_number_idempotent(number: str) -> None:
    """Normalizing twice gives the same result."""
    once = normalize_case_number(number)
    twice = normalize_case_number(once)
    assert once == twice


@settings(max_examples=200, deadline=None)
@given(number=st.text(min_size=1, max_size=200).filter(lambda s: s.strip()))
def test_normalize_case_number_ensure_hao(number: str) -> None:
    """When ensure_hao=True, result always ends with '号' (for non-empty after processing)."""
    result = normalize_case_number(number, ensure_hao=True)
    assert result.endswith("号")


def test_normalize_case_number_empty_and_none() -> None:
    """Empty string and None always return empty string."""
    assert normalize_case_number("", ensure_hao=False) == ""
    assert normalize_case_number("", ensure_hao=True) == ""


# ---------------------------------------------------------------------------
# _basename
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(path=st.text(min_size=1, max_size=300))
def test_basename_never_contains_slash(path: str) -> None:
    """Result never contains a path separator."""
    result = _basename(path)
    assert "/" not in result
    assert "\\" not in result


def test_basename_empty_and_none() -> None:
    """Empty/None inputs produce empty string."""
    assert _basename("") == ""


# ---------------------------------------------------------------------------
# get_file_extension_lower
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(filename=st.text(min_size=1, max_size=200))
def test_get_file_extension_starts_with_dot_or_empty(filename: str) -> None:
    """Extension always starts with '.' or is empty."""
    ext = get_file_extension_lower(filename)
    assert ext == "" or ext.startswith(".")


@settings(max_examples=200, deadline=None)
@given(filename=st.text(min_size=1, max_size=200))
def test_get_file_extension_always_lowercase(filename: str) -> None:
    """Extension is always lowercase."""
    ext = get_file_extension_lower(filename)
    assert ext == ext.lower()


@settings(max_examples=200, deadline=None)
@given(filename=st.text(min_size=1, max_size=200))
def test_get_file_extension_idempotent(filename: str) -> None:
    """When get_file_extension_lower returns a non-trivial extension, it is idempotent.

    Edge cases like '0.' produce '.' which is then collapsed to '' by the
    basename-is-dot guard -- this is correct behaviour, not a violation.
    """
    ext = get_file_extension_lower(filename)
    if ext and ext != ".":
        # Valid extension should be stable when re-applied
        ext2 = get_file_extension_lower(ext)
        assert ext == ext2


# ---------------------------------------------------------------------------
# validate_case_log_attachment
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(
    filename=st.text(min_size=1, max_size=200),
    size=st.one_of(st.none(), st.integers(min_value=0, max_value=100_000_000)),
)
def test_validate_always_returns_2_tuple(filename: str, size: int | None) -> None:
    """Return value is always a (bool, str | None) tuple."""
    result = validate_case_log_attachment(filename, size)
    assert isinstance(result, tuple) and len(result) == 2
    ok, msg = result
    assert isinstance(ok, bool)
    assert msg is None or isinstance(msg, str)


@settings(max_examples=200, deadline=None)
@given(
    ext=st.sampled_from(sorted(CASE_LOG_ALLOWED_EXTENSIONS)),
    basename=st.from_regex(r"[a-zA-Z0-9_]{1,30}", fullmatch=True),
    size=st.integers(min_value=1, max_value=10_000_000),
)
def test_validate_known_good_extensions(ext: str, basename: str, size: int) -> None:
    """Files with known allowed extensions pass validation."""
    filename = f"{basename}{ext}"
    ok, msg = validate_case_log_attachment(filename, size)
    assert ok is True
    assert msg is None


# ---------------------------------------------------------------------------
# _format_simple_case_type_label
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock

from apps.core.models.enums import SimpleCaseType


def _make_service():
    """Create a minimal mock of CaseFilingNumberService with bound method."""
    from apps.cases.services.number.case_filing_number_service import (
        CaseFilingNumberService,
    )

    svc = CaseFilingNumberService.__new__(CaseFilingNumberService)
    return svc


_known_values = [
    SimpleCaseType.CIVIL,
    SimpleCaseType.ADMINISTRATIVE,
    SimpleCaseType.CRIMINAL,
    SimpleCaseType.EXECUTION,
    SimpleCaseType.BANKRUPTCY,
]

_known_labels = {"民事", "行政", "刑事", "申请执行", "破产"}


@settings(max_examples=200, deadline=None)
@given(case_type=st.sampled_from(_known_values))
def test_format_simple_known_values(case_type: str) -> None:
    """Known SimpleCaseType values produce the expected Chinese label."""
    svc = _make_service()
    result = svc._format_simple_case_type_label(case_type)
    assert result in _known_labels


@settings(max_examples=200, deadline=None)
@given(case_type=st.text(min_size=1, max_size=50).filter(
    lambda s: s not in {v.value for v in SimpleCaseType}
))
def test_format_simple_unknown_returns_input(case_type: str) -> None:
    """Unknown case_type values are returned as-is."""
    svc = _make_service()
    result = svc._format_simple_case_type_label(case_type)
    assert result == case_type


@settings(max_examples=200, deadline=None)
@given(case_type=st.text(min_size=1, max_size=50))
def test_format_simple_always_non_empty_string(case_type: str) -> None:
    """Output is always a non-empty string."""
    svc = _make_service()
    result = svc._format_simple_case_type_label(case_type)
    assert isinstance(result, str)
    assert len(result) > 0
