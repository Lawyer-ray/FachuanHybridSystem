"""
文书识别任务管理服务

负责 DocumentRecognitionTask 的 CRUD 操作和案件搜索查询,
将 ORM 操作从 API 层下沉到 Service 层.
"""

import logging
from datetime import datetime
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, ValidationException

logger = logging.getLogger("apps.automation")


class DocumentRecognitionTaskService:
    """文书识别任务管理服务"""

    def create_task(self, *, file_path: str, original_filename: str) -> Any:
        """创建识别任务记录

        Args:
            file_path: 文件路径
            original_filename: 原始文件名

        Returns:
            DocumentRecognitionTask 实例
        """
        from apps.automation.models import DocumentRecognitionStatus, DocumentRecognitionTask

        task = DocumentRecognitionTask.objects.create(
            file_path=file_path,
            original_filename=original_filename,
            status=DocumentRecognitionStatus.PENDING,
        )
        logger.info("创建文书识别任务", extra={})
        return task

    def get_task(self, task_id: int, *, select_case: bool = False) -> Any:
        """获取识别任务

        Args:
            task_id: 任务 ID
            select_case: 是否预加载关联案件

        Returns:
            DocumentRecognitionTask 实例

        Raises:
            NotFoundError: 任务不存在
        """
        from apps.automation.models import DocumentRecognitionTask

        qs = DocumentRecognitionTask.objects.all()
        if select_case:
            qs = qs.select_related("case")
        try:
            return qs.get(id=task_id)
        except DocumentRecognitionTask.DoesNotExist:
            raise NotFoundError(message=_("任务不存在"), code="TASK_NOT_FOUND", errors={}) from None

    def update_task_info(
        self,
        task_id: int,
        *,
        case_number: str | None = None,
        key_time: str | None = None,
    ) -> Any:
        """更新识别任务信息(案号、关键时间)

        Args:
            task_id: 任务 ID
            case_number: 案号(None 表示不更新)
            key_time: 关键时间 ISO 格式字符串(None 表示不更新)

        Returns:
            更新后的 DocumentRecognitionTask 实例

        Raises:
            NotFoundError: 任务不存在
            ValidationException: 时间格式不正确
        """
        task = self.get_task(task_id)
        updated_fields: list[str] = []

        if case_number is not None:
            task.case_number = case_number if case_number else None
            updated_fields.append("case_number")

        if key_time is not None:
            if key_time:
                try:
                    task.key_time = datetime.fromisoformat(key_time.replace("Z", "+00:00"))
                except ValueError:
                    raise ValidationException(
                        message=_("时间格式不正确"),
                        code="INVALID_TIME_FORMAT",
                        errors={},
                    ) from None
            else:
                task.key_time = None
            updated_fields.append("key_time")

        if updated_fields:
            task.save(update_fields=updated_fields)
            logger.info(
                "识别信息已更新",
                extra={
                    "action": "update_task_info",
                    "task_id": task_id,
                    "updated_fields": updated_fields,
                    "case_number": task.case_number,
                    "key_time": str(task.key_time) if task.key_time else None,
                },
            )

        return task

    def search_cases_for_binding(self, *, search_term: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """搜索可绑定的案件

        支持按案件名称、案号、当事人搜索.

        Args:
            search_term: 搜索关键词
            limit: 返回数量限制

        Returns:
            案件信息字典列表
        """
        from apps.core.interfaces import ServiceLocator

        case_service = ServiceLocator.get_case_service()
        results = case_service.search_cases_for_binding_internal(search_term=search_term, limit=limit)

        logger.info(
            "案件搜索完成",
            extra={
                "action": "search_cases_for_binding",
                "query": search_term,
                "result_count": len(results),
            },
        )
        return results
