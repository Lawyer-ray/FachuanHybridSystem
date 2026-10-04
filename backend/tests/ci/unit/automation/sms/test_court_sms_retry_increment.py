"""法院短信匹配重试计数回归测试。

覆盖修复后的 retry_count 计数语义：
- 重试计数只由 retry_processing（人工重试）递增；匹配阶段正常进入/续跑
  （含下载完成续跑）不得递增，否则一次人工重试即达熔断阈值并误报；
- `retry_count >= 3` 的熔断（转 PENDING_MANUAL）语义保留；
- F 表达式原子自增的并发累加语义保持可用（供其它计数场景复用）。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.db.models import F
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.automation.services.sms.court_sms_service import CourtSMSService

_MOD = "apps.automation.services.sms.court_sms_service"


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

    def test_matching_entry_does_not_increment(self, db):
        """以 MATCHING 状态进入匹配阶段（正常首过/续跑）不得递增 retry_count。"""
        svc = self._make_service()
        sms = self._make_sms(retry_count=0)

        result = svc._process_matching(sms)
        result.refresh_from_db(fields=["retry_count"])

        assert result.retry_count == 0
        # 未达阈值应正常执行匹配（而非熔断）
        svc.matcher.match.assert_called_once()

    def test_repeated_reentry_does_not_accumulate(self, db):
        """多次重投递进入匹配阶段（不经过 retry_processing）计数保持不变。"""
        svc = self._make_service()
        sms = self._make_sms(retry_count=0)

        for _ in range(3):
            result = svc._process_matching(sms)
            result.status = CourtSMSStatus.MATCHING  # 模拟 worker 崩溃后状态卡在 MATCHING
            result.save(update_fields=["status"])
            sms = result

        sms.refresh_from_db(fields=["retry_count"])
        assert sms.retry_count == 0

    @patch(f"{_MOD}.submit_task")
    def test_retry_processing_is_the_only_incrementer(self, mock_submit, db):
        """人工重试（retry_processing）是唯一的计数递增入口。"""
        mock_submit.return_value = "task-1"
        svc = self._make_service()
        sms = self._make_sms(retry_count=0)

        svc.retry_processing(sms.id)
        sms.refresh_from_db(fields=["retry_count"])
        assert sms.retry_count == 1

        svc.retry_processing(sms.id)
        sms.refresh_from_db(fields=["retry_count"])
        assert sms.retry_count == 2

    @patch(f"{_MOD}.submit_task")
    def test_breaker_fires_after_manual_retries_reach_limit(self, mock_submit, db):
        """第 3 次人工重试（retry_count 递增到 3）后再进入匹配阶段即熔断。"""
        mock_submit.return_value = "task-2"
        svc = self._make_service()
        sms = self._make_sms(retry_count=2)

        svc.retry_processing(sms.id)  # 第 3 次人工重试
        sms.refresh_from_db(fields=["retry_count", "status"])
        assert sms.retry_count == 3

        result = svc._process_matching(sms)

        assert result.status == CourtSMSStatus.PENDING_MANUAL
        assert "已重试3次" in result.error_message
        svc.matcher.match.assert_not_called()

    @patch(f"{_MOD}.submit_task")
    def test_fourth_entry_short_circuits_without_matching(self, mock_submit, db):
        """retry_count 达到 3 后再次进入匹配阶段：熔断且不再执行匹配。"""
        mock_submit.return_value = "task-3"
        svc = self._make_service()
        sms = self._make_sms(retry_count=3)

        result = svc._process_matching(sms)

        assert result.status == CourtSMSStatus.PENDING_MANUAL
        svc.matcher.match.assert_not_called()

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
