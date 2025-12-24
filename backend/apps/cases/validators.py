from typing import Iterable, Tuple, Optional
from .models import CaseStage, CaseType

APPLICABLE_TYPES = {CaseType.CIVIL, CaseType.CRIMINAL, CaseType.ADMINISTRATIVE, CaseType.LABOR, CaseType.INTL}

def is_applicable(case_type: Optional[str]) -> bool:
    return bool(case_type) and case_type in APPLICABLE_TYPES

def _allowed() -> set:
    return {c[0] for c in CaseStage.choices}

def normalize_stages(case_type: Optional[str], representation_stages: Optional[Iterable[str]], current_stage: Optional[str], strict: bool = False) -> Tuple[list[str], Optional[str]]:
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