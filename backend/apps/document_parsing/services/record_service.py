"""解析记录查询服务（历史弹窗数据源）"""

from __future__ import annotations

import logging
from typing import Any

from django.core.paginator import Paginator

from apps.core.exceptions import NotFoundError
from apps.document_parsing.models import DocumentParsingTask

logger = logging.getLogger("apps.document_parsing")


def record_ownership_q(user: Any | None) -> Any | None:
    """解析记录的行级归属口径（审计 P1 修复）。

    - is_admin / is_superuser：全量可见（管理员监管视角），返回 None 表示无需过滤；
    - 普通用户：仅可见自己创建的记录；存量 created_by 为 NULL 的旧记录
      （加归属字段前创建）保持所内可见，作为兼容旧数据的口径。
    非归属人非管理员按此过滤后取不到记录，上层以 NotFoundError / 404 拒绝。
    """
    from django.db.models import Q

    from apps.core.security.admin_access import is_admin_user

    if is_admin_user(user):
        return None
    return Q(created_by=user) | Q(created_by__isnull=True)


class DocumentParsingRecordService:
    """DocumentParsingTask 的前台查询：分页列表 + 按 id 详情。"""

    PREVIEW_CHARS = 100

    def list_records(
        self,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        user: Any | None = None,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """分页列出解析记录（最新在前，按归属过滤），返回 (记录列表, 总数, 总页数)。"""
        qs = DocumentParsingTask.objects.all().order_by("-created_at")
        ownership = record_ownership_q(user)
        if ownership is not None:
            qs = qs.filter(ownership)
        if status:
            qs = qs.filter(status=status)
        safe_size = max(1, min(page_size, 50))
        paginator = Paginator(qs, safe_size)
        page_obj = paginator.get_page(page)
        items = [self._to_summary(task) for task in page_obj.object_list]
        return items, paginator.count, paginator.num_pages

    def get_record(self, record_id: int, *, user: Any | None = None) -> dict[str, Any]:
        """按 id 取单条记录全文（text/markdown/metadata，按归属过滤）。"""
        qs = DocumentParsingTask.objects.all()
        ownership = record_ownership_q(user)
        if ownership is not None:
            qs = qs.filter(ownership)
        try:
            task = qs.get(pk=record_id)
        except DocumentParsingTask.DoesNotExist:
            raise NotFoundError(message=f"解析记录不存在: ID={record_id}", code="PARSE_RECORD_NOT_FOUND") from None
        return {
            "id": task.id,
            "status": task.status,
            "file_name": task.file_name,
            "file_size": task.file_size,
            "backend_used": task.backend_used or None,
            "error_message": task.error_message or None,
            "text": task.text or "",
            "markdown": task.markdown or None,
            "metadata": task.metadata or {},
            "created_at": task.created_at,
            "completed_at": task.completed_at,
        }

    def _to_summary(self, task: DocumentParsingTask) -> dict[str, Any]:
        preview = (task.text or "").strip().replace("\n", " ")
        if len(preview) > self.PREVIEW_CHARS:
            preview = preview[: self.PREVIEW_CHARS] + "…"
        return {
            "id": task.id,
            "status": task.status,
            "file_name": task.file_name,
            "file_size": task.file_size,
            "backend_used": task.backend_used or None,
            "error_message": task.error_message or None,
            "text_preview": preview,
            "created_at": task.created_at,
            "completed_at": task.completed_at,
        }
