"""Property-based tests for apps.cases.domain.validators."""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from apps.cases.domain.validators import (
    APPLICABLE_TYPES,
    _allowed_stages,
    is_applicable,
    normalize_stages,
)

# All valid CaseType values (including non-applicable ones)
ALL_CASE_TYPES = {"civil", "criminal", "administrative", "labor", "intl", "special", "advisor"}

# Allowed stage values from CaseStage.choices
ALLOWED_STAGES = _allowed_stages()

_case_type_strat = st.sampled_from(sorted(ALL_CASE_TYPES))
_applicable_case_type_strat = st.sampled_from(sorted(APPLICABLE_TYPES))
_stage_strat = st.sampled_from(sorted(ALLOWED_STAGES))
_invalid_stage_strat = st.text(min_size=1, max_size=50).filter(lambda s: s not in ALLOWED_STAGES)


# ---------------------------------------------------------------------------
# is_applicable
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(case_type=_case_type_strat)
def test_is_applicable_returns_bool(case_type: str) -> None:
    """is_applicable always returns a bool."""
    result = is_applicable(case_type)
    assert isinstance(result, bool)


@settings(max_examples=50, deadline=None)
@given(dummy=st.just(None))
def test_is_applicable_none_and_empty_are_false(dummy: None) -> None:
    """None and empty string return False."""
    assert is_applicable(None) is False
    assert is_applicable("") is False


@settings(max_examples=200, deadline=None)
@given(case_type=_applicable_case_type_strat)
def test_is_applicable_known_types_true(case_type: str) -> None:
    """Known applicable types always return True."""
    assert is_applicable(case_type) is True


@settings(max_examples=200, deadline=None)
@given(case_type=st.text(min_size=1, max_size=30).filter(lambda s: s not in APPLICABLE_TYPES))
def test_is_applicable_unknown_types_false(case_type: str) -> None:
    """Types not in APPLICABLE_TYPES return False."""
    assert is_applicable(case_type) is False


# ---------------------------------------------------------------------------
# normalize_stages
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(
    stages=st.lists(_stage_strat, min_size=0, max_size=5),
    current=st.one_of(st.none(), _stage_strat),
)
def test_normalize_stages_valid_input_returns_subset_of_allowed(
    stages: list[str], current: str | None,
) -> None:
    """When input stages are all valid, output contains only allowed values."""
    # Ensure current is in stages if provided
    if current and current not in stages:
        stages = stages + [current]
    rep, cur = normalize_stages("civil", stages, current)
    for s in rep:
        assert s in ALLOWED_STAGES
    if cur is not None:
        assert cur in ALLOWED_STAGES


@settings(max_examples=200, deadline=None)
@given(
    stages=st.lists(_stage_strat, min_size=0, max_size=5),
    current=st.one_of(st.none(), _stage_strat),
)
def test_normalize_stages_idempotent(stages: list[str], current: str | None) -> None:
    """Normalizing twice gives the same result."""
    if current and current not in stages:
        stages = stages + [current]
    rep1, cur1 = normalize_stages("civil", stages, current)
    rep2, cur2 = normalize_stages("civil", rep1, cur1)
    assert rep1 == rep2
    assert cur1 == cur2


@settings(max_examples=200, deadline=None)
@given(
    stages=st.one_of(st.none(), st.just([])),
    current=st.one_of(st.none(), st.just("")),
)
def test_normalize_stages_non_applicable_type_returns_empty(
    stages: list[str] | None, current: str | None,
) -> None:
    """Non-applicable case types always return ([], None)."""
    rep, cur = normalize_stages("advisor", stages, current)
    assert rep == []
    assert cur is None


@settings(max_examples=200, deadline=None)
@given(stages=st.lists(_invalid_stage_strat, min_size=1, max_size=3))
def test_normalize_stages_invalid_raises(stages: list[str]) -> None:
    """Invalid stage values raise ValueError."""
    try:
        normalize_stages("civil", stages, None)
        assert False, "Expected ValueError for invalid stages"
    except ValueError:
        pass  # expected
