"""Business workflow orchestration."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.cases.services.case.repo.case_full_create_repo import CaseFullCreateRepo
from apps.core.exceptions import ConflictError, ValidationException


class CaseFullCreateWorkflow:
    def __init__(self, case_service: Any, repo: CaseFullCreateRepo | None = None) -> None:
        self.case_service = case_service
        self._repo = repo

    @property
    def repo(self) -> CaseFullCreateRepo:
        if self._repo is None:
            self._repo = CaseFullCreateRepo()
        return self._repo

    @transaction.atomic
    def run(
        self,
        *,
        data: dict[str, Any],
        actor_id: int | None = None,
        user: Any | None = None,
    ) -> dict[str, Any]:
        case_data = data.get("case", {})
        parties_data = data.get("parties", [])
        assignments_data = data.get("assignments", [])
        logs_data = data.get("logs", [])
        supervising_authorities_data = data.get("supervising_authorities", [])

        if logs_data and not actor_id:
            raise ValidationException(
                message="操作人不能为空",
                code="MISSING_ACTOR",
                errors={"actor_id": "创建日志时必须提供有效的操作人"},
            )

        case = self.case_service.create_case(case_data, user=user)

        seen_party_client_ids = set()
        for party in parties_data:
            client_id = party["client_id"]
            if client_id in seen_party_client_ids:
                raise ConflictError("当事人数据重复")
            seen_party_client_ids.add(client_id)

        parties = self.repo.bulk_create_case_parties(case=case, parties=parties_data)

        seen_assignment_lawyer_ids = set()
        for assignment in assignments_data:
            lawyer_id = assignment["lawyer_id"]
            if lawyer_id in seen_assignment_lawyer_ids:
                raise ConflictError("指派数据重复")
            seen_assignment_lawyer_ids.add(lawyer_id)
        assignments = self.repo.bulk_create_case_assignments(case=case, assignments=assignments_data)

        logs = self.repo.bulk_create_case_logs(case=case, logs=logs_data, actor_id=actor_id) if logs_data else []  # type: ignore[arg-type]

        supervising_authorities = (
            self.repo.bulk_create_supervising_authorities(case=case, authorities=supervising_authorities_data)
            if supervising_authorities_data
            else []
        )

        return {
            "case": case,
            "parties": parties,
            "assignments": assignments,
            "logs": logs,
            "supervising_authorities": supervising_authorities,
        }
