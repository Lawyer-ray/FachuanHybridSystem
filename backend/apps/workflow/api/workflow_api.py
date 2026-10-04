"""工作流 API 路由（Django Ninja）

包含：工作流运行 API + 模板 CRUD + 步骤注册表
模板 CRUD 的业务逻辑（ORM/slug 去重/步骤白名单）在 services/template_service.py。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from ninja import Router

from apps.core.security.admin_access import ensure_admin_request, get_request_user
from apps.core.security.auth import JWTOrSessionAuth

from ..mcp.workflow_tools import (
    approve_workflow_step,
    cancel_workflow,
    delete_workflow_run,
    get_workflow_detail,
    list_workflows,
    start_workflow,
)
from ..schemas.workflow_schemas import ApproveStepIn, StartWorkflowIn, TemplateCreateIn, TemplateUpdateIn
from ..services import WorkflowTemplateService, get_workflow_template_service
from .step_registry import get_flat_step_list, get_step_registry

router = Router(auth=JWTOrSessionAuth())


def _get_template_service() -> WorkflowTemplateService:
    """工厂函数：创建工作流模板服务实例"""
    return get_workflow_template_service()


# ── 工作流运行 ────────────────────────────────────────────────────────────────


async def _require_run_case_access(request: Any, run_id: int) -> None:
    """校验当前用户对工作流 run 所属案件的访问权（安全审计 IDOR）。"""
    from apps.core.security import get_request_access_context

    from ..services.run_access_service import WorkflowRunAccessService

    ctx = get_request_access_context(request)
    await WorkflowRunAccessService().ensure_run_case_access(run_id=run_id, ctx=ctx)


@router.post("/start")
async def start_workflow_api(request: Any, payload: StartWorkflowIn) -> dict[str, Any]:
    """启动诉讼工作流"""
    from apps.core.security import get_request_access_context

    ctx = get_request_access_context(request)
    return await start_workflow(
        payload.template_slug,
        payload.case_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.get("/runs")
async def list_workflows_api(
    request: Any,
    case_id: int | None = None,
    status: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """查询诉讼工作流列表（标准信封 items/total/page/page_size/total_pages；limit cap 100）"""
    return await list_workflows(case_id, status, limit=limit)


@router.get("/runs/{run_id}")
async def get_workflow_detail_api(request: Any, run_id: int) -> dict[str, Any]:
    """查看诉讼工作流详情"""
    await _require_run_case_access(request, run_id)
    return await get_workflow_detail(run_id)


@router.post("/runs/{run_id}/approve")
async def approve_workflow_api(request: Any, run_id: int, payload: ApproveStepIn) -> dict[str, Any]:
    """审批诉讼工作流步骤"""
    await _require_run_case_access(request, run_id)
    result = await approve_workflow_step(run_id, payload.approved, payload.comment)
    if "error" in result:
        from ninja.errors import HttpError

        raise HttpError(400, result["error"])
    return result


@router.post("/runs/{run_id}/cancel")
async def cancel_workflow_api(request: Any, run_id: int) -> dict[str, Any]:
    """取消诉讼工作流"""
    await _require_run_case_access(request, run_id)
    result = await cancel_workflow(run_id)
    if "error" in result:
        from ninja.errors import HttpError

        raise HttpError(400, result["error"])
    return result


@router.delete("/runs/{run_id}")
async def delete_workflow_api(request: Any, run_id: int) -> dict[str, Any]:
    """删除诉讼工作流"""
    await _require_run_case_access(request, run_id)
    result = await delete_workflow_run(run_id)
    if "error" in result:
        from ninja.errors import HttpError

        raise HttpError(400, result["error"])
    return result


# ── 步骤注册表 ────────────────────────────────────────────────────────────────


@router.get("/step-registry")
def get_steps_registry(request: Any) -> list[dict[str, Any]]:
    """获取步骤注册表（按分类分组）"""
    return get_step_registry()


@router.get("/step-registry/flat")
def get_steps_flat(request: Any) -> list[dict[str, Any]]:
    """获取扁平化步骤列表（用于搜索）"""
    return get_flat_step_list()


# ── 模板 CRUD（业务逻辑在 services/template_service.py） ──────────────────────


@router.get("/templates", response=list[dict])
def list_templates(
    request: Any,
    category: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    """查询工作流模板列表"""
    return _get_template_service().list_templates(category=category, is_active=is_active)


@router.post("/templates")
def create_template(request: Any, payload: TemplateCreateIn) -> dict[str, Any]:
    """创建工作流模板（仅管理员，安全审计 A-01）"""
    ensure_admin_request(request, message="仅管理员可管理工作流模板", code="PERMISSION_DENIED")
    return _get_template_service().create_template(payload, user=get_request_user(request))


@router.get("/templates/{template_id}")
def get_template(request: Any, template_id: int) -> dict[str, Any]:
    """获取模板详情"""
    return _get_template_service().get_template(template_id)


@router.put("/templates/{template_id}")
def update_template(request: Any, template_id: int, payload: TemplateUpdateIn) -> dict[str, Any]:
    """更新工作流模板（仅管理员，安全审计 A-01）"""
    ensure_admin_request(request, message="仅管理员可管理工作流模板", code="PERMISSION_DENIED")
    return _get_template_service().update_template(template_id, payload, user=get_request_user(request))


@router.delete("/templates/{template_id}")
def delete_template(request: Any, template_id: int) -> dict[str, Any]:
    """删除工作流模板（仅管理员，安全审计 A-01）"""
    ensure_admin_request(request, message="仅管理员可管理工作流模板", code="PERMISSION_DENIED")
    return _get_template_service().delete_template(template_id)


@router.post("/templates/{template_id}/duplicate")
def duplicate_template(request: Any, template_id: int) -> dict[str, Any]:
    """复制工作流模板（仅管理员，安全审计 A-01）"""
    ensure_admin_request(request, message="仅管理员可管理工作流模板", code="PERMISSION_DENIED")
    return _get_template_service().duplicate_template(template_id, user=get_request_user(request))
