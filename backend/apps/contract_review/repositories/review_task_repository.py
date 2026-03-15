"""
ReviewTask Repository

封装 ReviewTask 模型的数据访问操作
"""

from pathlib import Path
from typing import Any
from uuid import UUID

from django.db.models import QuerySet

from apps.contract_review.models.review_task import ReviewTask


class ReviewTaskRepository:
    """合同审查任务数据访问层"""

    def create(self, **kwargs: Any) -> ReviewTask:
        """创建任务"""
        return ReviewTask.objects.create(**kwargs)

    def get_by_id(self, task_id: UUID) -> ReviewTask | None:
        """根据 ID 获取任务"""
        return ReviewTask.objects.filter(id=task_id).first()

    def get_by_id_required(self, task_id: UUID) -> ReviewTask:
        """根据 ID 获取任务，不存在则抛出异常"""
        return ReviewTask.objects.get(id=task_id)

    def update(self, task_id: UUID, **kwargs: Any) -> ReviewTask | None:
        """更新任务"""
        ReviewTask.objects.filter(id=task_id).update(**kwargs)
        return self.get_by_id(task_id)

    def filter_by_user(self, user: Any) -> QuerySet[ReviewTask]:
        """根据用户筛选任务"""
        return ReviewTask.objects.filter(user=user)

    def filter_by_status(self, status: str) -> QuerySet[ReviewTask]:
        """根据状态筛选任务"""
        return ReviewTask.objects.filter(status=status)

    def delete_by_id(self, task_id: UUID) -> tuple[int, dict[str, int]]:
        """根据 ID 删除任务"""
        return ReviewTask.objects.filter(id=task_id).delete()

    def delete_many(self, task_ids: list[UUID]) -> tuple[int, dict[str, int]]:
        """批量删除任务"""
        return ReviewTask.objects.filter(id__in=task_ids).delete()

    def exists(self, task_id: UUID) -> bool:
        """检查任务是否存在"""
        return ReviewTask.objects.filter(id=task_id).exists()
