"""Module for scraper."""

from __future__ import annotations

import logging
from typing import Any, cast

logger = logging.getLogger("apps.automation")


def execute_scraper_task(task_id: int, **kwargs: Any) -> Any:
    if kwargs:
        logger.debug(f"忽略额外参数: {kwargs}")

    import os

    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

    from apps.automation.models import ScraperTask

    try:
        task = ScraperTask.objects.get(id=task_id)
    except ScraperTask.DoesNotExist:
        logger.error(f"任务不存在: {task_id}")
        return

    if not task.should_execute_now():
        logger.info(f"任务 {task_id} 尚未到执行时间,跳过")
        return

    logger.info(f"开始执行爬虫任务 {task_id}: {task.get_task_type_display()} (优先级: {task.priority})")  # type: ignore[attr-defined]

    from apps.automation.tasking import TaskRunner
    from apps.automation.tasking.handlers import ScraperTaskHandler

    handler = ScraperTaskHandler()
    runner = TaskRunner()
    try:
        result = runner.run(fn=lambda: handler.execute(task=task), task_name="execute_scraper_task", extra={})
        logger.info(f"任务 {task_id} 执行完成: {result}")
    except Exception as e:
        if task.can_retry():
            task.retry_count += 1
            task.status = "pending"
            task.save()
            handler.schedule_retry(task=task)
        else:
            logger.error(f"任务 {task_id} 执行异常: {e}", exc_info=True)


def process_pending_tasks() -> None:
    from django_q.tasks import async_task

    from apps.automation.models import ScraperTask, ScraperTaskStatus

    pending_tasks = ScraperTask.objects.filter(status=ScraperTaskStatus.PENDING).order_by("priority", "-created_at")

    count = pending_tasks.count()
    if count == 0:
        logger.info("没有待处理的任务")
        return 0  # type: ignore[return-value]

    logger.info(f"发现 {count} 个待处理任务,开始提交到队列...")

    submitted = 0
    for task in pending_tasks:
        try:
            if task.should_execute_now():
                async_task("apps.automation.tasks.execute_scraper_task", cast(int, task.id))
                submitted += 1
                logger.info(f"任务 {task.id} 已提交到队列")
            else:
                logger.info(f"任务 {task.id} 尚未到执行时间,跳过")
        except Exception as e:
            logger.error(f"提交任务 {task.id} 失败: {e}")

    logger.info(f"共提交 {submitted}/{count} 个任务到队列")
    return submitted  # type: ignore[return-value]


def reset_running_tasks() -> None:
    from apps.automation.models import ScraperTask, ScraperTaskStatus

    running_tasks = ScraperTask.objects.filter(status=ScraperTaskStatus.RUNNING)

    count = running_tasks.count()
    if count == 0:
        logger.info("没有卡住的 running 任务")
        return 0  # type: ignore[return-value]

    logger.warning(f"发现 {count} 个卡住的 running 任务,重置为 pending...")
    running_tasks.update(status=ScraperTaskStatus.PENDING)
    logger.info(f"已重置 {count} 个任务")
    return count  # type: ignore[return-value]


def startup_check() -> None:
    logger.info("=" * 60)
    logger.info("执行启动检查...")
    logger.info("=" * 60)

    reset_count = reset_running_tasks()  # type: ignore[func-returns-value]
    pending_count = process_pending_tasks()  # type: ignore[func-returns-value]

    logger.info("=" * 60)
    logger.info(f"启动检查完成: 重置 {reset_count} 个卡住任务, 提交 {pending_count} 个待处理任务")
    logger.info("=" * 60)

    return {"reset_count": reset_count, "pending_count": pending_count}  # type: ignore[return-value]
