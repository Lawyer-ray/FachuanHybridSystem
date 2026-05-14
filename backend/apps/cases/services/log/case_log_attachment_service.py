"""Business logic services."""

from __future__ import annotations

from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _

from apps.cases.models import CaseLogAttachment
from apps.cases.utils import CASE_LOG_ALLOWED_EXTENSIONS, CASE_LOG_MAX_FILE_SIZE, validate_case_log_attachment
from apps.core.exceptions import NotFoundError, ValidationException

from .case_log_attachment_storage_service import CaseLogAttachmentStorageService
from .case_log_query_service import CaseLogQueryService


class CaseLogAttachmentService:
    def __init__(
        self,
        query_service: CaseLogQueryService | None = None,
        storage_service: CaseLogAttachmentStorageService | None = None,
    ) -> None:
        self.query_service = query_service or CaseLogQueryService()
        self.storage_service = storage_service or CaseLogAttachmentStorageService()

    def upload_attachments(
        self,
        *,
        log_id: int,
        files: list[UploadedFile],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[CaseLogAttachment]:
        log = self.query_service.get_log_internal(log_id=log_id)

        if not perm_open_access:
            self.query_service.access_policy.ensure_access(
                case_id=log.case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=log.case,
                message=_("无权限上传附件"),
            )

        created = []
        for f in files:
            self._validate_attachment(f)
            saved = self.storage_service.save_attachment(
                f,
                case_id=log.case_id,
                target_subdir="案件日志附件",
                allowed_extensions=list(CASE_LOG_ALLOWED_EXTENSIONS),
                max_size_bytes=int(CASE_LOG_MAX_FILE_SIZE),
            )
            attachment = CaseLogAttachment.objects.create(
                log=log,
                file=saved.legacy_file_path,
                storage_root_type=saved.root_type,
                subdir_path=saved.subdir_path,
                relative_file_path=saved.relative_file_path,
                original_filename=saved.original_filename,
            )
            created.append(attachment)

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
            raise NotFoundError(_("附件 %(attachment_id)s 不存在") % {"attachment_id": attachment_id}) from None

        if not perm_open_access:
            self.query_service.access_policy.ensure_access(
                case_id=attachment.log.case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
                case=attachment.log.case,
                message=_("无权限删除此附件"),
            )

        attachment.delete()
        return {"success": True}

    def _validate_attachment(self, file: UploadedFile) -> None:
        name = getattr(file, "name", "")
        size = getattr(file, "size", 0)
        ok, error = validate_case_log_attachment(name, size)
        if not ok:
            raise ValidationException(_("附件校验失败"), errors={"file": error or _("附件校验失败")})
