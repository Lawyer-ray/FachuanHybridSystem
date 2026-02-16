"""Data repository layer."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from apps.cases.models import Case, CaseAssignment, CaseLog, CaseParty, SupervisingAuthority


class CaseFullCreateRepo:
    def create_case_party(self, *, case: Case, client_id: int, legal_status: str | None) -> CaseParty:
        return CaseParty.objects.create(case=case, client_id=client_id, legal_status=legal_status)

    def create_case_assignment(self, *, case: Case, lawyer_id: int) -> CaseAssignment:
        return CaseAssignment.objects.create(case=case, lawyer_id=lawyer_id)

    def create_case_log(self, *, case: Case, content: str, actor_id: int) -> CaseLog:
        return CaseLog.objects.create(case=case, content=content, actor_id=actor_id)

    def create_supervising_authority(
        self,
        *,
        case: Case,
        name: str | None,
        authority_type: str | None,
    ) -> SupervisingAuthority:
        return SupervisingAuthority.objects.create(case=case, name=name, authority_type=authority_type)

    def bulk_create_case_parties(self, *, case: Case, parties: Iterable[dict[str, Any]]) -> list[CaseParty]:
        results: list[Any] = []
        for party in parties:
            results.append(
                self.create_case_party(
                    case=case,
                    client_id=party["client_id"],
                    legal_status=party.get("legal_status"),
                )
            )
        return results

    def bulk_create_case_assignments(
        self, *, case: Case, assignments: Iterable[dict[str, Any]]
    ) -> list[CaseAssignment]:
        results: list[Any] = []
        for assignment in assignments:
            results.append(
                self.create_case_assignment(
                    case=case,
                    lawyer_id=assignment["lawyer_id"],
                )
            )
        return results

    def bulk_create_case_logs(self, *, case: Case, logs: Iterable[dict[str, Any]], actor_id: int) -> list[CaseLog]:
        results: list[Any] = []
        for log in logs:
            results.append(
                self.create_case_log(
                    case=case,
                    content=log["content"],
                    actor_id=actor_id,
                )
            )
        return results

    def bulk_create_supervising_authorities(
        self,
        *,
        case: Case,
        authorities: Iterable[dict[str, Any]],
    ) -> list[SupervisingAuthority]:
        results: list[Any] = []
        for authority in authorities:
            results.append(
                self.create_supervising_authority(
                    case=case,
                    name=authority.get("name"),
                    authority_type=authority.get("authority_type"),
                )
            )
        return results
