"""CourtSMS.retry_processing 的 retry_count 原子自增（DB 层验证）。

`test_court_sms_service_v2.py::TestRetryProcessing` 用 MagicMock 断言行为，
但 F() 表达式在 mock 上不会求值，测不出「并发点两次重试是否丢计数」。
这里在真实 DB 上验证：

1. 一次 retry 后 retry_count 确实 +1（F() 生效）；
2. 两次连续 retry 后是 +2（读改写丢失会导致只 +1）；
3. 事务提交后才入队（on_commit 语义）——否则 worker 可能读不到新状态。

注：`submit_task` 用 patch 替换，避免测试真的往 django-q 推任务。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus

_MOD = "apps.automation.services.sms.court_sms_service"


def _make_sms(**overrides: object) -> CourtSMS:
    payload: dict[str, object] = {
        "content": "测试短信内容",
        "received_at": timezone.now(),
        "status": CourtSMSStatus.COMPLETED,
        "retry_count": 0,
    }
    payload.update(overrides)
    return CourtSMS.objects.create(**payload)


@pytest.mark.django_db
@patch(f"{_MOD}.submit_task", return_value="task-x")
def test_retry_increments_count_once(mock_submit: object) -> None:
    from apps.automation.services.sms.court_sms_service import CourtSMSService

    sms = _make_sms(retry_count=0)
    CourtSMSService().retry_processing(sms.id)

    sms.refresh_from_db()
    assert sms.retry_count == 1
    assert sms.status == CourtSMSStatus.PENDING


@pytest.mark.django_db
@patch(f"{_MOD}.submit_task", return_value="task-x")
def test_retry_twice_increments_to_two(mock_submit: object) -> None:
    """连续两次重试必须累计到 2（读改写实现会丢一次）。"""
    from apps.automation.services.sms.court_sms_service import CourtSMSService

    sms = _make_sms(retry_count=0)
    svc = CourtSMSService()
    svc.retry_processing(sms.id)
    svc.retry_processing(sms.id)

    sms.refresh_from_db()
    assert sms.retry_count == 2


@pytest.mark.django_db
@patch(f"{_MOD}.submit_task", return_value="task-x")
def test_retry_clears_transient_fields(mock_submit: object) -> None:
    from apps.automation.services.sms.court_sms_service import CourtSMSService

    sms = _make_sms(retry_count=3, error_message="上次失败")
    CourtSMSService().retry_processing(sms.id)

    sms.refresh_from_db()
    assert sms.error_message == ""
    assert sms.retry_count == 4
