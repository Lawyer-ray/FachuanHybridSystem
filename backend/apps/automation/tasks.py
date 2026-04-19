"""
Django-Q 后台任务
"""

import asyncio
import logging
from collections.abc import Coroutine
from concurrent.futures import Future
from threading import Thread
from typing import Any

logger = logging.getLogger("apps.automation")


def _run_coroutine_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """
    在同步上下文中安全执行协程。

    Django-Q worker 某些场景下会存在运行中的事件循环，此时不能直接调用 asyncio.run。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    future: Future[T] = Future()

    def _runner() -> None:
        try:
            result = asyncio.run(coro)
        except Exception as exc:
            future.set_exception(exc)
        else:
            future.set_result(result)

    thread = Thread(target=_runner, name="automation-quote-task-runner", daemon=True)
    thread.start()
    thread.join()
    return future.result()


def _get_scraper_map() -> dict[str, type[Any]]:
    """
    延迟加载爬虫类映射，避免循环导入
    """
    from .models import ScraperTaskType
    from .services.scraper.scrapers import CourtDocumentScraper, CourtFilingScraper

    return {
        ScraperTaskType.COURT_DOCUMENT: CourtDocumentScraper,
        ScraperTaskType.COURT_FILING: CourtFilingScraper,
    }


def check_stuck_tasks() -> None:
    """
    定时任务：检查卡住的任务
    """
    from apps.core.interfaces import ServiceLocator

    monitor_service = ServiceLocator.get_monitor_service()
    stuck_tasks = monitor_service.check_stuck_tasks(timeout_minutes=30)

    if stuck_tasks:
        monitor_service.send_alert(
            "任务超时告警", f"发现 {len(stuck_tasks)} 个任务执行超时（>30分钟）", level="warning"
        )


def execute_scraper_task(task_id: int, **kwargs: Any) -> None:
    """
    执行爬虫任务（同步版本，用于 Django-Q）

    Args:
        task_id: 任务 ID
        **kwargs: 接受 Django-Q Schedule 传递的额外参数
    """
    if kwargs:
        logger.debug("忽略额外参数: %s", kwargs)

    import os

    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

    from .models import ScraperTask

    try:
        task = ScraperTask.objects.get(id=task_id)
    except ScraperTask.DoesNotExist:
        logger.error("任务不存在: %s", task_id)
        return

    if not task.should_execute_now():
        logger.info("任务 %s 尚未到执行时间，跳过", task_id)
        return

    logger.info("开始执行爬虫任务 %s: %s (优先级: %s)", task_id, task.get_task_type_display(), task.priority)

    scraper_map = _get_scraper_map()
    scraper_class = scraper_map.get(task.task_type)

    if not scraper_class:
        error_msg = f"不支持的任务类型: {task.task_type}"
        logger.error(error_msg)
        task.status = "failed"
        task.error_message = error_msg
        task.save()
        return

    try:
        scraper = scraper_class(task)
        result = scraper.execute()
        logger.info("任务 %s 执行完成: %s", task_id, result)
    except Exception as e:
        logger.error("任务 %s 执行异常: %s", task_id, e, exc_info=True)

        if task.can_retry():
            task.retry_count += 1
            task.status = "pending"
            task.save()

            from datetime import timedelta

            from django.utils import timezone
            from apps.core.tasking import ScheduleQueryService

            delay_seconds = min(2 ** (task.retry_count - 1) * 60, 3600)
            next_run_time = timezone.now() + timedelta(seconds=delay_seconds)

            ScheduleQueryService().create_once_schedule(
                func="apps.automation.tasks.execute_scraper_task",
                args=str(task.id),
                name=f"retry_task_{task.id}_{task.retry_count}",
                next_run=next_run_time,
            )

            logger.info(
                "任务 %s 将在 %s 秒后重试（第 %s/%s 次，指数退避），计划执行时间: %s",
                task_id,
                delay_seconds,
                task.retry_count,
                task.max_retries,
                next_run_time,
            )


def process_pending_tasks() -> int:
    """
    处理所有待处理的任务

    在 qcluster 启动时调用，检查并执行所有 pending 状态的任务
    """
    from apps.core.tasking import submit_task

    from .models import ScraperTask, ScraperTaskStatus

    pending_tasks = ScraperTask.objects.filter(status=ScraperTaskStatus.PENDING).order_by("priority", "-created_at")

    count = pending_tasks.count()
    if count == 0:
        logger.info("没有待处理的任务")
        return 0

    logger.info("发现 %s 个待处理任务，开始提交到队列...", count)

    submitted = 0
    for task in pending_tasks:
        try:
            if task.should_execute_now():
                submit_task("apps.automation.tasks.execute_scraper_task", task.id)
                submitted += 1
                logger.info("任务 %s 已提交到队列", task.id)
            else:
                logger.info("任务 %s 尚未到执行时间，跳过", task.id)
        except Exception as e:
            logger.error("提交任务 %s 失败: %s", task.id, e)

    logger.info("共提交 %s/%s 个任务到队列", submitted, count)
    return submitted


def reset_running_tasks() -> int:
    """
    重置所有 running 状态的任务为 pending

    在 qcluster 启动时调用，处理上次异常退出导致的卡住任务
    """
    from .models import ScraperTask, ScraperTaskStatus

    running_tasks = ScraperTask.objects.filter(status=ScraperTaskStatus.RUNNING)

    count = int(running_tasks.count())
    if count == 0:
        logger.info("没有卡住的 running 任务")
        return 0

    logger.warning("发现 %s 个卡住的 running 任务，重置为 pending...", count)
    running_tasks.update(status=ScraperTaskStatus.PENDING)
    logger.info("已重置 %s 个任务", count)
    return count


def startup_check() -> dict[str, int]:
    """
    启动时检查

    在 qcluster 启动时调用，执行以下操作：
    1. 重置卡住的 running 任务
    2. 处理所有待处理的任务
    """
    logger.info("=" * 60)
    logger.info("执行启动检查...")
    logger.info("=" * 60)

    reset_count = reset_running_tasks()
    pending_count = process_pending_tasks()

    logger.info("=" * 60)
    logger.info("启动检查完成: 重置 %s 个卡住任务, 提交 %s 个待处理任务", reset_count, pending_count)
    logger.info("=" * 60)

    return {"reset_count": reset_count, "pending_count": pending_count}


def execute_preservation_quote_task(quote_id: int) -> dict[str, Any]:
    """
    执行财产保全询价任务（Django Q 异步任务）

    Args:
        quote_id: 询价任务 ID
    """
    from .models import PreservationQuote, QuoteStatus
    from .services.insurance.court_insurance_client import CourtInsuranceClient
    from .services.insurance.exceptions import TokenError
    from .services.insurance.preservation_quote_service import PreservationQuoteService
    from .services.scraper.core.token_service import TokenService

    logger.info("🚀 开始执行询价任务 #%s", quote_id)

    try:
        token_service = TokenService()
        insurance_client = CourtInsuranceClient(token_service)  # type: ignore[arg-type]
        quote_service = PreservationQuoteService(
            token_service=token_service,  # type: ignore[arg-type]
            insurance_client=insurance_client,
        )

        raw_result = _run_coroutine_sync(quote_service.execute_quote(quote_id))
        result: dict[str, Any] = raw_result

        logger.info("✅ 询价任务 #%s 执行完成: %s", quote_id, result)
        return result

    except TokenError as e:
        logger.error("❌ 询价任务 #%s Token 错误: %s", quote_id, e)

        try:
            quote = PreservationQuote.objects.get(id=quote_id)
            quote.status = QuoteStatus.FAILED
            quote.error_message = f"Token 错误: {e!s}"
            quote.save(update_fields=["status", "error_message"])
        except Exception as update_error:
            logger.error("更新任务状态失败: %s", update_error)

        return {"quote_id": quote_id, "status": "failed", "error": "token_error", "message": str(e)}

    except Exception as e:
        logger.error("❌ 询价任务 #%s 执行失败: %s", quote_id, e, exc_info=True)

        try:
            quote = PreservationQuote.objects.get(id=quote_id)
            quote.status = QuoteStatus.FAILED
            quote.error_message = str(e)
            quote.save(update_fields=["status", "error_message"])
        except Exception as update_error:
            logger.error("更新任务状态失败: %s", update_error)

        raise
