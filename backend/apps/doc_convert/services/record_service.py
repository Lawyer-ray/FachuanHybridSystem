"""要素式转换历史记录服务：转换落库、分页查询、删除。"""

from __future__ import annotations

import logging
from typing import Any

from django.core.files.base import ContentFile
from django.core.paginator import Paginator

from apps.core.exceptions import NotFoundError
from apps.doc_convert.constants import MBID_DEFINITIONS
from apps.doc_convert.models import DocConvertRecord

logger = logging.getLogger("apps.doc_convert")

# mbid → 名称 的展示映射（constants 是静态清单，进程内缓存一份）
_MBID_NAME_MAP: dict[str, str] = {item["mbid"]: item["name"] for item in MBID_DEFINITIONS}


def mbid_display_name(mbid: str) -> str:
    """mbid → 文书类型展示名；未知 mbid 原样返回。"""
    return _MBID_NAME_MAP.get(mbid, mbid)


class DocConvertRecordService:
    """DocConvertRecord 的写入与查询（convert API 调 record_success/record_failure 落库）。"""

    PREVIEW_CHARS = 120

    def record_success(
        self,
        *,
        original_name: str,
        mbid: str,
        content: bytes,
        created_by: Any | None = None,
    ) -> DocConvertRecord:
        """转换成功：保存产物 docx 并建成功记录。"""
        record = DocConvertRecord.objects.create(
            original_name=original_name,
            mbid=mbid,
            mbid_name=mbid_display_name(mbid),
            status=DocConvertRecord.Status.SUCCESS,
            created_by=created_by,
        )
        # FileField.save 走 django storage（与 Media 规范的 default_storage 写入等价），
        # 物理文件名由 DatedUUIDPath 生成 UUID 防冲突
        stem = original_name.rsplit(".", 1)[0] if "." in original_name else original_name
        record.output_file.save(f"{stem}-要素式.docx", ContentFile(content), save=True)
        logger.info("要素式转换成功落库: record_id=%s, file=%s", record.id, original_name)
        return record

    def record_failure(
        self,
        *,
        original_name: str,
        mbid: str,
        error_message: str,
        created_by: Any | None = None,
    ) -> DocConvertRecord:
        """转换失败：记录原因，便于历史里回看失败原因。"""
        record = DocConvertRecord.objects.create(
            original_name=original_name,
            mbid=mbid,
            mbid_name=mbid_display_name(mbid),
            status=DocConvertRecord.Status.FAILED,
            error_message=error_message[:2000],
            created_by=created_by,
        )
        logger.info(
            "要素式转换失败落库: record_id=%s, file=%s, error=%s", record.id, original_name, error_message[:200]
        )
        return record

    def list_records(
        self,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        user: Any = None,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """分页列出转换记录（最新在前），返回 (记录列表, 总数, 总页数)。

        传入 user 时按属主过滤（superuser 豁免，安全审计 B-10）。
        """
        qs = DocConvertRecord.objects.all().order_by("-created_at")
        if user is not None and not getattr(user, "is_superuser", False):
            qs = qs.filter(created_by=user)
        if status:
            qs = qs.filter(status=status)
        safe_size = max(1, min(page_size, 50))
        paginator = Paginator(qs, safe_size)
        page_obj = paginator.get_page(page)
        items = [self._to_summary(record) for record in page_obj.object_list]
        return items, paginator.count, paginator.num_pages

    def get_record(self, record_id: int, user: Any = None) -> DocConvertRecord:
        qs = DocConvertRecord.objects.all()
        if user is not None and not getattr(user, "is_superuser", False):
            qs = qs.filter(created_by=user)
        try:
            return qs.get(pk=record_id)
        except DocConvertRecord.DoesNotExist:
            raise NotFoundError(
                message=f"转换记录不存在: ID={record_id}", code="DOC_CONVERT_RECORD_NOT_FOUND"
            ) from None

    def _to_summary(self, record: DocConvertRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "original_name": record.original_name,
            "mbid": record.mbid,
            "mbid_name": record.mbid_name,
            "status": record.status,
            "error_message": record.error_message or None,
            "has_file": bool(record.output_file),
            "created_at": record.created_at,
        }
