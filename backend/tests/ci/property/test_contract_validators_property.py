"""Property-based tests for apps.contracts.domain.validators."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.contracts.domain.validators import normalize_representation_stages
from apps.core.exceptions import ValidationException
from apps.core.models.enums import CaseStage, CaseType

# Valid CaseType values that are applicable for contracts
APPLICABLE_TYPES = {"civil", "criminal", "administrative", "labor", "intl"}

# Allowed stage values from CaseStage.choices
ALLOWED_STAGES = {c[0] for c in CaseStage.choices}

# All valid CaseType values
ALL_CASE_TYPES = {c[0] for c in CaseType.choices}

_stage_strat = st.sampled_from(sorted(ALLOWED_STAGES))
_applicable_type_strat = st.sampled_from(sorted(APPLICABLE_TYPES))
_non_applicable_type_strat = st.sampled_from(
    sorted(ALL_CASE_TYPES - APPLICABLE_TYPES),
)
_invalid_stage_strat = st.text(min_size=1, max_size=50).filter(lambda s: s not in ALLOWED_STAGES)


# ---------------------------------------------------------------------------
# normalize_representation_stages
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(
    case_type=_applicable_type_strat,
    stages=st.lists(_stage_strat, min_size=0, max_size=6),
)
def test_normalize_valid_input_subset_of_allowed(case_type: str, stages: list[str]) -> None:
    """Valid stages pass through and all outputs are from the allowed set."""
    result = normalize_representation_stages(case_type, stages)
    for s in result:
        assert s in ALLOWED_STAGES


@settings(max_examples=200, deadline=None)
@given(
    case_type=_applicable_type_strat,
    stages=st.lists(_stage_strat, min_size=0, max_size=6),
)
def test_normalize_idempotent(case_type: str, stages: list[str]) -> None:
    """Normalizing twice gives the same result."""
    r1 = normalize_representation_stages(case_type, stages)
    r2 = normalize_representation_stages(case_type, r1)
    assert r1 == r2


@settings(max_examples=200, deadline=None)
@given(
    case_type=_non_applicable_type_strat,
    stages=st.one_of(st.none(), st.just([])),
)
def test_normalize_non_applicable_returns_empty(case_type: str, stages: list[str] | None) -> None:
    """Non-applicable case types return empty list."""
    result = normalize_representation_stages(case_type, stages)
    assert result == []


@settings(max_examples=200, deadline=None)
@given(
    case_type=_non_applicable_type_strat,
    stages=st.lists(_stage_strat, min_size=1, max_size=3),
)
def test_normalize_non_applicable_strict_with_stages_raises(
    case_type: str, stages: list[str],
) -> None:
    """Non-applicable type + strict=True + non-empty stages raises ValidationException."""
    try:
        normalize_representation_stages(case_type, stages, strict=True)
        assert False, "Expected ValidationException"
    except ValidationException:
        pass


@settings(max_examples=200, deadline=None)
@given(
    case_type=_applicable_type_strat,
    stages=st.lists(_invalid_stage_strat, min_size=1, max_size=3),
)
def test_normalize_invalid_stages_raises(case_type: str, stages: list[str]) -> None:
    """Invalid stage values raise ValidationException."""
    try:
        normalize_representation_stages(case_type, stages)
        assert False, "Expected ValidationException for invalid stages"
    except ValidationException:
        pass
