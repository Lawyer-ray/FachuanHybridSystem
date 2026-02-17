"""
Django-Q 后台任务
"""

import logging
from typing import Any

logger = logging.getLogger("apps.automation")


def _get_scraper_map() -> dict[str, type[Any]]:
    """
    延迟加载爬虫类映射，避免循环导入
    """
    from .models import ScraperTaskType
    from .services.scraper.scrapers import CourtDocumentScraper, CourtFilingScraper

    return {
        ScraperTaskType.COURT_DOCUMENT: CourtDocumentScraper,
        ScraperTaskType.COURT_FILING: CourtFilingScraper,
        # 未来扩展：
        # ScraperTaskType.JUSTICE_BUREAU: JusticeBureauScraper,
        # ScraperTaskType.POLICE: PoliceScraper,
    }


def check_stuck_tasks() -> None:
    """
    定时任务：检查卡住的任务
    """
    from apps.core.interfaces import ServiceLocator

    monitor_service = ServiceLocator.get_monitor_service()
    stuck_tasks = monitor_service.check_stuck_tasks(timeout_minutes=30)

    if stuck_tasks:
        # 发送告警
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
    # 忽略 Schedule 传递的额外参数
    if kwargs:
        logger.debug(f"忽略额外参数: {kwargs}")

    # 强制在同步环境中执行
    import os

    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

    # 导入模型
    from .models import ScraperTask

    try:
        task = ScraperTask.objects.get(id=task_id)
    except ScraperTask.DoesNotExist:
        logger.error(f"任务不存在: {task_id}")
        return

    # 检查是否应该执行
    if not task.should_execute_now():
        logger.info(f"任务 {task_id} 尚未到执行时间，跳过")
        return

    logger.info(f"开始执行爬虫任务 {task_id}: {task.get_task_type_display()} (优先级: {task.priority})")  # type: ignore[attr-defined]

    # 获取对应的爬虫类
    scraper_map = _get_scraper_map()
    scraper_class = scraper_map.get(task.task_type)

    if not scraper_class:
        error_msg = f"不支持的任务类型: {task.task_type}"
        logger.error(error_msg)
        task.status = "failed"
        task.error_message = error_msg
        task.save()
        return

    # 创建爬虫实例并执行
    try:
        scraper = scraper_class(task)
        result = scraper.execute()
        logger.info(f"任务 {task_id} 执行完成: {result}")
    except Exception as e:
        logger.error(f"任务 {task_id} 执行异常: {e}", exc_info=True)

        # 判断是否需要重试
        if task.can_retry():
            task.retry_count += 1
            task.status = "pending"  # 重置为待执行
            task.save()

            # 重新提交到队列（指数退避策略）
            from datetime import timedelta

            from django.utils import timezone

            # 指数退避: 1分钟 -> 2分钟 -> 4分钟，最多1小时
            delay_seconds = min(2 ** (task.retry_count - 1) * 60, 3600)

            # 计算下次执行时间
            next_run_time = timezone.now() + timedelta(seconds=delay_seconds)

            # 使用 schedule 创建定时任务
            from django_q.models import Schedule

            Schedule.objects.create(
                func="apps.automation.tasks.execute_scraper_task",
                args=str(task.id),
                schedule_type=Schedule.ONCE,
                next_run=next_run_time,
                name=f"retry_task_{task.id}_{task.retry_count}",
            )

            logger.info(
                f"任务 {task_id} 将在 {delay_seconds} 秒后重试（第 {task.retry_count}/{task.max_retries} 次，指数退避）"
            )
            logger.info(f"计划执行时间: {next_run_time}")


def process_pending_tasks() -> int:
    """
    处理所有待处理的任务

    在 qcluster 启动时调用，检查并执行所有 pending 状态的任务
    """
    from django_q.tasks import async_task

    from .models import ScraperTask, ScraperTaskStatus

    # 查找所有待处理的任务
    pending_tasks = ScraperTask.objects.filter(status=ScraperTaskStatus.PENDING).order_by("priority", "-created_at")

    count = pending_tasks.count()
    if count == 0:
        logger.info("没有待处理的任务")
        return 0

    logger.info(f"发现 {count} 个待处理任务，开始提交到队列...")

    submitted = 0
    for task in pending_tasks:
        try:
            # 检查是否应该执行
            if task.should_execute_now():
                async_task("apps.automation.tasks.execute_scraper_task", task.id)
                submitted += 1
                logger.info(f"任务 {task.id} 已提交到队列")
            else:
                logger.info(f"任务 {task.id} 尚未到执行时间，跳过")
        except Exception as e:
            logger.error(f"提交任务 {task.id} 失败: {e}")

    logger.info(f"共提交 {submitted}/{count} 个任务到队列")
    return submitted


