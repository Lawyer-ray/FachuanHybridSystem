"""Property-based tests for miscellaneous validators and utilities."""

from __future__ import annotations

import re

import numpy as np
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.contracts.services.archive.category_mapping import (
    ArchiveCategory,
    get_archive_category,
)
from apps.documents.services.placeholders.litigation.party_formatter import PartyFormatter
from apps.documents.services.placeholders.contract.fee_terms_service import FeeTermsService
from apps.documents.services.document_template.placeholder_extractor import PLACEHOLDER_PATTERN
from apps.client.services.id_card_merge.validation import order_corners, is_convex_quadrilateral, validate_corners

VALID_CATEGORIES = {
    ArchiveCategory.NON_LITIGATION,
    ArchiveCategory.LITIGATION,
    ArchiveCategory.CRIMINAL,
}

formatter = PartyFormatter()


# ---------------------------------------------------------------------------
# get_archive_category
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(case_type=st.text(min_size=0, max_size=50))
def test_get_archive_category_output_in_valid_categories(case_type: str) -> None:
    """Output is always a valid ArchiveCategory value."""
    result = get_archive_category(case_type)
    assert result in VALID_CATEGORIES, f"unexpected category {result!r}"


@settings(max_examples=200, deadline=None)
@given(case_type=st.text(min_size=1, max_size=50).filter(lambda s: s not in ("advisor", "special", "civil", "intl", "labor", "administrative", "criminal")))
def test_get_archive_category_unknown_defaults_to_litigation(case_type: str) -> None:
    """Unknown case types default to 'litigation'."""
    result = get_archive_category(case_type)
    assert result == ArchiveCategory.LITIGATION


# ---------------------------------------------------------------------------
# PartyFormatter.get_role_label
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    role=st.sampled_from(["原告", "被告", "第三人"]),
    index=st.integers(min_value=0, max_value=100),
    total=st.integers(min_value=1, max_value=100),
)
def test_get_role_label_starts_with_role(role: str, index: int, total: int) -> None:
    """Output always starts with the role name."""
    assume(index < total)
    result = formatter.get_role_label(role, index, total)
    assert result.startswith(role), f"expected starts with {role!r}, got {result!r}"


@settings(max_examples=200, deadline=None)
@given(
    role=st.sampled_from(["原告", "被告", "第三人"]),
)
def test_get_role_label_total_1_just_role(role: str) -> None:
    """When total=1, output is exactly the role name."""
    result = formatter.get_role_label(role, 0, 1)
    assert result == role


@settings(max_examples=200, deadline=None)
@given(
    role=st.sampled_from(["原告", "被告", "第三人"]),
    index=st.integers(min_value=0, max_value=9),
    total=st.integers(min_value=2, max_value=10),
)
def test_get_role_label_multiple_parties_has_suffix(role: str, index: int, total: int) -> None:
    """When total > 1, output is longer than the role name alone."""
    assume(index < total)
    result = formatter.get_role_label(role, index, total)
    assert len(result) > len(role)


# ---------------------------------------------------------------------------
# FeeTermsService._to_chinese_ordinal
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(n=st.integers(min_value=1, max_value=10))
def test_to_chinese_ordinal_1_to_10(n: int) -> None:
    """Numbers 1-10 produce the expected Chinese ordinal characters."""
    expected_map = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
    result = FeeTermsService._to_chinese_ordinal(n)
    assert result == expected_map[n]


@settings(max_examples=200, deadline=None)
@given(n=st.integers(min_value=11, max_value=9999))
def test_to_chinese_ordinal_above_10_returns_str(n: int) -> None:
    """Numbers > 10 return str(n)."""
    result = FeeTermsService._to_chinese_ordinal(n)
    assert result == str(n)


# ---------------------------------------------------------------------------
# PLACEHOLDER_PATTERN (from placeholder_extractor)
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    name=st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_一-鿿]{0,20}", fullmatch=True),
)
def test_extract_placeholder_pattern_finds_name(name: str) -> None:
    """A well-formed {{name}} placeholder is matched by the pattern."""
    text = f"{{{{{name}}}}}"
    matches = PLACEHOLDER_PATTERN.findall(text)
    assert name in matches


@settings(max_examples=200, deadline=None)
@given(
    name=st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_一-鿿]{0,20}", fullmatch=True),
    surrounding=st.text(min_size=0, max_size=50),
)
def test_extract_placeholder_pattern_in_context(name: str, surrounding: str) -> None:
    """Placeholder found even with surrounding text."""
    assume("{{" not in surrounding and "}}" not in surrounding)
    text = f"{surrounding}{{{{{name}}}}}{surrounding}"
    matches = PLACEHOLDER_PATTERN.findall(text)
    assert name in matches


