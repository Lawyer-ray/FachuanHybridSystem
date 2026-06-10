"""Data repository layer."""

from typing import Any

from apps.automation.models import CourtSMS
from apps.core.exceptions import NotFoundError


class CourtSMSRepository:
    def get_by_id(self, *, sms_id: int) -> Any:
        sms = CourtSMS.objects.filter(id=sms_id).first()
        if not sms:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}")
        return sms

    def get_by_id_or_none(self, *, sms_id: int) -> CourtSMS | None:  # pragma: no cover
        return CourtSMS.objects.filter(id=sms_id).first()

    def save(self, *, sms: CourtSMS) -> None:  # pragma: no cover
        sms.save()

    def refresh(self, *, sms: CourtSMS) -> CourtSMS:  # pragma: no cover
        return CourtSMS.objects.get(id=sms.pk)

    def set_error(self, *, sms: CourtSMS, message: str) -> None:
        sms.error_message = message
        sms.save(update_fields=["error_message", "updated_at"])

    def clear_error(self, *, sms: CourtSMS) -> None:
        sms.error_message = None
        sms.save(update_fields=["error_message", "updated_at"])

    def reset_retry_fields(self, *, sms: CourtSMS) -> None:
        sms.scraper_task = None
        sms.case = None
        sms.case_log = None
        sms.notification_results = None

    def set_status(self, *, sms: CourtSMS, status: str, error_message: str | None = None) -> None:
        sms.status = status
        sms.error_message = error_message
        sms.save(update_fields=["status", "error_message", "updated_at"])
