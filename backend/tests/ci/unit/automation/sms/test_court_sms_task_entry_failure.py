"""法院短信任务入口失败落库回归测试。

覆盖 2026-10-12 事故：qcluster 未随代码更新重启，worker 内存残留旧模块，
process_sms 在服务装配阶段抛 ImportError，短信永远卡在 pending 且
error_message 为空（admin 页面看不到任何异常，也无法判断可否重试）。

修复语义：
- 任务入口（构造 usecase/服务装配）阶段抛异常时，兜底把 SMS 落库为
  FAILED + 带入口标识的 error_message，异常继续上抛给 Django-Q 记录；
- 已是 FAILED/COMPLETED 的记录跳过，避免覆盖 Service 层更精确的错误信息。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.automation.workers.court_sms_tasks import process_sms, process_sms_from_matching

_WORKER_MOD = "apps.automation.workers.court_sms_tasks"


def _make_sms(status: str = CourtSMSStatus.PENDING) -> CourtSMS:
    return CourtSMS.objects.create(
        content="【佛山市禅城区人民法院】测试短信",
        received_at=timezone.now(),
        status=status,
    )


class TestTaskEntryFailureMarking:
    def test_service_locator_failure_marks_failed(self, db):
        """服务装配抛 ImportError（事故场景）：pending → FAILED，错误信息可读。"""
        sms = _make_sms(status=CourtSMSStatus.PENDING)

        with (
            patch(f"{_WORKER_MOD}.ServiceLocator.get_court_sms_service") as locator,
            pytest.raises(ImportError, match="CaseAssignmentSource"),
        ):
            locator.side_effect = ImportError("cannot import name 'CaseAssignmentSource' from 'apps.cases.models'")
            process_sms(sms.id)

        sms.refresh_from_db()
        assert sms.status == CourtSMSStatus.FAILED
        assert "CaseAssignmentSource" in sms.error_message
        assert "process_sms" in sms.error_message

    def test_usecase_execute_failure_marks_failed(self, db):
        """进入 usecase 后执行抛错（Service 未落库的场景）：同样兜底落库。"""
        sms = _make_sms(status=CourtSMSStatus.MATCHING)
        usecase = MagicMock()
        usecase.execute.side_effect = RuntimeError("匹配引擎崩溃")

        with (
            patch(f"{_WORKER_MOD}.ServiceLocator.get_court_sms_service"),
            patch(
                "apps.automation.usecases.court_sms.process_sms.ProcessSmsFromMatchingUsecase",
                return_value=usecase,
            ),
            pytest.raises(RuntimeError, match="匹配引擎崩溃"),
        ):
            process_sms_from_matching(sms.id)

        sms.refresh_from_db()
        assert sms.status == CourtSMSStatus.FAILED
        assert "匹配引擎崩溃" in sms.error_message

    def test_existing_failed_message_not_overwritten(self, db):
        """Service 层已写 FAILED + 精确错误时，入口兜底不得覆盖。"""
        sms = _make_sms(status=CourtSMSStatus.FAILED)
        sms.error_message = "处理短信失败: 精确的业务错误"
        sms.save(update_fields=["error_message"])

        with (
            patch(f"{_WORKER_MOD}.ServiceLocator.get_court_sms_service") as locator,
            pytest.raises(ImportError),
        ):
            locator.side_effect = ImportError("boom")
            process_sms(sms.id)

        sms.refresh_from_db()
        assert sms.status == CourtSMSStatus.FAILED
        assert sms.error_message == "处理短信失败: 精确的业务错误"

    def test_completed_sms_not_downgraded(self, db):
        """已完成短信即使入口炸了也不得回退为 FAILED。"""
        sms = _make_sms(status=CourtSMSStatus.COMPLETED)

        with (
            patch(f"{_WORKER_MOD}.ServiceLocator.get_court_sms_service") as locator,
            pytest.raises(ImportError),
        ):
            locator.side_effect = ImportError("boom")
            process_sms(sms.id)

        sms.refresh_from_db()
        assert sms.status == CourtSMSStatus.COMPLETED

    def test_missing_sms_is_silent_noop(self, db):
        """SMS 不存在（如已删除）：兜底不产生任何数据库副作用，异常照常上抛。"""
        with (
            patch(f"{_WORKER_MOD}.ServiceLocator.get_court_sms_service") as locator,
            pytest.raises(ImportError),
        ):
            locator.side_effect = ImportError("boom")
            process_sms(999999)
