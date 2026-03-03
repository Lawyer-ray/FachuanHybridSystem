"""Business logic services."""

from __future__ import annotations

from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _

from apps.cases.models import CaseLogAttachment
from apps.cases.utils import validate_case_log_attachment
from apps.core.exceptions import NotFoundError, ValidationException

from .case_log_query_service import CaseLogQueryService


class CaseLogAttachmentService:
    def __init__(self, query_service: CaseLogQueryService | None = None) -> None:
        self.query_service = query_service or CaseLogQueryService()

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
            created.append(CaseLogAttachment.objects.create(log=log, file=f))

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

        if attachment.file:
            attachment.file.delete(save=False)

        attachment.delete()
        return {"success": True}

    def _validate_attachment(self, file: UploadedFile) -> None:
        name = getattr(file, "name", "")
        size = getattr(file, "size", 0)
        ok, error = validate_case_log_attachment(name, size)
        if not ok:
            raise ValidationException(_("附件校验失败"), errors={"file": error or _("附件校验失败")})
