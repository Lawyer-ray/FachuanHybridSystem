"""公众号发布 API"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from ninja import Router
from ninja.errors import HttpError

from apps.wechat_mp.models import PublishTask, PublishTaskStatus, WeChatAccount
from apps.wechat_mp.schemas import PublishTaskCreate, PublishTaskOut, WeChatAccountOut
from apps.wechat_mp.tasks import execute_publish_task

router = Router()

@router.get("/accounts", response=list[WeChatAccountOut])
def list_accounts(request: HttpRequest) -> Any:
    """获取公众号账号列表"""
    return WeChatAccount.objects.filter(is_active=True)

@router.post("/publish", response=PublishTaskOut)
def create_publish_task(request: HttpRequest, payload: PublishTaskCreate) -> Any:
    """创建发布任务"""
    # 验证账号存在
    try:
        account = WeChatAccount.objects.get(id=payload.account_id, is_active=True)
    except WeChatAccount.DoesNotExist:
        raise HttpError(400, "公众号账号不存在或已禁用")

    # 创建任务
    task = PublishTask.objects.create(
        account=account,
        title=payload.title,
        content_md=payload.content_md,
        save_as_draft=payload.save_as_draft,
        format_method=payload.format_method,
        created_by=request.user if request.user.is_authenticated else None,
    )

    # 提交异步任务
    from apps.core.tasking import submit_task

    queue_task_id = submit_task("apps.wechat_mp.tasks.execute_publish_task", task.id)
    task.queue_task_id = str(queue_task_id)
    task.save(update_fields=["queue_task_id"])

    return task

@router.get("/tasks", response=list[PublishTaskOut])
def list_tasks(request: HttpRequest) -> Any:
    """获取发布任务列表"""
    return PublishTask.objects.all().order_by("-created_at")[:100]

@router.get("/tasks/{task_id}", response=PublishTaskOut)
def get_task(request: HttpRequest, task_id: int) -> Any:
    """获取发布任务详情"""
    try:
        return PublishTask.objects.get(id=task_id)
    except PublishTask.DoesNotExist:
        raise HttpError(404, "任务不存在")