@settings(max_examples=200, deadline=None)
@given(
    names=st.lists(
        st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_一-鿿]{0,10}", fullmatch=True),
        min_size=1,
        max_size=5,
        unique=True,
    ),
)
def test_extract_placeholder_pattern_finds_all(names: list[str]) -> None:
    """Multiple placeholders in one text are all found."""
    text = "".join(f"{{{{{n}}}}}" for n in names)
    matches = PLACEHOLDER_PATTERN.findall(text)
    for n in names:
        assert n in matches


# ---------------------------------------------------------------------------
# order_corners
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    x0=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    y0=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    x1=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    y1=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    x2=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    y2=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    x3=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    y3=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
)
def test_order_corners_returns_4x2(
    x0: float, y0: float, x1: float, y1: float,
    x2: float, y2: float, x3: float, y3: float,
) -> None:
    """order_corners always returns a (4, 2) float32 array."""
    corners = np.array([[x0, y0], [x1, y1], [x2, y2], [x3, y3]], dtype=np.float32)
    ordered = order_corners(corners)
    assert ordered.shape == (4, 2)
    assert ordered.dtype == np.float32


@settings(max_examples=200, deadline=None)
@given(
    x0=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    y0=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    x1=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    y1=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    x2=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    y2=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    x3=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    y3=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
)
def test_order_corners_top_left_is_min_sum(
    x0: float, y0: float, x1: float, y1: float,
    x2: float, y2: float, x3: float, y3: float,
) -> None:
    """ordered[0] is the point with the minimum (x+y) among inputs."""
    corners = np.array([[x0, y0], [x1, y1], [x2, y2], [x3, y3]], dtype=np.float32)
    ordered = order_corners(corners)
    sums = corners[:, 0] + corners[:, 1]
    min_idx = int(np.argmin(sums))
    np.testing.assert_array_equal(ordered[0], corners[min_idx])


# ---------------------------------------------------------------------------
# is_convex_quadrilateral
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    x=st.floats(min_value=0.01, max_value=1000, allow_nan=False, allow_infinity=False),
    y=st.floats(min_value=0.01, max_value=1000, allow_nan=False, allow_infinity=False),
)
def test_is_convex_quadrilateral_rectangle_is_true(x: float, y: float) -> None:
    """A rectangle (axis-aligned) is always a convex quadrilateral."""
    corners = np.array(
        [[0, 0], [x, 0], [x, y], [0, y]],
        dtype=np.float32,
    )
    assert is_convex_quadrilateral(corners) is True


@settings(max_examples=200, deadline=None)
@given(
    x=st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False),
    y=st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False),
)
def test_is_convex_quadrilateral_square_is_true(x: float, y: float) -> None:
    """A non-degenerate parallelogram is convex."""
    corners = np.array(
        [[0, 0], [x, 0], [x + 1, y], [1, y]],
        dtype=np.float32,
    )
    assert is_convex_quadrilateral(corners) is True


@settings(max_examples=200, deadline=None)
@given(n=st.integers(min_value=0, max_value=10).filter(lambda v: v != 4))
def test_is_convex_quadrilateral_wrong_count(n: int) -> None:
    """Non-4-point arrays always return False."""
    if n == 0:
        corners = np.array([], dtype=np.float32).reshape(0, 2)
    else:
        corners = np.random.RandomState(42).randn(n, 2).astype(np.float32)
    assert is_convex_quadrilateral(corners) is False


# ---------------------------------------------------------------------------
# validate_corners
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    x=st.integers(min_value=1, max_value=500),
    y=st.integers(min_value=1, max_value=500),
)
def test_validate_corners_valid_rectangle_returns_none(x: int, y: int) -> None:
    """A valid axis-aligned rectangle passes validation (returns None)."""
    corners = [[0, 0], [x, 0], [x, y], [0, y]]
    result = validate_corners(corners)
    assert result is None


@settings(max_examples=200, deadline=None)
@given(text=st.just("junk"))
def test_validate_corners_wrong_count_returns_string(text: str) -> None:
    """Fewer than 4 corners always returns an error string."""
    for n in (0, 1, 2, 3, 5):
        result = validate_corners([[0, 0]] * n)
        assert isinstance(result, str)
        assert len(result) > 0


@settings(max_examples=200, deadline=None)
@given(n=st.integers(min_value=0, max_value=10))
def test_validate_corners_output_type(n: int) -> None:
    """validate_corners always returns None (valid) or a non-empty string (error)."""
    corners = [[i, i] for i in range(n)]
    result = validate_corners(corners)
    assert result is None or (isinstance(result, str) and len(result) > 0)
