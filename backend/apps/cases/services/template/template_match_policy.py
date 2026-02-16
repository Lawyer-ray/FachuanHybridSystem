"""Business logic services."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class CaseTemplateMatchInput:
    case_type: str | None
    case_stage: str | None
    legal_statuses: set[str]


class CaseTemplateMatchPolicy:
    def is_match(self, template: object, match_input: CaseTemplateMatchInput) -> bool:
        case_types = getattr(template, "case_types", None) or []
        type_match = (
            "all" in case_types or (match_input.case_type and match_input.case_type in case_types) or not case_types
        )

        case_stages = getattr(template, "case_stages", None) or []
        stage_match = (
            "all" in case_stages
            or (match_input.case_stage and match_input.case_stage in case_stages)
            or not case_stages
        )

        template_legal_statuses = getattr(template, "legal_statuses", None) or []
        match_mode = getattr(template, "legal_status_match_mode", "any") or "any"
        legal_status_match = self._match_legal_status(template_legal_statuses, match_input.legal_statuses, match_mode)

        return bool(type_match and stage_match and legal_status_match)

    def filter(self, templates: Iterable[object], match_input: CaseTemplateMatchInput) -> list[object]:
        return [t for t in templates if self.is_match(t, match_input)]

    def _match_legal_status(
        self, template_legal_statuses: list[str], case_legal_statuses: set[str], match_mode: str
    ) -> bool:
        if not template_legal_statuses:
            return True

        template_set = set(template_legal_statuses)

        if match_mode == "any":
            if not case_legal_statuses:
                return True
            return bool(case_legal_statuses & template_set)

        if match_mode == "all":
            return template_set <= case_legal_statuses

        if match_mode == "exact":
            return case_legal_statuses == template_set

        if not case_legal_statuses:
            return True
        return bool(case_legal_statuses & template_set)
