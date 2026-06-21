"""CourtSMS 去重服务。"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.core.exceptions import FieldDoesNotExist, FieldError
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSType

logger = logging.getLogger("apps.automation")


@dataclass(frozen=True)
class CourtSMSDedupIdentity:
    """CourtSMS 事件身份。"""

    event_id: str | None
    event_key: str | None
    canonical_payload: str | None
    uses_fallback: bool = False


@dataclass(frozen=True)
class CourtSMSDedupResult:
    """CourtSMS 去重创建结果。"""

    sms: CourtSMS
    created: bool
    identity: CourtSMSDedupIdentity


class CourtSMSDedupService:
    """统一处理 CourtSMS 的事件键生成与幂等创建。"""

    def build_existing_sms_result(self, sms: CourtSMS, file_path: str) -> dict[str, Any]:
        """构造重复命中时的统一返回结构。"""
        notification_sent = False
        if sms.notification_results and isinstance(sms.notification_results, dict):
            notification_sent = any(
                v.get("success", False) for v in sms.notification_results.values() if isinstance(v, dict)
            )
        if not notification_sent and sms.feishu_sent_at:
            notification_sent = True

        return {
            "success": True,
            "case_id": sms.case_id,
            "case_log_id": sms.case_log_id,
            "renamed_path": file_path,
            "notification_sent": notification_sent,
            "error_message": None,
            "deduplicated": True,
        }

    def _has_model_field(self, field_name: str) -> bool:
        try:
            CourtSMS._meta.get_field(field_name)
            return True
        except FieldDoesNotExist:
            return False

    def _find_existing_by_event_key(self, event_key: str) -> CourtSMS | None:
        if not self._has_model_field("delivery_event_key"):
            return None
        try:
            return CourtSMS.objects.filter(delivery_event_key=event_key).first()
        except FieldError:
            return None

    def _normalize_text(self, value: str | None) -> str:
        return " ".join((value or "").split())

    def _normalize_send_time(self, value: datetime) -> str:
        current_tz = timezone.get_current_timezone()
        aware_value = value if timezone.is_aware(value) else timezone.make_aware(value, current_tz)
        return timezone.localtime(aware_value, current_tz).isoformat(timespec="seconds")

    def _hash_payload(self, payload: str) -> str:
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
