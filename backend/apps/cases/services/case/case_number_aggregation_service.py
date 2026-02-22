"""Business logic services."""

from __future__ import annotations

from .repo import CaseNumberRepo


class CaseNumberAggregationService:
    def __init__(self, case_number_repo: CaseNumberRepo | None = None) -> None:
        self._case_number_repo = case_number_repo

    @property
    def case_number_repo(self) -> CaseNumberRepo:
        if self._case_number_repo is None:
            self._case_number_repo = CaseNumberRepo()
        return self._case_number_repo

    def get_primary_case_numbers_by_case_ids(self, case_ids: list[int]) -> dict[int, str | None]:
        if not case_ids:
            return {}

        rows = self.case_number_repo.list_case_numbers_by_case_ids(case_ids)

        result: dict[int, str | None] = {}
        for case_id, number in rows:
            if case_id in result:
                continue
            result[case_id] = number

        for case_id in case_ids:
            result.setdefault(case_id, None)

        return result
