"""外部事件 → 恢复对应的 Temporal Workflow"""

from __future__ import annotations

import logging

from temporalio.client import Client

from django.conf import settings

from apps.workflow.models import WorkflowRun

logger = logging.getLogger(__name__)

TEMPORAL_ADDRESS = getattr(settings, "TEMPORAL_ADDRESS", "localhost:7233")


async def on_court_reply(case_id: int, status: str, documents: list | None = None) -> None:
    """法院审核结果到达"""
    runs = [
        r async for r in WorkflowRun.objects.filter(
            case_id=case_id,
            status=WorkflowRun.Status.WAITING_EVENT,
            current_step_id="wait_court",
        )
    ]
    if not runs:
        logger.info("案件 %d 无等待中的 workflow", case_id)
        return

    client = await Client.connect(TEMPORAL_ADDRESS)
    for run in runs:
        handle = client.get_workflow_handle(run.temporal_workflow_id)
        await handle.signal("gate_approved", {"step_id": run.current_step_id, "approved": True, "comment": status, "documents": documents or []})
        run.status = WorkflowRun.Status.RUNNING
        await run.asave(update_fields=["status"])
        logger.info("Workflow %s 收到法院回复: %s", run.temporal_workflow_id, status)
