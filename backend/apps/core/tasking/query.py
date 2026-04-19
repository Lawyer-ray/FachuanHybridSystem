"""任务查询服务 — 封装 django_q.models 的 Task / OrmQ / Schedule 查询。

所有需要查询任务状态的代码应通过此模块，而非直接 import django_q.models。
这样未来迁移到 Celery 时，只需改这一个文件。
"""

from __future__ import annotations

from typing import Any


class TaskQueryService:
    """异步任务状态查询"""

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """查询任务状态。

        Returns:
            dict 包含: task_id, status (pending/running/success/failure/not_found),
            result, started_at, finished_at
        """
        from django_q.models import OrmQ, Task

        task = Task.objects.filter(id=task_id).first()
        if task:
            status = "success" if task.success else "failure"
            if task.started and not task.stopped:
                status = "running"
            return {
                "task_id": task_id,
                "status": status,
                "result": task.result,
                "started_at": task.started.isoformat() if task.started else None,
                "finished_at": task.stopped.isoformat() if task.stopped else None,
            }

        queued = OrmQ.objects.filter(key=task_id).exists()
        if queued:
            return {
                "task_id": task_id,
                "status": "pending",
                "result": None,
                "started_at": None,
                "finished_at": None,
            }

        return {
            "task_id": task_id,
            "status": "not_found",
            "result": None,
            "started_at": None,
            "finished_at": None,
        }

    def get_failed_task_info(self, task_id: str) -> dict[str, Any] | None:
        """获取失败任务的详细信息（用于错误回填）。

        Returns:
            dict 包含: task_id, stopped, result(error text), success；或 None
        """
        from django_q.models import Task

        q_task = Task.objects.filter(id=task_id).only("success", "stopped", "result").first()
        if q_task is None or q_task.stopped is None or q_task.success:
            return None
        return {
            "task_id": task_id,
            "stopped": q_task.stopped,
            "result": q_task.result,
            "success": q_task.success,
        }

    def get_task_by_id(self, task_id: str) -> Any:
        """获取原始 Task 对象（用于需要更多字段的场景）。

        注意：返回的是 django_q.models.Task 实例，未来迁移时需要调整调用方。
        """
        from django_q.models import Task

        return Task.objects.filter(id=task_id).first()

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        """Best-effort 取消任务。

        - 排队中的任务从队列移除
        - 运行中的任务无法强制终止，调用方应使用协作式取消
        """
        from django_q.models import OrmQ, Task

        queue_deleted, _ = OrmQ.objects.filter(key=task_id).delete()
        task = Task.objects.filter(id=task_id).first()

        running = bool(task and task.started and not task.stopped)
        finished = bool(task and task.stopped)
        return {
            "task_id": task_id,
            "queue_deleted": int(queue_deleted),
            "running": running,
            "finished": finished,
            "exists": task is not None,
        }


class ScheduleQueryService:
    """定时调度查询与管理"""

    def schedule_exists(self, name: str) -> bool:
        """检查指定名称的调度是否已存在"""
        from django_q.models import Schedule

        return Schedule.objects.filter(name=name).exists()  # type: ignore[no-any-return]

    def get_schedule_by_name(self, name: str) -> Any:
        """按名称获取调度对象"""
        from django_q.models import Schedule

        return Schedule.objects.filter(name=name).first()

    def delete_schedules(self, *, name: str | None = None, func: str | None = None) -> int:
        """删除匹配的调度，返回删除数量"""
        from django_q.models import Schedule

        qs = Schedule.objects.all()
        if name is not None:
            qs = qs.filter(name=name)
        if func is not None:
            qs = qs.filter(func=func)
        count = qs.count()
        qs.delete()
        return count  # type: ignore[no-any-return]

    def create_once_schedule(
        self,
        *,
        func: str,
        args: str = "",
        name: str,
        next_run: Any,
    ) -> Any:
        """创建一次性调度任务。

        Args:
            func: 任务函数的 dotted path
            args: 位置参数字符串（django_q Schedule 的 args 字段格式）
            name: 调度名称
            next_run: 下次执行时间 (datetime)

        Returns:
            创建的 Schedule 对象
        """
        from django_q.models import Schedule

        return Schedule.objects.create(
            func=func,
            args=args,
            name=name,
            schedule_type=Schedule.ONCE,
            next_run=next_run,
        )

    def create_interval_schedule(
        self,
        *,
        func: str,
        name: str,
        minutes: int,
        args: str = "",
        repeats: int = -1,
    ) -> str:
        """创建间隔执行的调度任务。

        Returns:
            task_id 字符串
        """
        from django_q.tasks import schedule

        return str(
            schedule(
                func,
                args,
                schedule_type="I",
                minutes=minutes,
                name=name,
                repeats=repeats,
            )
        )

    def create_monthly_schedule(
        self,
        *,
        func: str,
        name: str,
        next_run: Any,
        repeats: int = -1,
    ) -> Any:
        """创建每月执行的调度任务。

        Returns:
            创建的 Schedule 对象
        """
        from django_q.models import Schedule

        return Schedule.objects.create(
            name=name,
            func=func,
            schedule_type=Schedule.MONTHLY,
            repeats=repeats,
            next_run=next_run,
        )
