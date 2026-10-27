"""任务队列 API — 暴露 django-q2 任务状态"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

from apps.core.security.admin_access import ensure_admin_request

router = Router()


def _fmt_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class QueuedTaskOut(Schema):
    id: str
    name: str
    func: str
    group: str | None = None
    created_at: str | None = None


class TaskOut(Schema):
    id: str
    name: str
    func: str
    group: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration: float | None = None
    success: bool
    result: str | None = None


class ScheduleOut(Schema):
    id: int
    name: str
    func: str
    schedule_type: str
    repeats: int
    next_run: str | None = None
    last_run: str | None = None
    success: bool | None = None


@router.get("/queued", response=list[QueuedTaskOut])
def list_queued(request: HttpRequest) -> Any:  # pragma: no cover
    """获取排队中的任务"""
    ensure_admin_request(request, message="无权限访问任务队列", code="PERMISSION_DENIED")

    from apps.core.tasking.task_queue_query import list_queued as _list_queued

    items = _list_queued()
    return [
        QueuedTaskOut(
            id=str(item.key),
            name=item.task().get("name", ""),
            func=item.task().get("func", ""),
            group=item.task().get("group", ""),
            created_at=_fmt_dt(item.lock),
        )
        for item in items
    ]


@router.get("/completed", response=list[TaskOut])
def list_completed(request: HttpRequest) -> Any:  # pragma: no cover
    """获取已完成的成功任务"""
    ensure_admin_request(request, message="无权限访问任务队列", code="PERMISSION_DENIED")

    from apps.core.tasking.task_queue_query import list_completed as _list_completed

    tasks = _list_completed()
    return [
        TaskOut(
            id=str(t.id),
            name=t.name or "",
            func=t.func or "",
            group=t.group,
            started_at=_fmt_dt(t.started),
            finished_at=_fmt_dt(t.stopped),
            duration=t.time_taken(),
            success=True,
            result=str(t.result)[:200] if t.result else None,
        )
        for t in tasks
    ]


@router.get("/failed", response=list[TaskOut])
def list_failed(request: HttpRequest) -> Any:  # pragma: no cover
    """获取失败的任务"""
    ensure_admin_request(request, message="无权限访问任务队列", code="PERMISSION_DENIED")

    from apps.core.tasking.task_queue_query import list_failed as _list_failed

    tasks = _list_failed()
    return [
        TaskOut(
            id=str(t.id),
            name=t.name or "",
            func=t.func or "",
            group=t.group,
            started_at=_fmt_dt(t.started),
            finished_at=_fmt_dt(t.stopped),
            duration=t.time_taken(),
            success=False,
            result=str(t.result)[:500] if t.result else None,
        )
        for t in tasks
    ]


@router.get("/scheduled", response=list[ScheduleOut])
def list_scheduled(request: HttpRequest) -> Any:  # pragma: no cover
    """获取定时调度任务"""
    ensure_admin_request(request, message="无权限访问任务队列", code="PERMISSION_DENIED")

    from apps.core.tasking.task_queue_query import SCHEDULE_TYPE_LABELS, get_last_run_times
    from apps.core.tasking.task_queue_query import list_scheduled as _list_scheduled

    schedules = _list_scheduled()

    # 单次查询批量预取各调度的最后运行时间
    names = [s.name for s in schedules if s.name]
    last_runs = get_last_run_times(names) if names else {}

    return [
        ScheduleOut(
            id=s.id,
            name=s.name or "",
            func=s.func,
            schedule_type=SCHEDULE_TYPE_LABELS.get(s.schedule_type, str(s.schedule_type)),
            repeats=s.repeats,
            next_run=_fmt_dt(s.next_run),
            last_run=_fmt_dt(last_runs.get(s.name)),
        )
        for s in schedules
    ]


@router.delete("/tasks/{task_id}")
def delete_task(request: HttpRequest, task_id: str) -> dict[str, Any]:  # pragma: no cover
    """删除已完成或失败的任务"""
    ensure_admin_request(request, message="无权限访问任务队列", code="PERMISSION_DENIED")

    from apps.core.tasking.task_queue_query import delete_task as _delete_task

    deleted = _delete_task(task_id)
    return {"deleted": deleted}


@router.delete("/schedules/{schedule_id}")
def delete_schedule(request: HttpRequest, schedule_id: int) -> dict[str, Any]:  # pragma: no cover
    """删除定时调度"""
    ensure_admin_request(request, message="无权限访问任务队列", code="PERMISSION_DENIED")

    from apps.core.tasking.task_queue_query import delete_schedule as _delete_schedule

    deleted = _delete_schedule(schedule_id)
    return {"deleted": deleted}


@router.post("/tasks/{task_id}/resubmit")
def resubmit_task(request: HttpRequest, task_id: str) -> dict[str, Any]:  # pragma: no cover
    """重新提交失败的任务"""
    ensure_admin_request(request, message="无权限访问任务队列", code="PERMISSION_DENIED")

    from apps.core.tasking.task_queue_query import resubmit_task as _resubmit_task

    new_id = _resubmit_task(task_id)
    if new_id is None:
        return {"error": "任务不存在"}
    return {"new_task_id": new_id}


class ClusterStatusOut(Schema):
    """集群活性聚合（设置页·系统状态）。"""

    clusters: int | None = None
    queue_depth: int = 0
    succeeded_today: int = 0
    failed_today: int = 0
    last_success_at: str | None = None
    last_failed_at: str | None = None
    broker_error: str | None = None


@router.get("/cluster-status", response=ClusterStatusOut)
def get_cluster_status(request: HttpRequest) -> Any:  # pragma: no cover
    """Django-Q 集群活性聚合。

    与上面的任务明细端点不同，这里**不做** ``ensure_admin_request``：返回的是
    聚合数字（集群心跳数 / 队列深度 / 今日成败计数），不含任务载荷；律师在
    设置页看系统状态也需要它，路由层挂的 JWTOrSessionAuth 已够。
    """
    from apps.core.tasking.task_queue_query import cluster_status

    data = cluster_status()
    return ClusterStatusOut(
        clusters=data["clusters"],
        queue_depth=data["queue_depth"],
        succeeded_today=data["succeeded_today"],
        failed_today=data["failed_today"],
        last_success_at=_fmt_dt(data["last_success_at"]),
        last_failed_at=_fmt_dt(data["last_failed_at"]),
        broker_error=data["broker_error"],
    )
