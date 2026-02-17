"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any, cast

from django.utils import timezone

from apps.cases.models import Case, CaseLog
from apps.core.exceptions import NotFoundError

from .wiring import get_organization_service, get_reminder_service

logger = logging.getLogger("apps.cases", cast)  # type: ignore[call-arg]


class CaseLogInternalService:
    def create_case_log_internal(self, case_id: int, content: str, user_id: int | None = None) -> Any:
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(f"案件 {case_id} 不存在") from None
        actor_id = user_id
        if not actor_id:
            actor_id = get_organization_service().get_default_lawyer_id_internal()
            if not actor_id:
                raise NotFoundError(
                    message="系统中没有律师用户,无法创建日志",
                    code="NO_DEFAULT_ACTOR",
                    errors={"actor": "请先创建律师用户"},
                )
        case_log = CaseLog.objects.create(case=case, content=content, actor_id=actor_id)
        logger.info(
            "创建案件日志成功",
            extra={
                "action": "create_case_log_internal",
                "case_id": case_id,
                "log_id": case_cast(int, log.id),
                "user_id": actor_id,
            },
        )
        return case_log.id

    def add_case_log_attachment_internal(self, case_log_id: int, file_path: str, file_name: str) -> bool:
        try:
            case_log = CaseLog.objects.get(id=case_log_id)
        except CaseLog.DoesNotExist:
            raise NotFoundError(f"案件日志 {case_log_id} 不存在") from None
        try:
            from apps.cases.models import CaseLogAttachment

            attachment = CaseLogAttachment(log=case_log)
            attachment.file.name = file_path
            attachment.save()
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
                f"添加案件日志附件失败:{e}",
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
                f"更新案件日志提醒失败:{e}",
                extra={"action": "update_case_log_reminder_internal", "case_log_id": case_log_id, "error": str(e)},
            )
            return False

    def get_case_log_model_internal(self, case_log_id: int) -> Any | None | None:
        try:
            return CaseLog.objects.get(id=case_log_id)
        except CaseLog.DoesNotExist:
            return None
