"""公众号文章发布异步任务（Django Q）"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.wechat_mp.models import PublishTask, PublishTaskStatus
from apps.wechat_mp.services.publisher import PublishError, WeChatPublisher

logger = logging.getLogger("apps.wechat_mp")


def execute_publish_task(task_id: int) -> None:
    """执行公众号文章发布任务。

    此函数作为 Django Q 的异步任务入口。
    """
    logger.info("开始执行公众号发布任务", extra={"task_id": task_id})

    try:
        task = PublishTask.objects.select_related("account").get(id=task_id)
    except PublishTask.DoesNotExist:
        logger.error("发布任务不存在", extra={"task_id": task_id})
        return

    task.status = PublishTaskStatus.LOGGING_IN
    task.started_at = timezone.now()
    task.error_message = ""
    task.save(update_fields=["status", "started_at", "error_message", "updated_at"])

    try:
        publisher = WeChatPublisher(task)
        result = publisher.publish()

        task.status = PublishTaskStatus.SUCCESS
        task.result_data = result
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "result_data", "finished_at", "updated_at"])

        logger.info("公众号发布任务完成", extra={"task_id": task_id, "result": result})

    except PublishError as exc:
        logger.error("公众号发布任务失败", extra={"task_id": task_id, "error": str(exc)})
        task.status = PublishTaskStatus.FAILED
        task.error_message = str(exc)
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error_message", "finished_at", "updated_at"])

    except Exception as exc:
        logger.error("公众号发布任务异常", extra={"task_id": task_id, "error": str(exc)}, exc_info=True)
        task.status = PublishTaskStatus.FAILED
        task.error_message = f"未知错误: {exc}"
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
