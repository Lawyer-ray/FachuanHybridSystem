"""法院短信匹配重试计数回归测试。

覆盖 retry_count 原子自增（F 表达式）语义：
- 重试进入匹配阶段时计数在数据库侧累加（并发重投递下读改写不再丢计数）；
- 累加后的新值对 `retry_count >= 3` 的 OCR-OOM 熔断判断可见。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.db.models import F
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.automation.services.sms.court_sms_service import CourtSMSService


@pytest.mark.django_db
class TestCourtSMSRetryIncrement:
    def _make_service(self) -> CourtSMSService:
        matcher = MagicMock()
        # 不匹配到案件：走待人工分支，避免触发后续深流程
        matcher.match.return_value = None
        return CourtSMSService(parser=MagicMock(), matcher=matcher)

    def _make_sms(self, retry_count: int = 0) -> CourtSMS:
        return CourtSMS.objects.create(
            content="【送达】测试短信",
            received_at=timezone.now(),
            status=CourtSMSStatus.MATCHING,
            retry_count=retry_count,
        )

    def test_reentry_increment_accumulates_in_db(self, db):
        """两次连续重试进入（模拟并发重投递）retry_count 应累加为 2。"""
        svc = self._make_service()
        sms = self._make_sms(retry_count=0)

        for expected in (1, 2):
            result = svc._process_matching(sms)
            result.refresh_from_db(fields=["retry_count"])
            assert result.retry_count == expected

            # 重置回 MATCHING 模拟 worker 崩溃后的下一次重投递
            result.status = CourtSMSStatus.MATCHING
            result.save(update_fields=["status"])
            sms = result

    def test_concurrent_style_updates_accumulate_via_f_expression(self, db):
        """并发语义验证：两条连续原子 update（非内存读改写）计数应累加不丢失。"""
        sms = self._make_sms(retry_count=0)

        for _ in range(2):
            CourtSMS.objects.filter(pk=sms.pk).update(
                retry_count=F("retry_count") + 1,
                updated_at=timezone.now(),
            )
        sms.refresh_from_db(fields=["retry_count"])

        assert sms.retry_count == 2

    def test_ocr_breaker_fires_after_increment_reaches_limit(self, db):
        """retry_count 从 2 递增到 3 后熔断生效，转入待人工处理。"""
        svc = self._make_service()
        sms = self._make_sms(retry_count=2)

        result = svc._process_matching(sms)
        result.refresh_from_db(fields=["retry_count", "status"])

        assert result.retry_count == 3
        assert result.status == CourtSMSStatus.PENDING_MANUAL
        assert "已重试3次" in result.error_message
