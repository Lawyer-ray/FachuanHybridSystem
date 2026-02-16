from collections.abc import Iterable

"""Module for validators."""


from apps.core.enums import CaseStage, CaseType

APPLICABLE_TYPES: set[str] = {CaseType.CIVIL, CaseType.CRIMINAL, CaseType.ADMINISTRATIVE, CaseType.LABOR, CaseType.INTL}


def is_applicable(case_type: str | None) -> bool:
    return bool(case_type) and case_type in APPLICABLE_TYPES


def _allowed() -> set[str]:
    return {c[0] for c in CaseStage.choices}


def normalize_stages(
    case_type: str | None,
    representation_stages: Iterable[str] | None,
    current_stage: str | None,
    strict: bool = False,
) -> tuple[list[str], str | None]:
    if not is_applicable(case_type):
        if strict and (representation_stages or current_stage):
            raise ValueError("stages_not_applicable")
        return [], None
    rep = list(representation_stages or [])
    cur = current_stage or None
    allowed = _allowed()
    invalid = set(rep) - allowed
    if invalid:
        raise ValueError(f"invalid_rep:{','.join(sorted(invalid))}")
    if cur:
        if cur not in allowed:
            raise ValueError("invalid_cur")
        if rep and cur not in set(rep):
            raise ValueError("cur_not_in_rep")
    return rep, cur
