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


def task_ownership_q(user: Any | None) -> Any | None:
    """识别任务的行级归属口径（审计 P1 修复）。

    - is_admin / is_superuser：全量可见（管理员监管视角），返回 None 表示无需过滤；
    - 普通用户：仅可见自己创建的任务；存量 created_by 为 NULL 的旧任务
      （加归属字段前创建）保持所内可见，作为兼容旧数据的口径。
    非归属人非管理员按此过滤后取不到任务，上层以 NotFoundError / 404 拒绝。
    """
    from django.db.models import Q

    from apps.core.security.admin_access import is_admin_user

    if is_admin_user(user):
        return None
    return Q(created_by=user) | Q(created_by__isnull=True)


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
        created_by: Any | None = None,
    ) -> Any:  # pragma: no cover
        """创建识别任务记录

        Args:
            file_path: 文件路径
            original_filename: 原始文件名
            source_court_sms_id: 来源法院短信 ID（管线模式：案件已由短信第一轮绑定）
            case_id: 管线预绑定的案件 ID（与 case_log_id 配套，跳过识别期匹配）
            case_log_id: 管线预绑定的案件日志 ID（日期确认的提醒锚点）
            llm_model: 用户指定的识别模型（None 走默认；识别完成后被实际模型覆盖）
            created_by: 任务归属人（request 用户，行级归属过滤的依据）

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
            created_by=created_by,
            binding_success=True if case_log_id else None,
            binding_message="案件已由来源管线（法院短信）绑定" if case_log_id else None,
        )
        logger.info(
            "创建文书识别任务",
            extra={
                "source_court_sms_id": source_court_sms_id,
                "prebound_case_log_id": case_log_id,
                "llm_model": llm_model,
                "created_by_id": getattr(created_by, "id", None),
            },
        )
        return task

    def get_task(self, task_id: int, *, select_case: bool = False, user: Any | None = None) -> Any:  # pragma: no cover
        """获取识别任务（按归属口径过滤）

        Args:
            task_id: 任务 ID
            select_case: 是否预加载关联案件
            user: 当前用户（管理员见全量；普通用户见自己的任务与存量 NULL 任务）

        Returns:
            DocumentRecognitionTask 实例

        Raises:
            NotFoundError: 任务不存在或对当前用户不可见
        """
        from apps.document_recognition.models import DocumentRecognitionTask

        qs = DocumentRecognitionTask.objects.all()
        ownership = task_ownership_q(user)
        if ownership is not None:
            qs = qs.filter(ownership)
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
        user: Any | None = None,
    ) -> Any:
        """更新识别任务信息(案号、关键时间)

        Args:
            task_id: 任务 ID
            case_number: 案号(None 表示不更新)
            key_time: 关键时间 ISO 格式字符串(None 表示不更新)
            user: 当前用户（归属过滤，非归属人非管理员按任务不存在拒绝）

        Returns:
            更新后的 DocumentRecognitionTask 实例

        Raises:
            NotFoundError: 任务不存在或对当前用户不可见
            ValidationException: 时间格式不正确
        """
        task = self.get_task(task_id, user=user)
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

    def pending_tasks(self, *, limit: int = 10, user: Any | None = None) -> list[dict[str, Any]]:
        """待确认日期的识别任务（工作台侧栏「待确认任务」）

        Args:
            limit: 返回数量限制
            user: 当前用户（归属过滤：管理员全量；普通用户自己的任务 + 存量 NULL 任务）

        Returns:
            任务摘要字典列表
        """
        from django.db.models import Count

        from apps.document_recognition.models import (
            DateConfirmationStatus,
            DocumentRecognitionStatus,
            DocumentRecognitionTask,
        )

        qs = DocumentRecognitionTask.objects.filter(
            status=DocumentRecognitionStatus.SUCCESS,
            date_confirmation_status__in=[DateConfirmationStatus.PENDING, DateConfirmationStatus.PARTIAL],
        )
        ownership = task_ownership_q(user)
        if ownership is not None:
            qs = qs.filter(ownership)
        tasks = (
            qs.select_related("case").annotate(candidate_count=Count("date_candidates")).order_by("-created_at")[:limit]
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
