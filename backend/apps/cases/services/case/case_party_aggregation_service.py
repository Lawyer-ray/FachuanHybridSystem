"""Business logic services."""

from __future__ import annotations

from .repo import CasePartyRepo


class CasePartyAggregationService:
    def __init__(self, case_party_repo: CasePartyRepo | None = None) -> None:
        self._case_party_repo = case_party_repo

    @property
    def case_party_repo(self) -> CasePartyRepo:
        if self._case_party_repo is None:
            self._case_party_repo = CasePartyRepo()
        return self._case_party_repo

    def get_case_party_names(self, case_id: int) -> list[str]:
        party_names = self.case_party_repo.list_party_names_by_case(case_id)
        return [name for name in party_names if name]
