"""
Django-Q 后台任务 —— 爬虫与保全询价
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
    from ..models import ScraperTaskType
    from ..services.scraper.scrapers import CourtDocumentScraper

    CourtFilingScraper: type[Any] | None = None
    try:
        from plugins.court_automation.filing.playwright_filing.service import CourtZxfwFilingService

        CourtFilingScraper = CourtZxfwFilingService
    except ImportError:
        pass

    _scraper_map: dict[str, type[Any]] = {ScraperTaskType.COURT_DOCUMENT: CourtDocumentScraper}
    if CourtFilingScraper is not None:
        _scraper_map[ScraperTaskType.COURT_FILING] = CourtFilingScraper
    return _scraper_map


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

    from ..models import ScraperTask, ScraperTaskStatus

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
        else:
            # 重试耗尽必须落终态：否则任务停在 running，只能等 qcluster 重启时
            # reset_running_tasks 兜底转回 pending 再空转一轮
            task.status = ScraperTaskStatus.FAILED
            task.error_message = f"重试 {task.max_retries} 次后仍失败: {e}"
            task.save()
            logger.error("任务 %s 重试耗尽（%s/%s），标记为失败", task_id, task.retry_count, task.max_retries)


def process_pending_tasks() -> int:
    """
    处理所有待处理的任务

    在 qcluster 启动时调用，检查并执行所有 pending 状态的任务
    """
    from apps.core.tasking import submit_task

    from ..models import ScraperTask, ScraperTaskStatus

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
    from ..models import ScraperTask, ScraperTaskStatus

    running_tasks = ScraperTask.objects.filter(status=ScraperTaskStatus.RUNNING)

    count = int(running_tasks.count())
    if count == 0:
        logger.info("没有卡住的 running 任务")
        return 0

    logger.warning("发现 %s 个卡住的 running 任务，重置为 pending...", count)
    running_tasks.update(status=ScraperTaskStatus.PENDING)
    logger.info("已重置 %s 个任务", count)
    return count


def execute_preservation_quote_task(quote_id: int) -> dict[str, Any]:
    """
    执行财产保全询价任务（Django Q 异步任务）

    Args:
        quote_id: 询价任务 ID
    """
    from ..models import PreservationQuote, QuoteStatus

    try:
        from plugins.court_automation.preservation_quote.court_insurance_client import CourtInsuranceClient
        from plugins.court_automation.preservation_quote.exceptions import TokenError
        from plugins.court_automation.preservation_quote.service import PreservationQuoteService
    except ImportError:
        logger.error("court_automation plugin not installed — cannot execute preservation quote task")
        return {"quote_id": quote_id, "status": "error", "message": "plugin not installed"}
    from ..services.scraper.core.token_service import TokenServiceAdapter

    logger.info("🚀 开始执行询价任务 #%s", quote_id)

    # 记录可能在任务入队后被用户删除，此时静默退出即可
    if not PreservationQuote.objects.filter(id=quote_id).exists():
        logger.info("询价任务 #%s 已不存在（可能已被删除），跳过执行", quote_id)
        return {"quote_id": quote_id, "status": "skipped", "message": "记录已删除"}

    try:
        token_service = TokenServiceAdapter()  # type: ignore[valid-type, misc]
        insurance_client = CourtInsuranceClient(token_service)
        quote_service = PreservationQuoteService(
            token_service=token_service,
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
        # 记录可能在执行过程中被删除
        if "matching query does not exist" in str(e) or "DoesNotExist" in type(e).__name__:
            logger.info("询价任务 #%s 记录已不存在（可能已被删除），跳过", quote_id)
            return {"quote_id": quote_id, "status": "skipped", "message": "记录已删除"}

        logger.error("❌ 询价任务 #%s 执行失败: %s", quote_id, e, exc_info=True)

        try:
            quote = PreservationQuote.objects.get(id=quote_id)
            quote.status = QuoteStatus.FAILED
            quote.error_message = str(e)
            quote.save(update_fields=["status", "error_message"])
        except Exception as update_error:
            logger.error("更新任务状态失败: %s", update_error)

        raise
