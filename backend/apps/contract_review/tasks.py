"""
合同审查异步任务

包含审查处理和文件清理任务
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.contract_review.models.review_task import ReviewTask, TaskStatus
from apps.core.services.storage_service import delete_media_file

logger = logging.getLogger(__name__)


def process_review(task_id_str: str) -> None:  # pragma: no cover
    """
    异步执行审查流水线（由 Django-Q2 调用）

    此函数作为入口点，调用 ReviewService 中的处理逻辑
    """
    from apps.contract_review.services.review.review_service import process_review as _process_review

    _process_review(task_id_str)


def cleanup_old_files(days: int = 30) -> dict[str, int]:  # pragma: no cover
    """
    清理指定天数前的上传文件和输出文件

    Args:
        days: 保留天数，默认 30 天

    Returns:
        清理结果统计 {"upload_files": x, "output_files": y}
    """
    from apps.contract_review.repositories.review_task_repository import ReviewTaskRepository

    repository = ReviewTaskRepository()
    cutoff_date = timezone.now() - timedelta(days=days)

    # 查找需要清理的任务
    old_tasks = ReviewTask.objects.filter(created_at__lt=cutoff_date).exclude(status__in=[TaskStatus.PROCESSING])

    upload_count = 0
    output_count = 0
    deleted_count = 0

    for task in old_tasks:
        # 删除上传文件（落库为 media 相对路径，存量绝对路径同样兼容）
        if task.original_file and delete_media_file(task.original_file):
            upload_count += 1

        # 删除输出文件
        if task.output_file and delete_media_file(task.output_file):
            output_count += 1

        # 删除数据库记录
        try:
            repository.delete_by_id(task.id)
            deleted_count += 1
        except (OSError, ValueError) as e:
            logger.warning("删除任务记录失败: %s - %s", task.id, e)

    logger.info("文件清理完成: 上传文件 %d, 输出文件 %d, 任务记录 %d", upload_count, output_count, deleted_count)
    return {"upload_files": upload_count, "output_files": output_count, "tasks": deleted_count}
