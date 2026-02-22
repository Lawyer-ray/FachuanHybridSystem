"""Module for validators."""

from __future__ import annotations

from collections.abc import Iterable

from django.utils.translation import gettext_lazy as _

from apps.core.enums import CaseStage, CaseType

__all__: list[str] = [
    "APPLICABLE_TYPES",
    "is_applicable",
    "normalize_stages",
]

APPLICABLE_TYPES: set[str] = {
    str(CaseType.CIVIL),
    str(CaseType.CRIMINAL),
    str(CaseType.ADMINISTRATIVE),
    str(CaseType.LABOR),
    str(CaseType.INTL),
}


def is_applicable(case_type: str | None) -> bool:
    """检查案件类型是否适用阶段管理。"""
    return bool(case_type) and case_type in APPLICABLE_TYPES


def _allowed_stages() -> set[str]:
    """获取所有允许的案件阶段值。"""
    return {str(c[0]) for c in CaseStage.choices}


def normalize_stages(
    case_type: str | None,
    representation_stages: Iterable[str] | None,
    current_stage: str | None,
    strict: bool = False,
) -> tuple[list[str], str | None]:
    """规范化案件阶段数据。"""
    if not is_applicable(case_type):
        if strict and (representation_stages or current_stage):
            raise ValueError(_("stages_not_applicable"))
        return [], None
    rep = list(representation_stages or [])
    cur = current_stage or None
    allowed = _allowed_stages()
    invalid = set(rep) - allowed
    if invalid:
        raise ValueError(
            _("invalid_rep:%(stages)s") % {"stages": ",".join(sorted(invalid))}
        )
    if cur:
        if cur not in allowed:
            raise ValueError(_("invalid_cur"))
        if rep and cur not in set(rep):
            raise ValueError(_("cur_not_in_rep"))
    return rep, cur