def reset_running_tasks() -> int:
    """
    重置所有 running 状态的任务为 pending

    在 qcluster 启动时调用，处理上次异常退出导致的卡住任务
    """
    from .models import ScraperTask, ScraperTaskStatus

    # 查找所有 running 状态的任务
    running_tasks = ScraperTask.objects.filter(status=ScraperTaskStatus.RUNNING)

    count = running_tasks.count()
    if count == 0:
        logger.info("没有卡住的 running 任务")
        return 0

    logger.warning(f"发现 {count} 个卡住的 running 任务，重置为 pending...")

    # 重置为 pending
    running_tasks.update(status=ScraperTaskStatus.PENDING)

    logger.info(f"已重置 {count} 个任务")
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

    # 1. 重置卡住的任务
    reset_count = reset_running_tasks()

    # 2. 处理待处理的任务
    pending_count = process_pending_tasks()

    logger.info("=" * 60)
    logger.info(f"启动检查完成: 重置 {reset_count} 个卡住任务, 提交 {pending_count} 个待处理任务")
    logger.info("=" * 60)

    return {"reset_count": reset_count, "pending_count": pending_count}


def execute_document_recognition_task(task_id: int) -> None:
    """
    执行文书识别任务（Django Q 异步任务）

    Args:
        task_id: 识别任务 ID

    Requirements: 1.1, 1.2, 1.4, 5.1, 5.2, 5.3
    """
    from django.utils import timezone

    from .models import DocumentRecognitionStatus, DocumentRecognitionTask

    logger.info(f"🔍 开始执行文书识别任务 #{task_id}")

    try:
        task = DocumentRecognitionTask.objects.get(id=task_id)
    except DocumentRecognitionTask.DoesNotExist:
        logger.error(f"识别任务不存在: {task_id}")
        return

    # 更新状态为处理中
    task.status = DocumentRecognitionStatus.PROCESSING
    task.started_at = timezone.now()
    task.save(update_fields=["status", "started_at"])

    try:
        # 获取识别服务
        from apps.core.interfaces import ServiceLocator

        service = ServiceLocator.get_court_document_recognition_service()

        # 执行识别
        result = service.recognize_document(task.file_path, user=None)

        # 保存识别结果
        recognition = result.recognition
        task.document_type = recognition.document_type.value
        task.case_number = recognition.case_number
        task.key_time = recognition.key_time
        task.confidence = recognition.confidence
        task.extraction_method = recognition.extraction_method
        task.raw_text = recognition.raw_text[:10000] if recognition.raw_text else None  # 限制长度
        task.renamed_file_path = result.file_path

        # 保存绑定结果
        if result.binding:
            task.binding_success = result.binding.success
            task.binding_message = result.binding.message
            task.binding_error_code = result.binding.error_code
            if result.binding.case_id:
                task.case_id = result.binding.case_id  # type: ignore[attr-defined]
            if result.binding.case_log_id:
                task.case_log_id = result.binding.case_log_id  # type: ignore[attr-defined]

        task.status = DocumentRecognitionStatus.SUCCESS
        task.finished_at = timezone.now()
        task.save()

        # Requirements 1.1, 1.2: 绑定成功后发送通知
        if result.binding and result.binding.success:
            _send_recognition_notification(task, result)

        logger.info(f"✅ 文书识别任务 #{task_id} 完成: {task.document_type}")
        return {"task_id": task_id, "status": "success", "document_type": task.document_type}  # type: ignore[return-value]

    except Exception as e:
        logger.error(f"❌ 文书识别任务 #{task_id} 失败: {e}", exc_info=True)

        task.status = DocumentRecognitionStatus.FAILED
        task.error_message = str(e)
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error_message", "finished_at"])

        return {"task_id": task_id, "status": "failed", "error": str(e)}  # type: ignore[return-value]


