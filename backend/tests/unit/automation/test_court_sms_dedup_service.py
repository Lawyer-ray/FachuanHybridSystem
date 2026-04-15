"""CourtSMSDedupService 单元测试。"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMSStatus
from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord
from apps.automation.services.sms.court_sms_dedup_service import CourtSMSDedupService


@pytest.mark.django_db
class TestCourtSMSDedupService:
    """验证文书送达去重的核心行为。"""

    def test_build_identity_prefers_delivery_event_id(self) -> None:
        service = CourtSMSDedupService()
        record = DocumentDeliveryRecord(
            case_number="（2026）粤0101民初1号",
            send_time=timezone.now(),
            element_index=0,
            document_name="送达文书",
            court_name="广东省某法院",
            delivery_event_id="SDBH-001",
        )

        identity = service.build_document_delivery_identity(record)

        assert identity.event_id == "SDBH-001"
        assert identity.event_key
        assert identity.uses_fallback is False

    def test_build_identity_fallback_when_no_event_id(self) -> None:
        service = CourtSMSDedupService()
        send_time = timezone.now()
        record = DocumentDeliveryRecord(
            case_number="（2026）粤0101民初2号",
            send_time=send_time,
            element_index=0,
            document_name="裁定书",
            court_name="广东省某法院",
            delivery_event_id="",
        )

        identity = service.build_document_delivery_identity(record)

        assert identity.event_id is None
        assert identity.event_key
        assert identity.uses_fallback is True

    def test_get_or_create_reuses_existing_sms(self) -> None:
        service = CourtSMSDedupService()
        record = DocumentDeliveryRecord(
            case_number="（2026）粤0101民初3号",
            send_time=timezone.now(),
            element_index=0,
            document_name="判决书",
            court_name="广东省某法院",
            delivery_event_id="SDBH-REUSE-001",
        )

        first = service.get_or_create_document_delivery_sms(record=record, extracted_files=["/tmp/a.pdf"])
        second = service.get_or_create_document_delivery_sms(record=record, extracted_files=["/tmp/b.pdf"])

        assert first.created is True
        assert second.created is False
        assert first.sms.id == second.sms.id
        assert second.sms.status == CourtSMSStatus.MATCHING

    def test_get_or_create_without_identity_does_not_force_dedup(self) -> None:
        service = CourtSMSDedupService()
        record = DocumentDeliveryRecord(
            case_number="",
            send_time=None,
            element_index=0,
            document_name="",
            court_name="",
            delivery_event_id="",
        )

        first = service.get_or_create_document_delivery_sms(record=record, extracted_files=["/tmp/a.pdf"])
        second = service.get_or_create_document_delivery_sms(record=record, extracted_files=["/tmp/b.pdf"])

        assert first.created is True
        assert second.created is True
        assert first.sms.id != second.sms.id
