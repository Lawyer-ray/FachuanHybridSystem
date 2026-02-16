"""Module for validators."""

from collections.abc import Iterable

from apps.core.enums import CaseStage, CaseType

APPLICABLE_TYPES = {CaseType.CIVIL, CaseType.CRIMINAL, CaseType.ADMINISTRATIVE, CaseType.LABOR, CaseType.INTL}


def normalize_representation_stages(
    case_type: str | None,
    representation_stages: Iterable[str] | None,
    strict: bool = False,
) -> list[str]:
    if not case_type or case_type not in APPLICABLE_TYPES:
        rep = list(representation_stages or [])
        if strict and rep:
            raise ValueError("stages_not_applicable")
        return []

    rep = list(representation_stages or [])
    allowed = {c[0] for c in CaseStage.choices}
    invalid = set(rep) - allowed
    if invalid:
        raise ValueError(f"invalid_rep:{','.join(sorted(invalid))}")
    return rep
