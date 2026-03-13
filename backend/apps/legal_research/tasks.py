from __future__ import annotations

from typing import Any

from apps.legal_research.services import LegalResearchExecutor


def execute_legal_research_task(task_id: str) -> dict[str, Any]:
    executor = LegalResearchExecutor()
    return executor.run(task_id=task_id)
