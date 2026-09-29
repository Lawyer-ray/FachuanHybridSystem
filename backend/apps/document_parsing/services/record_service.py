"""解析记录查询服务（历史弹窗数据源）"""

from __future__ import annotations

import logging
from typing import Any

from django.core.paginator import Paginator

from apps.core.exceptions import NotFoundError
from apps.document_parsing.models import DocumentParsingTask

logger = logging.getLogger("apps.document_parsing")


class DocumentParsingRecordService:
    """DocumentParsingTask 的前台查询：分页列表 + 按 id 详情。"""

    PREVIEW_CHARS = 100

    def list_records(
        self,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """分页列出解析记录（最新在前），返回 (记录列表, 总数, 总页数)。"""
        qs = DocumentParsingTask.objects.all().order_by("-created_at")
        if status:
            qs = qs.filter(status=status)
        safe_size = max(1, min(page_size, 50))
        paginator = Paginator(qs, safe_size)
        page_obj = paginator.get_page(page)
        items = [self._to_summary(task) for task in page_obj.object_list]
        return items, paginator.count, paginator.num_pages

    def get_record(self, record_id: int) -> dict[str, Any]:
        """按 id 取单条记录全文（text/markdown/metadata）。"""
        try:
            task = DocumentParsingTask.objects.get(pk=record_id)
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
