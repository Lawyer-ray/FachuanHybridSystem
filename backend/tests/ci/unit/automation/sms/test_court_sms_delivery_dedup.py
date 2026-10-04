"""法院短信提交幂等去重（delivery_event_key）测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.automation.services.sms.court_sms_delivery_dedup import (
    DUPLICATE_WINDOW_SECONDS,
    build_delivery_event_key,
    build_lookup_keys,
)


class TestDeliveryEventKeyFunctions:
    def test_same_content_same_window_same_key(self) -> None:
        """同内容同时间窗内生成相同键（可被唯一约束拦截）。"""
        t1 = datetime(2025, 6, 1, 10, 0, 0)
        t2 = t1 + timedelta(seconds=30)
        assert build_delivery_event_key("同一短信", t1) == build_delivery_event_key("同一短信", t2)

    def test_same_content_days_apart_different_key(self) -> None:
        """隔天重发的相同文本键不同（不得误挡）。"""
        t1 = datetime(2025, 6, 1, 10, 0, 0)
        t2 = t1 + timedelta(days=2)
        assert build_delivery_event_key("同一短信", t1) != build_delivery_event_key("同一短信", t2)

    def test_different_content_different_key(self) -> None:
        t = datetime(2025, 6, 1, 10, 0, 0)
        assert build_delivery_event_key("短信A", t) != build_delivery_event_key("短信B", t)

    def test_key_length_fits_field(self) -> None:
        key = build_delivery_event_key("x", datetime(2025, 6, 1))
        assert len(key) == 64  # CourtSMS.delivery_event_key max_length=64

    def test_lookup_keys_cover_boundary(self) -> None:
        """查重键包含当前桶与上一桶，跨窗口边界提交也能命中。"""
        original_t = datetime(2025, 6, 1, 10, 9, 55)
        # 原始记录存的是其所在桶的键
        stored_key = build_delivery_event_key("同一短信", original_t)
        # 5 秒后（可能跨入下一桶）提交的查重键必须包含 stored_key
        late_t = original_t + timedelta(seconds=5)
        assert stored_key in build_lookup_keys("同一短信", late_t)

    def test_window_constant_reasonable(self) -> None:
        assert 60 <= DUPLICATE_WINDOW_SECONDS <= 3600


@pytest.mark.django_db
class TestSubmitSmsDedupEndToEnd:
    @patch("apps.automation.services.sms.court_sms_service.submit_task")
    def test_duplicate_submit_returns_existing(self, mock_submit) -> None:
        """窗口内重复提交：返回既有记录、不新增行、任务只提交一次。"""
        from apps.automation.services.sms.court_sms_service import CourtSMSService

        mock_submit.return_value = "task-1"
        received_at = datetime(2025, 6, 1, 10, 0, 0)
        svc = CourtSMSService()

        first = svc.submit_sms("【佛山市禅城区法院】重复提交测试", received_at=received_at)
        second = svc.submit_sms("【佛山市禅城区法院】重复提交测试", received_at=received_at + timedelta(seconds=30))

        assert second.id == first.id
        assert CourtSMS.objects.filter(content="【佛山市禅城区法院】重复提交测试").count() == 1
        mock_submit.assert_called_once()

    @patch("apps.automation.services.sms.court_sms_service.submit_task")
    def test_same_content_days_apart_creates_new(self, mock_submit) -> None:
        """隔天重发的相同文本是不同送达事件，必须创建新记录。"""
        from apps.automation.services.sms.court_sms_service import CourtSMSService

        mock_submit.return_value = "task-2"
        svc = CourtSMSService()
        content = "【佛山中院】开庭提醒"

        first = svc.submit_sms(content, received_at=datetime(2025, 6, 1, 10, 0, 0))
        second = svc.submit_sms(content, received_at=datetime(2025, 6, 3, 10, 0, 0))

        assert second.id != first.id
        assert CourtSMS.objects.filter(content=content).count() == 2

    @patch("apps.automation.services.sms.court_sms_service.submit_task")
    def test_unique_constraint_blocks_same_key_insert(self, mock_submit) -> None:
        """同键插入被唯一约束 uniq_courtsms_delivery_event_key 拦截。"""
        from django.db import IntegrityError

        received_at = datetime(2025, 6, 1, 10, 0, 0)
        key = build_delivery_event_key("约束测试", received_at)

        CourtSMS.objects.create(
            content="约束测试",
            received_at=received_at,
            status=CourtSMSStatus.PENDING,
            delivery_event_key=key,
        )
        with pytest.raises(IntegrityError):
            CourtSMS.objects.create(
                content="约束测试",
                received_at=received_at,
                status=CourtSMSStatus.PENDING,
                delivery_event_key=key,
            )
