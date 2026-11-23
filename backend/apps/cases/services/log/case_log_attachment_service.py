"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import DatabaseError, transaction

from apps.cases.models import CaseLogAttachment
from apps.cases.utils import validate_case_log_attachment
from apps.core.exceptions import NotFoundError, ValidationException

from .case_log_query_service import CaseLogQueryService

logger = logging.getLogger("apps.cases")


def _discard_written_files(attachments: list[CaseLogAttachment]) -> None:
    """回删本次已落盘的附件文件（存储层不随数据库事务回滚）。"""
    for attachment in attachments:
        # _committed=True 才代表 FileField 已经把内容写进存储；未提交的不能删，
        # 否则会按上传名删掉同名的既有文件。
        if not getattr(attachment.file, "_committed", False):
            continue
        try:
            attachment.file.delete(save=False)
        except (OSError, ValueError, AttributeError):
            logger.exception(
                "回删日志附件文件失败",
                extra={"attachment_id": attachment.pk, "file_path": attachment.file.name},
            )


class CaseLogAttachmentService:
    def __init__(self, query_service: CaseLogQueryService | None = None) -> None:
        self.query_service = query_service or CaseLogQueryService()

    @transaction.atomic
    def upload_attachments(
        self,
        *,
        log_id: int,
        files: list[UploadedFile],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[CaseLogAttachment]:  # pragma: no cover
        # S14-04（2026-11-23 二轮审计）：原实现边校验边逐条 create，第 N 个文件
        # 校验失败（或写盘失败）时前 N-1 条附件已入库、文件已写盘，接口却返回 4xx，
        # 留下「部分成功」的附件行与孤儿文件。现在先全校验再写，写入包在一个事务里，
        # 失败时回滚数据库行并回删本次已落盘的文件（FileField 在 INSERT 之前落盘，
        # 存储层不随事务回滚）。
        log = self.query_service.get_log_internal(log_id=log_id)

        if not perm_open_access:
            self.query_service.access_policy.ensure_access(
                case_id=log.case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=log.case,
                message="无权限上传附件",
            )

        for f in files:
            self._validate_attachment(f)

        created: list[CaseLogAttachment] = []
        attempted: list[CaseLogAttachment] = []
        try:
            for f in files:
                attachment = CaseLogAttachment(log=log, file=f)
                attempted.append(attachment)
                attachment.save()
                created.append(attachment)
        except (DatabaseError, OSError, ValueError):
            _discard_written_files(attempted)
            raise

        return created

    def delete_attachment(
        self,
        *,
        attachment_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, bool]:
        try:
            attachment = CaseLogAttachment.objects.select_related("log__case").get(id=attachment_id)
        except CaseLogAttachment.DoesNotExist:
            raise NotFoundError("附件 %(attachment_id)s 不存在" % {"attachment_id": attachment_id}) from None

        if not perm_open_access:
            self.query_service.access_policy.ensure_access(
                case_id=attachment.log.case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=attachment.log.case,
                message="无权限删除此附件",
            )

        if attachment.file:
            attachment.file.delete(save=False)

        attachment.delete()
        return {"success": True}

    def _validate_attachment(self, file: UploadedFile) -> None:
        name = getattr(file, "name", "")
        size = getattr(file, "size", 0)
        ok, error = validate_case_log_attachment(name, size)
        if not ok:
            raise ValidationException("附件校验失败", errors={"file": error or "附件校验失败"})
