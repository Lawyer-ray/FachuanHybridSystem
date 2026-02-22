"""Business logic services."""

from __future__ import annotations

from typing import Any

from .workflows.case_full_create_workflow import CaseFullCreateWorkflow


class CaseFullCreateService:
    def __init__(self, case_service: Any, workflow: CaseFullCreateWorkflow | None = None) -> None:
        self.case_service = case_service
        self._workflow = workflow

    @property
    def workflow(self) -> CaseFullCreateWorkflow:
        if self._workflow is None:
            self._workflow = CaseFullCreateWorkflow(case_service=self.case_service)
        return self._workflow

    def create_case_full(
        self,
        data: dict[str, Any],
        actor_id: int | None = None,
        user: Any | None = None,
    ) -> dict[str, Any]:
        return self.workflow.run(data=data, actor_id=actor_id, user=user)
