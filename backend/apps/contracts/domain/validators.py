"""Module for validators."""

from collections.abc import Iterable

from django.utils.translation import gettext_lazy as _

from apps.core.enums import CaseStage, CaseType
from apps.core.exceptions import ValidationException

APPLICABLE_TYPES = {CaseType.CIVIL, CaseType.CRIMINAL, CaseType.ADMINISTRATIVE, CaseType.LABOR, CaseType.INTL}


def normalize_representation_stages(
    case_type: str | None,
    representation_stages: Iterable[str] | None,
    strict: bool = False,
) -> list[str]:
    if not case_type or case_type not in APPLICABLE_TYPES:
        rep = list(representation_stages or [])
        if strict and rep:
            raise ValidationException(
                _("代理阶段不适用于此合同类型"), code="STAGES_NOT_APPLICABLE"
            )
        return []

    rep = list(representation_stages or [])
    allowed = {c[0] for c in CaseStage.choices}
    invalid = set(rep) - allowed
    if invalid:
        raise ValidationException(
            _("无效的代理阶段"),
            code="INVALID_STAGES",
            errors={"invalid_stages": sorted(invalid)},
        )
    return rep
