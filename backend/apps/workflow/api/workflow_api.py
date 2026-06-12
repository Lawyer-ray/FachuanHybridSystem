"""工作流 API 路由（Django Ninja）

包含：工作流运行 API + 模板 CRUD + 步骤注册表
"""

from __future__ import annotations

from typing import Any

from django.utils.text import slugify
from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from ..mcp.workflow_tools import (
    approve_workflow_step,
    cancel_workflow,
    get_workflow_detail,
    list_workflows,
    start_workflow,
)
from ..models import WorkflowTemplate
from ..schemas.workflow_schemas import (
    ApproveStepIn,
    StartWorkflowIn,
    TemplateCreateIn,
    TemplateUpdateIn,
)
from .step_registry import get_flat_step_list, get_step_registry

router = Router(auth=JWTOrSessionAuth())


# ── 工作流运行 ────────────────────────────────────────────────────────────────


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


# ── 步骤注册表 ────────────────────────────────────────────────────────────────


@router.get("/step-registry/")
def get_steps_registry(request: Any) -> list[dict[str, Any]]:
    """获取步骤注册表（按分类分组）"""
    return get_step_registry()


@router.get("/step-registry/flat/")
def get_steps_flat(request: Any) -> list[dict[str, Any]]:
    """获取扁平化步骤列表（用于搜索）"""
    return get_flat_step_list()


# ── 模板 CRUD ─────────────────────────────────────────────────────────────────


@router.get("/templates/", response=list[dict])
def list_templates(
    request: Any,
    category: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    """查询工作流模板列表"""
    qs = WorkflowTemplate.objects.all()
    if category:
        qs = qs.filter(category=category)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)

    return [
        {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "category": t.category,
            "description": t.description,
            "is_active": t.is_active,
            "steps_count": len(t.steps_schema) if isinstance(t.steps_schema, list) else 0,
            "temporal_workflow_name": t.temporal_workflow_name,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
        }
        for t in qs
    ]


@router.post("/templates/")
def create_template(request: Any, payload: TemplateCreateIn) -> dict[str, Any]:
    """创建工作流模板"""
    slug = payload.slug or slugify(payload.name, allow_unicode=True)

    base_slug = slug
    counter = 1
    while WorkflowTemplate.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    template = WorkflowTemplate.objects.create(
        name=payload.name,
        slug=slug,
        category=payload.category,
        description=payload.description,
        temporal_workflow_name=payload.temporal_workflow_name or "DynamicWorkflow",
        steps_schema=[s.model_dump() for s in payload.steps] if payload.steps else [],
        is_active=payload.is_active if payload.is_active is not None else True,
    )

    return {
        "id": template.id,
        "name": template.name,
        "slug": template.slug,
        "message": f"模板「{template.name}」创建成功",
    }


@router.get("/templates/{template_id}/")
def get_template(request: Any, template_id: int) -> dict[str, Any]:
    """获取模板详情"""
    template = WorkflowTemplate.objects.get(pk=template_id)
    return {
        "id": template.id,
        "name": template.name,
        "slug": template.slug,
        "category": template.category,
        "description": template.description,
        "temporal_workflow_name": template.temporal_workflow_name,
        "steps_schema": template.steps_schema,
        "is_active": template.is_active,
        "created_at": template.created_at.isoformat(),
        "updated_at": template.updated_at.isoformat(),
    }


@router.put("/templates/{template_id}/")
def update_template(request: Any, template_id: int, payload: TemplateUpdateIn) -> dict[str, Any]:
    """更新工作流模板"""
    template = WorkflowTemplate.objects.get(pk=template_id)

    if payload.name is not None:
        template.name = payload.name
    if payload.slug is not None:
        template.slug = payload.slug
    if payload.category is not None:
        template.category = payload.category
    if payload.description is not None:
        template.description = payload.description
    if payload.temporal_workflow_name is not None:
        template.temporal_workflow_name = payload.temporal_workflow_name
    if payload.steps is not None:
        template.steps_schema = [s.model_dump() for s in payload.steps]
    if payload.is_active is not None:
        template.is_active = payload.is_active

    template.save()
    return {"id": template.id, "name": template.name, "message": "模板已更新"}


@router.delete("/templates/{template_id}/")
def delete_template(request: Any, template_id: int) -> dict[str, Any]:
    """删除工作流模板"""
    template = WorkflowTemplate.objects.get(pk=template_id)
    name = template.name
    template.delete()
    return {"message": f"模板「{name}」已删除"}


@router.post("/templates/{template_id}/duplicate/")
def duplicate_template(request: Any, template_id: int) -> dict[str, Any]:
    """复制工作流模板"""
    source = WorkflowTemplate.objects.get(pk=template_id)

    new_slug = f"{source.slug}-copy"
    counter = 1
    while WorkflowTemplate.objects.filter(slug=new_slug).exists():
        new_slug = f"{source.slug}-copy-{counter}"
        counter += 1

    new_template = WorkflowTemplate.objects.create(
        name=f"{source.name} (副本)",
        slug=new_slug,
        category=source.category,
        description=source.description,
        temporal_workflow_name=source.temporal_workflow_name,
        steps_schema=source.steps_schema,
        is_active=False,
    )

    return {
        "id": new_template.id,
        "name": new_template.name,
        "slug": new_template.slug,
        "message": f"已复制为「{new_template.name}」",
    }
