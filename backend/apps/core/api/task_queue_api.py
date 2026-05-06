"""任务队列 API — 暴露 django-q2 任务状态"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

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
def list_queued(request: HttpRequest) -> Any:
    """获取排队中的任务"""
    from django_q.models import OrmQ

    items = OrmQ.objects.all().order_by("-lock")[:200]
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
def list_completed(request: HttpRequest) -> Any:
    """获取已完成的成功任务"""
    from django_q.models import Task

    tasks = Task.objects.filter(success=True).order_by("-stopped")[:200]
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
def list_failed(request: HttpRequest) -> Any:
    """获取失败的任务"""
    from django_q.models import Task

    tasks = Task.objects.filter(success=False).order_by("-stopped")[:200]
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
def list_scheduled(request: HttpRequest) -> Any:
    """获取定时调度任务"""
    from django_q.models import Schedule, Success

    schedules = Schedule.objects.all().order_by("next_run")[:200]
    type_labels = {
        Schedule.ONCE: "单次",
        Schedule.MINUTES: "分钟间隔",
        Schedule.HOURLY: "小时",
        Schedule.DAILY: "每天",
        Schedule.WEEKLY: "每周",
        Schedule.MONTHLY: "每月",
        Schedule.QUARTERLY: "每季度",
        Schedule.YEARLY: "每年",
    }

    # Pre-fetch last run times per schedule name
    names = [s.name for s in schedules if s.name]
    last_runs: dict[str, datetime | None] = {}
    if names:
        for name in names:
            task = Success.objects.filter(name=name).order_by("-stopped").first()
            last_runs[name] = task.stopped if task else None

    return [
        ScheduleOut(
            id=s.id,
            name=s.name or "",
            func=s.func,
            schedule_type=type_labels.get(s.schedule_type, str(s.schedule_type)),
            repeats=s.repeats,
            next_run=_fmt_dt(s.next_run),
            last_run=_fmt_dt(last_runs.get(s.name)),
        )
        for s in schedules
    ]


@router.delete("/tasks/{task_id}")
def delete_task(request: HttpRequest, task_id: str) -> dict[str, Any]:
    """删除已完成或失败的任务"""
    from django_q.models import Task

    deleted, _ = Task.objects.filter(id=task_id).delete()
    return {"deleted": deleted}


@router.delete("/schedules/{schedule_id}")
def delete_schedule(request: HttpRequest, schedule_id: int) -> dict[str, Any]:
    """删除定时调度"""
    from django_q.models import Schedule

    deleted, _ = Schedule.objects.filter(id=schedule_id).delete()
    return {"deleted": deleted}


@router.post("/tasks/{task_id}/resubmit")
def resubmit_task(request: HttpRequest, task_id: str) -> dict[str, Any]:
    """重新提交失败的任务"""
    from django_q.models import Task
    from django_q.tasks import async_task

    task = Task.objects.filter(id=task_id).first()
    if not task:
        return {"error": "任务不存在"}

    new_id = async_task(task.func, *task.args or [], **task.kwargs or {}, group=task.group, name=task.name)
    return {"new_task_id": str(new_id)}
