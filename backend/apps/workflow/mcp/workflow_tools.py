"""Claude 通过 MCP 工具操控诉讼工作流（5 个工具）"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

TEMPORAL_ADDRESS = "localhost:7233"
TASK_QUEUE = "fachuan-workflow"


async def _get_client():  # type: ignore[no-untyped-def]
    from temporalio.client import Client
    return await Client.connect(TEMPORAL_ADDRESS)


async def start_workflow(template_slug: str, case_id: int) -> dict[str, Any]:
    """启动诉讼工作流

    Args:
        template_slug: 流程模板标识，如 'sales-contract-dispute-test'
        case_id: 案件 ID
    """
    from apps.workflow.models import WorkflowRun, WorkflowTemplate

    template = await WorkflowTemplate.objects.aget(slug=template_slug, is_active=True)
    client = await _get_client()
    workflow_id = f"{template_slug}-{case_id}"

    run = await WorkflowRun.objects.acreate(
        template=template,
        case_id=case_id,
        temporal_workflow_id=workflow_id,
        temporal_run_id="",
        status=WorkflowRun.Status.RUNNING,
    )

    handle = await client.start_workflow(
        template.temporal_workflow_name,
        args=[{
            "case_id": case_id,
            "run_id": run.id,
            "template_id": template.id,
        }],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    run.temporal_run_id = handle.result_run_id
    await run.asave(update_fields=["temporal_run_id"])

    return {
        "run_id": run.id,
        "workflow_id": workflow_id,
        "status": "running",
        "message": f"已启动「{template.name}」，案件 ID: {case_id}",
    }


async def list_workflows(case_id: int | None = None, status: str | None = None) -> list[dict[str, Any]]:
    """查询诉讼工作流列表

    Args:
        case_id: 按案件 ID 筛选（可选）
        status: 按状态筛选（可选：running/waiting_human/waiting_event/completed/failed）
    """
    from apps.workflow.models import WorkflowRun

    qs = WorkflowRun.objects.select_related("template", "case")
    if case_id:
        qs = qs.filter(case_id=case_id)
    if status:
        qs = qs.filter(status=status)

    runs = [r async for r in qs.order_by("-started_at")[:20]]

    return [
        {
            "run_id": r.id,
            "workflow_id": r.temporal_workflow_id,
            "template": r.template.name,
            "case_name": r.case.name,
            "status": r.status,
            "current_step": r.current_step_id,
            "started_at": r.started_at.isoformat(),
        }
        for r in runs
    ]


async def get_workflow_detail(run_id: int) -> dict[str, Any]:
    """查看诉讼工作流详情，包含各步骤状态

    Args:
        run_id: 工作流运行 ID
    """
    from apps.workflow.models import WorkflowRun

    run = await WorkflowRun.objects.select_related("template", "case").aget(pk=run_id)
    steps = [s async for s in run.step_executions.all()]

    return {
        "run_id": run.id,
        "template": run.template.name,
        "case_name": run.case.name,
        "status": run.status,
        "current_step": run.current_step_id,
        "result": run.result,
        "steps": [
            {
                "step_id": s.step_id,
                "name": s.step_name,
                "type": s.step_type,
                "status": s.status,
                "output_summary": str(s.output_data)[:200] if s.output_data else None,
                "error": s.error_message,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            }
            for s in steps
        ],
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


async def approve_workflow_step(run_id: int, approved: bool, comment: str = "") -> dict[str, Any]:
    """审批诉讼工作流中的待确认步骤

    Args:
        run_id: 工作流运行 ID
        approved: 是否通过
        comment: 审批意见（可选）
    """
    from apps.workflow.models import WorkflowRun

    try:
        run = await WorkflowRun.objects.aget(pk=run_id)
    except WorkflowRun.DoesNotExist:
        return {"error": f"工作流运行 #{run_id} 不存在"}

    if run.status != WorkflowRun.Status.WAITING_HUMAN:
        return {"error": f"当前状态为 {run.status}，无需审批"}

    signal_key = "gate_approved"
    signal_data = {"approved": approved, "step_id": run.current_step_id, "comment": comment}

    try:
        client = await _get_client()
        handle = client.get_workflow_handle(run.temporal_workflow_id)

        await handle.signal(signal_key, signal_data)
    except Exception as e:
        logger.warning("Temporal signal 发送失败: run_id=%s, error=%s", run_id, e)
        return {"error": f"Temporal 信号发送失败: {e}"}

    run.status = WorkflowRun.Status.RUNNING
    await run.asave(update_fields=["status"])

    return {
        "run_id": run_id,
        "step_id": run.current_step_id,
        "action": "approved" if approved else "rejected",
        "message": f"已{'通过' if approved else '拒绝'}审批",
    }


async def cancel_workflow(run_id: int) -> dict[str, Any]:
    """取消正在运行的诉讼工作流

    Args:
        run_id: 工作流运行 ID
    """
    from django.utils import timezone

    from apps.workflow.models import WorkflowRun

    try:
        run = await WorkflowRun.objects.aget(pk=run_id)
    except WorkflowRun.DoesNotExist:
        return {"error": f"工作流运行 #{run_id} 不存在"}

    try:
        client = await _get_client()
        handle = client.get_workflow_handle(run.temporal_workflow_id)
        await handle.cancel()
    except Exception as e:
        logger.warning("Temporal cancel 失败: run_id=%s, error=%s", run_id, e)
        return {"error": f"Temporal 取消失败: {e}"}

    run.status = WorkflowRun.Status.CANCELLED
    run.finished_at = timezone.now()
    await run.asave(update_fields=["status", "finished_at"])

    return {"run_id": run_id, "status": "cancelled", "message": "已取消"}


async def delete_workflow_run(run_id: int) -> dict[str, Any]:
    """删除诉讼工作流运行记录

    Args:
        run_id: 工作流运行 ID
    """
    from apps.workflow.models import WorkflowRun

    try:
        run = await WorkflowRun.objects.select_related("template").aget(pk=run_id)
    except WorkflowRun.DoesNotExist:
        return {"error": f"工作流运行 #{run_id} 不存在"}

    # 如果还在运行中，先尝试取消 Temporal 工作流
    if run.status in (WorkflowRun.Status.RUNNING, WorkflowRun.Status.WAITING_HUMAN, WorkflowRun.Status.WAITING_EVENT):
        try:
            client = await _get_client()
            handle = client.get_workflow_handle(run.temporal_workflow_id)
            await handle.cancel()
        except Exception as e:
            logger.info("删除前取消 Temporal 工作流失败（可能已结束）: %s", e)

    run_id_display = run.id
    template_name = run.template.name if run.template else "未知"
    await run.adelete()

    return {"run_id": run_id_display, "message": f"已删除工作流「{template_name}」"}
