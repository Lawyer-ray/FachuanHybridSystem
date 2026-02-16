"""Business logic services."""

from .repo import CaseAssignmentRepo


class CaseAssignmentAggregationService:
    def __init__(self, case_assignment_repo: CaseAssignmentRepo | None = None) -> None:
        self._case_assignment_repo = case_assignment_repo

    @property
    def case_assignment_repo(self) -> CaseAssignmentRepo:
        if self._case_assignment_repo is None:
            self._case_assignment_repo = CaseAssignmentRepo()
        return self._case_assignment_repo

    def get_primary_lawyer_names_by_case_ids(self, case_ids: list[int]) -> dict[int, str | None]:
        if not case_ids:
            return {}

        assignments = self.case_assignment_repo.list_assignments_by_case_ids(case_ids)

        result: dict[int, str | None] = {}
        for assignment in assignments:
            if assignment.case_id in result:
                continue
            lawyer = getattr(assignment, "lawyer", None)
            if lawyer:
                result[assignment.case_id] = lawyer.real_name or lawyer.username
            else:
                result[assignment.case_id] = None

        for case_id in case_ids:
            result.setdefault(case_id, None)

        return result
