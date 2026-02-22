from __future__ import annotations

from collections.abc import Iterable

from apps.cases.models import CaseAssignment


class CaseAssignmentRepo:
    def check_case_access(self, case_id: int, user_id: int) -> bool:
        return CaseAssignment.objects.filter(case_id=case_id, lawyer_id=user_id).exists()

    def has_case_access(self, case_id: int, lawyer_ids: Iterable[int]) -> bool:
        if not lawyer_ids:
            return False
        return CaseAssignment.objects.filter(case_id=case_id, lawyer_id__in=list(lawyer_ids)).exists()

    def list_assignments_by_case_ids(self, case_ids: Iterable[int]) -> list[CaseAssignment]:
        if not case_ids:
            return []
        return list(
            CaseAssignment.objects.filter(case_id__in=case_ids).select_related("lawyer").order_by("case_id", "id")
        )
