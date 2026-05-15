"""Business logic services."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case, CaseLog
from apps.cases.utils import CASE_LOG_ALLOWED_EXTENSIONS, CASE_LOG_MAX_FILE_SIZE
from apps.core.exceptions import NotFoundError

from .wiring import get_organization_service, get_reminder_service

logger = logging.getLogger("apps.cases")


class CaseLogInternalService:
    def create_case_log_internal(self, case_id: int, content: str, user_id: int | None = None) -> Any:
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(_("案件 %(id)s 不存在") % {"id": case_id}) from None
        actor_id = user_id
        if not actor_id:
            actor_id = get_organization_service().get_default_lawyer_id()
            if not actor_id:
                raise NotFoundError(
                    message=_("系统中没有律师用户,无法创建日志"),
                    code="NO_DEFAULT_ACTOR",
                    errors={"actor": str(_("请先创建律师用户"))},
                )
        case_log = CaseLog.objects.create(case=case, content=content, actor_id=actor_id)
        logger.info(
            "创建案件日志成功",
            extra={
                "action": "create_case_log_internal",
                "case_id": case_id,
                "log_id": cast(int, case_log.id),  # type: ignore
                "user_id": actor_id,
            },
        )
        return case_log.id

    def add_case_log_attachment_internal(
        self,
        case_log_id: int,
        file_path: str,
        file_name: str,
        source_scene: str = "manual_log_upload",
        recommendation_file_name: str = "",
    ) -> bool:
        try:
            case_log = CaseLog.objects.get(id=case_log_id)
        except CaseLog.DoesNotExist:
            raise NotFoundError(_("案件日志 %(id)s 不存在") % {"id": case_log_id}) from None
        try:
            from apps.cases.models import CaseLogAttachment
            from apps.cases.services.log.case_log_attachment_storage_service import CaseLogAttachmentStorageService

            storage_service = CaseLogAttachmentStorageService()
            raw_file_path = str(file_path or "").strip()
            source_path = Path(raw_file_path).expanduser()
            if source_path.is_absolute() and source_path.exists():
                uploaded_file = SimpleUploadedFile(
                    name=file_name or source_path.name,
                    content=source_path.read_bytes(),
                )
                saved = storage_service.save_attachment(
                    uploaded_file,
                    case_id=case_log.case_id,
                    target_subdir="",
                    log=case_log,
                    allowed_extensions=list(CASE_LOG_ALLOWED_EXTENSIONS),
                    max_size_bytes=int(CASE_LOG_MAX_FILE_SIZE),
                    source_scene=source_scene,
                    recommendation_file_name=recommendation_file_name or file_name,
                    perm_open_access=True,
                )
                attachment = CaseLogAttachment.objects.create(
                    log=case_log,
                    file=saved.relative_file_path,
                    storage_root_type=saved.root_type,
                    subdir_path=saved.subdir_path,
                    relative_file_path=saved.relative_file_path,
                    original_filename=saved.original_filename,
                )
            else:
                relative_path = raw_file_path
                attachment = CaseLogAttachment.objects.create(
                    log=case_log,
                    file=relative_path,
                    storage_root_type="media",
                    subdir_path=relative_path.rsplit("/", 1)[0] if "/" in relative_path else "",
                    relative_file_path=relative_path,
                    original_filename=file_name or (relative_path.rsplit("/", 1)[-1] if relative_path else ""),
                )
                resolved = storage_service.resolve_attachment(attachment)
                if not resolved.exists:
                    attachment.delete()
                    raise FileNotFoundError(file_path)
            logger.info(
                "添加案件日志附件成功",
                extra={
                    "action": "add_case_log_attachment_internal",
                    "case_log_id": case_log_id,
                    "file_name": file_name,
                },
            )
            return True
        except Exception as e:
            logger.error(
                "添加案件日志附件失败: %s",
                e,
                extra={
                    "action": "add_case_log_attachment_internal",
                    "case_log_id": case_log_id,
                    "file_name": file_name,
                    "error": str(e),
                },
            )
            return False

    def update_case_log_reminder_internal(self, case_log_id: int, reminder_time: Any, reminder_type: str) -> bool:
        try:
            log = CaseLog.objects.filter(id=case_log_id).first()
            if not log:
                logger.warning(
                    "案件日志不存在", extra={"action": "update_case_log_reminder_internal", "case_log_id": case_log_id}
                )
                return False
            if reminder_time and timezone.is_naive(reminder_time):
                reminder_time = timezone.make_aware(reminder_time)
            reminder_service = get_reminder_service()
            result = reminder_service.create_reminder_internal(
                case_log_id=case_log_id, reminder_type=reminder_type, reminder_time=reminder_time
            )
            if result:
                logger.info(
                    "创建案件日志提醒成功",
                    extra={
                        "action": "update_case_log_reminder_internal",
                        "case_log_id": case_log_id,
                        "reminder_time": str(reminder_time),
                        "reminder_type": str(reminder_type),
                    },
                )
                return True
            logger.warning(
                "创建案件日志提醒失败",
                extra={"action": "update_case_log_reminder_internal", "case_log_id": case_log_id},
            )
            return False
        except Exception as e:
            logger.error(
                "更新案件日志提醒失败: %s",
                e,
                extra={"action": "update_case_log_reminder_internal", "case_log_id": case_log_id, "error": str(e)},
            )
            return False

    def get_case_log_model_internal(self, case_log_id: int) -> Any | None:
        try:
            return CaseLog.objects.get(id=case_log_id)
        except CaseLog.DoesNotExist:
            return None

