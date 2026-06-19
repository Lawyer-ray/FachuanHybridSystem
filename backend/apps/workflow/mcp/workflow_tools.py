"""Claude 通过 MCP 工具操控诉讼工作流和模板管理"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

try:
    from django.conf import settings
    TEMPORAL_ADDRESS = getattr(settings, "TEMPORAL_ADDRESS", "localhost:7233")
except Exception:
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
    workflow_id = f"{template_slug}-{case_id}-{uuid4().hex[:8]}"

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


# ════════════════════════════════════════════════════════════════
# 模板管理 MCP 工具 — AI Agent 可通过这些工具创建和管理工作流模板
# ════════════════════════════════════════════════════════════════


async def get_step_registry() -> list[dict[str, Any]]:
    """获取所有可用的工作流步骤类型（步骤注册表）

    AI Agent 在创建模板前应先调用此工具，了解有哪些步骤可以使用。
    返回按类别分组的步骤定义列表，每个步骤包含 id、name、type、mcp_tool 等信息。
    """
    from apps.workflow.api.step_registry import STEP_CATEGORIES
    return STEP_CATEGORIES


async def get_step_registry_flat() -> list[dict[str, Any]]:
    """获取扁平化的工作流步骤列表（用于搜索）

    返回所有步骤的扁平列表，每个步骤附带 category_id 和 category_name。
    """
    from apps.workflow.api.step_registry import get_flat_step_list
    return get_flat_step_list()


async def create_workflow_template(
    name: str,
    steps: list[dict[str, Any]],
    slug: str = "",
    category: str = "litigation",
    description: str = "",
) -> dict[str, Any]:
    """创建 DynamicWorkflow 工作流模板

    AI Agent 根据用户需求，从步骤注册表中选择步骤组合成工作流模板。
    模板创建后可通过 start_workflow 启动执行。

    Args:
        name: 模板名称，如 "买卖合同纠纷起诉流程"
        steps: 步骤列表，每步包含 id/name/type/mcp_tool/config 等字段
               示例: [{"id": "collect_facts", "name": "收集案件事实", "type": "activity", "mcp_tool": "get_case", "config": {}}]
        slug: URL 标识（留空自动生成）
        category: 分类 (litigation/preservation/enforcement)
        description: 模板描述

    Returns:
        创建的模板信息，包含 id、name、slug、steps_count
    """
    from django.utils.text import slugify as dj_slugify

    from apps.workflow.models import WorkflowTemplate

    if not slug:
        slug = dj_slugify(name, allow_unicode=True)
        # 确保唯一
        base_slug = slug
        counter = 1
        while await WorkflowTemplate.objects.filter(slug=slug).aexists():
            slug = f"{base_slug}-{counter}"
            counter += 1

    # 将步骤列表规范化为 steps_schema 格式
    steps_schema = []
    for step in steps:
        steps_schema.append({
            "id": step.get("id", ""),
            "name": step.get("name", ""),
            "type": step.get("type", "activity"),
            "description": step.get("description", ""),
            "icon": step.get("icon", ""),
            "mcp_tool": step.get("mcp_tool", ""),
            "config": step.get("config", {}),
            "timeout": step.get("timeout", "30s"),
            "retry_max": step.get("retry_max", 3),
            "on_fail": step.get("on_fail", "abort"),
        })

    template = await WorkflowTemplate.objects.acreate(
        name=name,
        slug=slug,
        category=category,
        description=description,
        temporal_workflow_name="DynamicWorkflow",
        steps_schema=steps_schema,
        is_active=True,
    )

    return {
        "template_id": template.id,
        "name": template.name,
        "slug": template.slug,
        "category": template.category,
        "steps_count": len(steps_schema),
        "steps_schema": steps_schema,
        "message": f"模板「{name}」创建成功，包含 {len(steps_schema)} 个步骤",
    }


async def update_workflow_template(
    template_id: int,
    name: str | None = None,
    steps: list[dict[str, Any]] | None = None,
    description: str | None = None,
    category: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    """更新已有的工作流模板

    Args:
        template_id: 模板 ID
        name: 新名称（可选）
        steps: 新步骤列表（可选，传入则完全替换原有步骤）
        description: 新描述（可选）
        category: 新分类（可选）
        is_active: 是否启用（可选）
    """
    from apps.workflow.models import WorkflowTemplate

    try:
        template = await WorkflowTemplate.objects.aget(pk=template_id)
    except WorkflowTemplate.DoesNotExist:
        return {"error": f"模板 #{template_id} 不存在"}

    updated_fields = []
    if name is not None:
        template.name = name
        updated_fields.append("name")
    if description is not None:
        template.description = description
        updated_fields.append("description")
    if category is not None:
        template.category = category
        updated_fields.append("category")
    if is_active is not None:
        template.is_active = is_active
        updated_fields.append("is_active")
    if steps is not None:
        steps_schema = []
        for step in steps:
            steps_schema.append({
                "id": step.get("id", ""),
                "name": step.get("name", ""),
                "type": step.get("type", "activity"),
                "description": step.get("description", ""),
                "icon": step.get("icon", ""),
                "mcp_tool": step.get("mcp_tool", ""),
                "config": step.get("config", {}),
                "timeout": step.get("timeout", "30s"),
                "retry_max": step.get("retry_max", 3),
                "on_fail": step.get("on_fail", "abort"),
            })
        template.steps_schema = steps_schema
        updated_fields.append("steps_schema")

    if not updated_fields:
        return {"error": "没有要更新的字段"}

    await template.asave(update_fields=updated_fields)

    return {
        "template_id": template.id,
        "name": template.name,
        "slug": template.slug,
        "updated_fields": updated_fields,
        "steps_count": len(template.steps_schema) if isinstance(template.steps_schema, list) else 0,
        "message": f"模板「{template.name}」已更新: {', '.join(updated_fields)}",
    }


async def list_workflow_templates(
    category: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    """列出工作流模板

    Args:
        category: 按分类筛选（可选：litigation/preservation/enforcement）
        is_active: 按启用状态筛选（可选）
    """
    from apps.workflow.models import WorkflowTemplate

    qs = WorkflowTemplate.objects.all()
    if category:
        qs = qs.filter(category=category)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)

    templates = [t async for t in qs.order_by("-created_at")]

    return [
        {
            "template_id": t.id,
            "name": t.name,
            "slug": t.slug,
            "category": t.category,
            "description": t.description,
            "is_active": t.is_active,
            "steps_count": len(t.steps_schema) if isinstance(t.steps_schema, list) else 0,
            "temporal_workflow_name": t.temporal_workflow_name,
        }
        for t in templates
    ]


async def get_workflow_template(template_id: int) -> dict[str, Any]:
    """获取工作流模板详情（包含完整步骤定义）

    Args:
        template_id: 模板 ID
    """
    from apps.workflow.models import WorkflowTemplate

    try:
        template = await WorkflowTemplate.objects.aget(pk=template_id)
    except WorkflowTemplate.DoesNotExist:
        return {"error": f"模板 #{template_id} 不存在"}

    return {
        "template_id": template.id,
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


async def delete_workflow_template(template_id: int) -> dict[str, Any]:
    """删除工作流模板

    Args:
        template_id: 模板 ID
    """
    from apps.workflow.models import WorkflowTemplate

    try:
        template = await WorkflowTemplate.objects.aget(pk=template_id)
    except WorkflowTemplate.DoesNotExist:
        return {"error": f"模板 #{template_id} 不存在"}

    name = template.name
    await template.adelete()
    return {"template_id": template_id, "message": f"模板「{name}」已删除"}


async def duplicate_workflow_template(template_id: int, new_name: str | None = None) -> dict[str, Any]:
    """复制工作流模板

    Args:
        template_id: 要复制的源模板 ID
        new_name: 新模板名称（可选，默认在原名后加 "(副本)"）
    """
    from django.utils.text import slugify as dj_slugify

    from apps.workflow.models import WorkflowTemplate

    try:
        source = await WorkflowTemplate.objects.aget(pk=template_id)
    except WorkflowTemplate.DoesNotExist:
        return {"error": f"模板 #{template_id} 不存在"}

    name = new_name or f"{source.name}(副本)"
    slug = dj_slugify(name, allow_unicode=True)
    base_slug = slug
    counter = 1
    while await WorkflowTemplate.objects.filter(slug=slug).aexists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    new_template = await WorkflowTemplate.objects.acreate(
        name=name,
        slug=slug,
        category=source.category,
        description=source.description,
        temporal_workflow_name=source.temporal_workflow_name,
        steps_schema=source.steps_schema,
        is_active=False,  # 默认不启用
    )

    return {
        "template_id": new_template.id,
        "name": new_template.name,
        "slug": new_template.slug,
        "source_template_id": template_id,
        "message": f"已从「{source.name}」复制为「{name}」",
    }


async def start_workflow_from_steps(
    case_id: int,
    steps: list[dict[str, Any]],
    template_name: str = "",
) -> dict[str, Any]:
    """从步骤列表直接创建模板并启动工作流（一步到位）

    这是给 AI Agent 最方便的接口：传入步骤列表，自动创建模板并启动。
    适合临时性工作流，不需要预先设计模板。

    Args:
        case_id: 案件 ID
        steps: 步骤列表（格式同 create_workflow_template）
        template_name: 模板名称（留空自动生成）

    Returns:
        包含 template_id、run_id、workflow_id 的信息
    """
    if not template_name:
        from django.utils import timezone
        template_name = f"临时工作流-{timezone.now().strftime('%Y%m%d%H%M%S')}"

    # 创建模板
    result = await create_workflow_template(
        name=template_name,
        steps=steps,
        category="litigation",
        description="AI Agent 自动创建的临时工作流",
    )
    if "error" in result:
        return result

    template_slug = result["slug"]

    # 启动工作流
    start_result = await start_workflow(template_slug, case_id)

    return {
        **start_result,
        "template_id": result["template_id"],
        "template_name": template_name,
    }