def _send_recognition_notification(task: Any, result: Any) -> None:
    """
    发送文书识别通知（内部辅助函数）

    在绑定成功后调用，发送飞书群通知。
    通知失败不影响识别结果，仅记录错误。

    Args:
        task: DocumentRecognitionTask 实例
        result: RecognitionResponse 识别结果

    Requirements: 1.1, 1.4, 5.1, 5.2, 5.3
    """
    try:
        from .services.court_document_recognition.notification_service import DocumentRecognitionNotificationService

        notification_service = DocumentRecognitionNotificationService()

        # 使用重命名后的文件路径（如果有），否则使用原始路径
        # Requirements 3.3: 使用重命名后的文件路径进行推送
        file_path = task.renamed_file_path or task.file_path

        notification_result = notification_service.send_notification(
            case_id=result.binding.case_id,
            document_type=task.document_type,
            case_number=task.case_number,
            key_time=task.key_time,
            file_path=file_path,
            case_name=result.binding.case_name,
        )

        # Requirements 5.1, 5.2, 5.3: 更新任务通知状态
        task.notification_sent = notification_result.success
        task.notification_sent_at = notification_result.sent_at
        task.notification_file_sent = notification_result.file_sent

        if not notification_result.success:
            task.notification_error = notification_result.message
            logger.warning(f"文书识别通知发送失败: task_id={task.id}, error={notification_result.message}")
        else:
            logger.info(f"📨 文书识别通知发送成功: task_id={task.id}, file_sent={notification_result.file_sent}")

        task.save(
            update_fields=[
                "notification_sent",
                "notification_sent_at",
                "notification_file_sent",
                "notification_error",
            ]
        )

    except Exception as e:
        # Requirements 1.4: 通知失败不影响识别结果，仅记录错误
        logger.error(f"发送文书识别通知异常: task_id={task.id}, error={e}", exc_info=True)
        task.notification_sent = False
        task.notification_error = str(e)
        task.save(update_fields=["notification_sent", "notification_error"])


def execute_preservation_quote_task(quote_id: int) -> dict[str, Any]:
    """
    执行财产保全询价任务（Django Q 异步任务）

    Args:
        quote_id: 询价任务 ID
    """
    import asyncio

    from .models import PreservationQuote, QuoteStatus
    from .services.insurance.court_insurance_client import CourtInsuranceClient
    from .services.insurance.exceptions import TokenError
    from .services.insurance.preservation_quote_service import PreservationQuoteService
    from .services.scraper.core.token_service import TokenService

    logger.info(f"🚀 开始执行询价任务 #{quote_id}")

    try:
        # 创建服务实例
        token_service = TokenService()
        insurance_client = CourtInsuranceClient(token_service)  # type: ignore[arg-type]
        quote_service = PreservationQuoteService(
            token_service=token_service,  # type: ignore[arg-type]
            insurance_client=insurance_client,
        )

        # 执行询价任务（异步）
        result = asyncio.run(quote_service.execute_quote(quote_id))

        logger.info(f"✅ 询价任务 #{quote_id} 执行完成: {result}")
        return result

    except TokenError as e:
        # Token 错误：更新任务状态并记录友好的错误信息
        logger.error(f"❌ 询价任务 #{quote_id} Token 错误: {e}")

        try:
            quote = PreservationQuote.objects.get(id=quote_id)
            quote.status = QuoteStatus.FAILED
            quote.error_message = f"Token 错误: {e!s}"
            quote.save(update_fields=["status", "error_message"])
        except Exception as update_error:
            logger.error(f"更新任务状态失败: {update_error}")

        # 不重新抛出异常，避免 Django Q 重试
        return {"quote_id": quote_id, "status": "failed", "error": "token_error", "message": str(e)}

    except Exception as e:
        logger.error(f"❌ 询价任务 #{quote_id} 执行失败: {e}", exc_info=True)

        # 更新任务状态
        try:
            quote = PreservationQuote.objects.get(id=quote_id)
            quote.status = QuoteStatus.FAILED
            quote.error_message = str(e)
            quote.save(update_fields=["status", "error_message"])
        except Exception as update_error:
            logger.error(f"更新任务状态失败: {update_error}")

        raise
