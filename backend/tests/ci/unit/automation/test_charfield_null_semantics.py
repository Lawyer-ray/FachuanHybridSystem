"""automation CharField 空值语义归一回归测试。

归一后契约：文本字段（error_message / sms_type / captcha_* / token_*）
列级 NOT NULL + ORM 默认空串，创建不传字段落 ''，清错/重置写 '' 而非 None。
例外：CourtSMS.delivery_event_id / delivery_event_key 保留 NULL 语义
（条件唯一约束依赖 isnull=False 分支），不在本批归一范围。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.automation.models import (
    CourtSMS,
    CourtSMSStatus,
    CourtSMSType,
    PreservationQuote,
    ScraperTask,
    ScraperTaskType,
    TokenAcquisitionHistory,
    TokenAcquisitionStatus,
)
from apps.automation.services.sms.court_sms_repository import CourtSMSRepository

REPO = CourtSMSRepository()


def _make_task() -> ScraperTask:
    return ScraperTask.objects.create(task_type=ScraperTaskType.COURT_DOCUMENT, url="https://example.com/test")


def _make_sms() -> CourtSMS:
    from django.utils import timezone

    return CourtSMS.objects.create(content="测试短信", received_at=timezone.now())


@pytest.mark.django_db
class TestCreateDefaultsAreEmptyString:
    def test_scraper_task_texts_default_empty(self):
        task = _make_task()
        task.refresh_from_db()
        assert task.error_message == ""
        assert task.captcha_image_path == ""
        assert task.captcha_answer == ""
        assert not task.error_message

    def test_court_sms_texts_default_empty(self):
        sms = _make_sms()
        sms.refresh_from_db()
        assert sms.sms_type == ""
        assert sms.error_message == ""
        assert sms.feishu_error == ""
        str(sms)  # '' 类型下 __str__ 不应抛错

    def test_preservation_quote_error_message_default_empty(self):
        quote = PreservationQuote.objects.create(preserve_amount=Decimal("100.00"))
        quote.refresh_from_db()
        assert quote.error_message == ""

    def test_token_history_texts_default_empty(self):
        history = TokenAcquisitionHistory.objects.create(
            site_name="court_zxfw",
            account="tester",
            status=TokenAcquisitionStatus.FAILED,
            trigger_reason="test",
        )
        history.refresh_from_db()
        assert history.error_message == ""
        assert history.token_preview == ""
        assert history.token_fingerprint == ""
        assert history.token_redacted == ""


@pytest.mark.django_db
class TestRepositoryWritesEmptyString:
    def test_clear_error_writes_empty_string(self):
        sms = _make_sms()
        sms.error_message = "boom"
        REPO.clear_error(sms=sms)
        sms.refresh_from_db()
        assert sms.error_message == ""

    def test_set_status_none_error_coerced_to_empty(self):
        sms = _make_sms()
        REPO.set_status(sms=sms, status=CourtSMSStatus.PENDING)
        sms.refresh_from_db()
        assert sms.error_message == ""


@pytest.mark.django_db
class TestSmsTypeValueRoundTrip:
    def test_real_sms_type_preserved(self):
        sms = _make_sms()
        sms.sms_type = CourtSMSType.DOCUMENT_DELIVERY
        sms.save(update_fields=["sms_type"])
        sms.refresh_from_db()
        assert sms.sms_type == CourtSMSType.DOCUMENT_DELIVERY
        assert sms.get_sms_type_display() == "文书送达"
