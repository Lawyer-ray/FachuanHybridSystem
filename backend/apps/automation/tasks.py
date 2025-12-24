"""
Django-Q 后台任务
"""
import logging

logger = logging.getLogger("apps.automation")


def _get_scraper_map():
    """
    延迟加载爬虫类映射，避免循环导入
    """
    from .models import ScraperTaskType
    from .services.scraper.scrapers import (
        CourtDocumentScraper,
        CourtFilingScraper,
    )
    
    return {
        ScraperTaskType.COURT_DOCUMENT: CourtDocumentScraper,
        ScraperTaskType.COURT_FILING: CourtFilingScraper,
        # 未来扩展：
        # ScraperTaskType.JUSTICE_BUREAU: JusticeBureauScraper,
        # ScraperTaskType.POLICE: PoliceScraper,
    }


def check_stuck_tasks():
    """
    定时任务：检查卡住的任务
    """
    from apps.core.interfaces import ServiceLocator
    monitor_service = ServiceLocator.get_monitor_service()
    stuck_tasks = monitor_service.check_stuck_tasks(timeout_minutes=30)
    
    if stuck_tasks:
        # 发送告警
        monitor_service.send_alert(
            "任务超时告警",
            f"发现 {len(stuck_tasks)} 个任务执行超时（>30分钟）",
            level="warning"
        )


def execute_scraper_task(task_id: int, **kwargs):
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
    
    logger.info(f"开始执行爬虫任务 {task_id}: {task.get_task_type_display()} (优先级: {task.priority})")
    
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
            from django_q.tasks import async_task
            from django.utils import timezone
            from datetime import timedelta
            
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
                name=f"retry_task_{task.id}_{task.retry_count}"
            )
            
            logger.info(f"任务 {task_id} 将在 {delay_seconds} 秒后重试（第 {task.retry_count}/{task.max_retries} 次，指数退避）")
            logger.info(f"计划执行时间: {next_run_time}")


def process_pending_tasks():
    """
    处理所有待处理的任务
    
    在 qcluster 启动时调用，检查并执行所有 pending 状态的任务
    """
    from .models import ScraperTask, ScraperTaskStatus
    from django_q.tasks import async_task
    
    # 查找所有待处理的任务
    pending_tasks = ScraperTask.objects.filter(
        status=ScraperTaskStatus.PENDING
    ).order_by('priority', '-created_at')
    
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
                async_task(
                    "apps.automation.tasks.execute_scraper_task",
                    task.id
                )
                submitted += 1
                logger.info(f"任务 {task.id} 已提交到队列")
            else:
                logger.info(f"任务 {task.id} 尚未到执行时间，跳过")
        except Exception as e:
            logger.error(f"提交任务 {task.id} 失败: {e}")
    
    logger.info(f"共提交 {submitted}/{count} 个任务到队列")
    return submitted


def reset_running_tasks():
    """
    重置所有 running 状态的任务为 pending
    
    在 qcluster 启动时调用，处理上次异常退出导致的卡住任务
    """
    from .models import ScraperTask, ScraperTaskStatus
    
    # 查找所有 running 状态的任务
    running_tasks = ScraperTask.objects.filter(
        status=ScraperTaskStatus.RUNNING
    )
    
    count = running_tasks.count()
    if count == 0:
        logger.info("没有卡住的 running 任务")
        return 0
    
    logger.warning(f"发现 {count} 个卡住的 running 任务，重置为 pending...")
    
    # 重置为 pending
    running_tasks.update(status=ScraperTaskStatus.PENDING)
    
    logger.info(f"已重置 {count} 个任务")
    return count


def startup_check():
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
    
    return {
        "reset_count": reset_count,
        "pending_count": pending_count
    }


def execute_preservation_quote_task(quote_id: int):
    """
    执行财产保全询价任务（Django Q 异步任务）
    
    Args:
        quote_id: 询价任务 ID
    """
    import asyncio
    from .services.insurance.preservation_quote_service import PreservationQuoteService
    from .services.scraper.core.token_service import TokenService
    from .services.insurance.court_insurance_client import CourtInsuranceClient
    from .services.insurance.exceptions import TokenError
    from .models import PreservationQuote, QuoteStatus
    
    logger.info(f"🚀 开始执行询价任务 #{quote_id}")
    
    try:
        # 创建服务实例
        token_service = TokenService()
        insurance_client = CourtInsuranceClient(token_service)
        quote_service = PreservationQuoteService(token_service, insurance_client)
        
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
            quote.error_message = f"Token 错误: {str(e)}"
            quote.save(update_fields=["status", "error_message"])
        except Exception as update_error:
            logger.error(f"更新任务状态失败: {update_error}")
        
        # 不重新抛出异常，避免 Django Q 重试
        return {
            "quote_id": quote_id,
            "status": "failed",
            "error": "token_error",
            "message": str(e)
        }
        
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
