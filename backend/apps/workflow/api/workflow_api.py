"""工作流 API 路由（Django Ninja）"""

from __future__ import annotations

from typing import Any

from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from ..mcp.workflow_tools import (
    approve_workflow_step,
    cancel_workflow,
    get_workflow_detail,
    list_workflows,
    start_workflow,
)
from ..schemas.workflow_schemas import ApproveStepIn, StartWorkflowIn

router = Router(auth=JWTOrSessionAuth())


@router.post("/start/")
async def start_workflow_api(request: Any, payload: StartWorkflowIn) -> dict[str, Any]:
    """启动诉讼工作流"""
    return await start_workflow(payload.template_slug, payload.case_id)


@router.get("/runs/")
async def list_workflows_api(
    request: Any,
    case_id: int | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """查询诉讼工作流列表"""
    return await list_workflows(case_id, status)


@router.get("/runs/{run_id}/")
async def get_workflow_detail_api(request: Any, run_id: int) -> dict[str, Any]:
    """查看诉讼工作流详情"""
    return await get_workflow_detail(run_id)


@router.post("/runs/{run_id}/approve/")
async def approve_workflow_api(request: Any, run_id: int, payload: ApproveStepIn) -> dict[str, Any]:
    """审批诉讼工作流步骤"""
    return await approve_workflow_step(run_id, payload.approved, payload.comment)


@router.post("/runs/{run_id}/cancel/")
async def cancel_workflow_api(request: Any, run_id: int) -> dict[str, Any]:
    """取消诉讼工作流"""
    return await cancel_workflow(run_id)
