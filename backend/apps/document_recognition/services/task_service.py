"""
文书识别任务管理服务

负责 DocumentRecognitionTask 的 CRUD 操作和案件搜索查询,
将 ORM 操作从 API 层下沉到 Service 层.
"""

import logging
from datetime import datetime
from typing import Any

from apps.core.exceptions import NotFoundError, ValidationException

logger = logging.getLogger("apps.document_recognition")


class DocumentRecognitionTaskService:
    """文书识别任务管理服务"""

    def create_task(
        self,
        *,
        file_path: str,
        original_filename: str,
        source_court_sms_id: int | None = None,
        case_id: int | None = None,
        case_log_id: int | None = None,
        llm_model: str | None = None,
    ) -> Any:  # pragma: no cover
        """创建识别任务记录

        Args:
            file_path: 文件路径
            original_filename: 原始文件名
            source_court_sms_id: 来源法院短信 ID（管线模式：案件已由短信第一轮绑定）
            case_id: 管线预绑定的案件 ID（与 case_log_id 配套，跳过识别期匹配）
            case_log_id: 管线预绑定的案件日志 ID（日期确认的提醒锚点）
            llm_model: 用户指定的识别模型（None 走默认；识别完成后被实际模型覆盖）

        Returns:
            DocumentRecognitionTask 实例
        """
        from apps.document_recognition.models import DocumentRecognitionStatus, DocumentRecognitionTask

        task = DocumentRecognitionTask.objects.create(
            file_path=file_path,
            original_filename=original_filename,
            status=DocumentRecognitionStatus.PENDING,
            source_court_sms_id=source_court_sms_id,
            case_id=case_id,
            case_log_id=case_log_id,
            llm_model=llm_model,
            binding_success=True if case_log_id else None,
            binding_message="案件已由来源管线（法院短信）绑定" if case_log_id else None,
        )
        logger.info(
            "创建文书识别任务",
            extra={
                "source_court_sms_id": source_court_sms_id,
                "prebound_case_log_id": case_log_id,
                "llm_model": llm_model,
            },
        )
        return task

    def get_task(self, task_id: int, *, select_case: bool = False) -> Any:  # pragma: no cover
        """获取识别任务

        Args:
            task_id: 任务 ID
            select_case: 是否预加载关联案件

        Returns:
            DocumentRecognitionTask 实例

        Raises:
            NotFoundError: 任务不存在
        """
        from apps.document_recognition.models import DocumentRecognitionTask

        qs = DocumentRecognitionTask.objects.all()
        if select_case:
            qs = qs.select_related("case")
        try:
            return qs.get(id=task_id)
        except DocumentRecognitionTask.DoesNotExist:
            raise NotFoundError(message="任务不存在", code="TASK_NOT_FOUND", errors={}) from None

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
                        message="时间格式不正确",
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

    def pending_tasks(self, *, limit: int = 10) -> list[dict[str, Any]]:
        """待确认日期的识别任务（工作台侧栏「待确认任务」）

        Args:
            limit: 返回数量限制

        Returns:
            任务摘要字典列表
        """
        from django.db.models import Count

        from apps.document_recognition.models import (
            DateConfirmationStatus,
            DocumentRecognitionStatus,
            DocumentRecognitionTask,
        )

        tasks = (
            DocumentRecognitionTask.objects.filter(
                status=DocumentRecognitionStatus.SUCCESS,
                date_confirmation_status__in=[DateConfirmationStatus.PENDING, DateConfirmationStatus.PARTIAL],
            )
            .select_related("case")
            .annotate(candidate_count=Count("date_candidates"))
            .order_by("-created_at")[:limit]
        )
        return [
            {
                "task_id": t.id,
                "original_filename": t.original_filename,
                "document_type": t.document_type,
                "date_confirmation_status": t.date_confirmation_status,
                "candidate_count": t.candidate_count,
                "case_name": t.case.name if t.case_id else None,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]

    def search_cases_for_binding(
        self,
        *,
        search_term: str = "",
        limit: int = 20,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[dict[str, Any]]:
        """搜索可绑定的案件

        支持按案件名称、案号、当事人搜索.

        Args:
            search_term: 搜索关键词
            limit: 返回数量限制
            user: 当前用户（提供时按案件访问范围过滤）
            org_access: 组织访问上下文
            perm_open_access: 是否开放访问权限

        Returns:
            案件信息字典列表
        """
        from apps.core.interfaces import ServiceLocator

        case_service = ServiceLocator.get_case_service()
        results = case_service.search_cases_for_binding_internal(
            search_term=search_term,
            limit=limit,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

        logger.info(
            "案件搜索完成",
            extra={
                "action": "search_cases_for_binding",
                "query": search_term,
                "result_count": len(results),
            },
        )
        return results
