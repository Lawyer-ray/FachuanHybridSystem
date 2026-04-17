"""CourtSMS 文书送达去重服务。"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.core.exceptions import FieldDoesNotExist, FieldError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus, CourtSMSType
from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord

logger = logging.getLogger("apps.automation")


@dataclass(frozen=True)
class CourtSMSDedupIdentity:
    """文书送达事件身份。"""

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
    """统一处理文书送达 CourtSMS 的事件键生成与幂等创建。"""

    def build_document_delivery_identity(self, record: DocumentDeliveryRecord) -> CourtSMSDedupIdentity:
        """为文书送达记录生成稳定的事件身份。"""
        event_id = self._normalize_text(record.delivery_event_id)
        if event_id:
            canonical_payload = json.dumps(
                {"event_id": event_id, "event_type": CourtSMSType.DOCUMENT_DELIVERY},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            return CourtSMSDedupIdentity(
                event_id=event_id,
                event_key=self._hash_payload(canonical_payload),
                canonical_payload=canonical_payload,
                uses_fallback=False,
            )

        if not record.case_number or record.send_time is None:
            return CourtSMSDedupIdentity(event_id=None, event_key=None, canonical_payload=None, uses_fallback=False)

        canonical_payload = json.dumps(
            {
                "case_number": self._normalize_text(record.case_number),
                "court_name": self._normalize_text(record.court_name),
                "document_name": self._normalize_text(record.document_name),
                "event_type": CourtSMSType.DOCUMENT_DELIVERY,
                "send_time": self._normalize_send_time(record.send_time),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return CourtSMSDedupIdentity(
            event_id=None,
            event_key=self._hash_payload(canonical_payload),
            canonical_payload=canonical_payload,
            uses_fallback=True,
        )

    def find_document_delivery_sms(self, record: DocumentDeliveryRecord) -> CourtSMS | None:
        """按事件身份查找已存在的文书送达短信。"""
        identity = self.build_document_delivery_identity(record)
        if not identity.event_key:
            return None
        return self._find_existing_by_event_key(identity.event_key)

    def should_skip_document_delivery(self, record: DocumentDeliveryRecord) -> tuple[bool, CourtSMS | None]:
        """判断文书送达主流程是否应跳过。"""
        existing_sms = self.find_document_delivery_sms(record)
        return existing_sms is not None, existing_sms

    def get_or_create_document_delivery_sms(
        self,
        *,
        record: DocumentDeliveryRecord,
        extracted_files: list[str],
        content: str | None = None,
        received_at: datetime | None = None,
        status: str = CourtSMSStatus.MATCHING,
    ) -> CourtSMSDedupResult:
        """事务化创建或复用文书送达 CourtSMS。"""
        identity = self.build_document_delivery_identity(record)
        if identity.event_key:
            existing_sms = self._find_existing_by_event_key(identity.event_key)
            if existing_sms is not None:
                logger.info(
                    "命中文书送达重复事件，复用已有 CourtSMS: event_key=%s, event_id=%s, sms_id=%s, status=%s",
                    identity.event_key,
                    identity.event_id,
                    existing_sms.id,
                    existing_sms.status,
                )
                return CourtSMSDedupResult(sms=existing_sms, created=False, identity=identity)

        resolved_received_at = received_at or record.send_time or timezone.now()
        resolved_content = content or f"文书送达自动下载: {record.case_number}"

        create_kwargs: dict[str, Any] = {
            "content": resolved_content,
            "received_at": resolved_received_at,
            "status": status,
            "case_numbers": [record.case_number] if record.case_number else [],
            "sms_type": CourtSMSType.DOCUMENT_DELIVERY,
            "document_file_paths": extracted_files,
        }
        if self._has_model_field("delivery_event_id"):
            create_kwargs["delivery_event_id"] = identity.event_id
        if self._has_model_field("delivery_event_key"):
            create_kwargs["delivery_event_key"] = identity.event_key

        try:
            with transaction.atomic():
                sms = CourtSMS.objects.create(**create_kwargs)
        except IntegrityError:
            if not identity.event_key:
                raise
            existing_sms = self._find_existing_by_event_key(identity.event_key)
            if existing_sms is None:
                raise
            logger.info(
                "并发命中文书送达重复事件，复用已有 CourtSMS: event_key=%s, event_id=%s, sms_id=%s, status=%s",
                identity.event_key,
                identity.event_id,
                existing_sms.id,
                existing_sms.status,
            )
            return CourtSMSDedupResult(sms=existing_sms, created=False, identity=identity)

        logger.info(
            "创建文书送达 CourtSMS 成功: sms_id=%s, event_key=%s, event_id=%s, fallback=%s",
            sms.id,
            identity.event_key,
            identity.event_id,
            identity.uses_fallback,
        )
        return CourtSMSDedupResult(sms=sms, created=True, identity=identity)

    def build_existing_sms_result(self, sms: CourtSMS, file_path: str) -> dict[str, Any]:
        """构造重复命中时的统一返回结构。"""
        # 检查 notification_results 中是否有任何平台成功
        notification_sent = False
        if sms.notification_results and isinstance(sms.notification_results, dict):
            notification_sent = any(
                v.get("success", False) for v in sms.notification_results.values() if isinstance(v, dict)
            )
        # 向后兼容：也检查旧的 feishu_sent_at 字段
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
            logger.warning("CourtSMS 模型缺少 delivery_event_key 字段，跳过事件键去重查询")
            return None
        try:
            return CourtSMS.objects.filter(delivery_event_key=event_key).first()
        except FieldError:
            logger.warning("CourtSMS 模型当前未加载 delivery_event_key，跳过事件键去重查询")
            return None

    def _normalize_text(self, value: str | None) -> str:
        return " ".join((value or "").split())

    def _normalize_send_time(self, value: datetime) -> str:
        current_tz = timezone.get_current_timezone()
        aware_value = value if timezone.is_aware(value) else timezone.make_aware(value, current_tz)
        return timezone.localtime(aware_value, current_tz).isoformat(timespec="seconds")

    def _hash_payload(self, payload: str) -> str:
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
