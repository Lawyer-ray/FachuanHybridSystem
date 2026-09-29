"""court_sms_abort_service.py 单元测试。"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from django_q.models import OrmQ, Schedule
from django_q.signing import SignedPackage


def _queue_payload(func: str, args: list) -> str:
    """按 submit_task 的包装格式构造签名队列条目（run_task 剥壳路径）"""
    return SignedPackage.dumps({"id": "fake-id", "name": "test", "func": func, "args": args})


class TestQueueEntryMatches:
    def _svc(self):
        from apps.automation.services.sms.court_sms_abort_service import CourtSmsAbortService

        return CourtSmsAbortService()

    def test_matches_wrapped_sms_worker(self):
        payload = _queue_payload(
            "apps.core.tasking.entries.run_task", ["apps.automation.workers.court_sms_tasks.process_sms", [77]]
        )
        assert self._svc()._queue_entry_matches(payload, "77", set()) is True

    def test_matches_scraper_worker_by_task_id(self):
        payload = _queue_payload(
            "apps.core.tasking.entries.run_task", ["apps.automation.tasks.execute_scraper_task", [321]]
        )
        assert self._svc()._queue_entry_matches(payload, "77", {"321"}) is True

    def test_rejects_same_digits_different_id(self):
        # sms_id=7 不能匹配 args 里的 77（数字子串误配是经典坑）
        payload = _queue_payload(
            "apps.core.tasking.entries.run_task", ["apps.automation.workers.court_sms_tasks.process_sms", [77]]
        )
        assert self._svc()._queue_entry_matches(payload, "7", set()) is False

    def test_rejects_unrelated_func(self):
        payload = _queue_payload("apps.core.tasking.entries.run_task", ["some.other.func", [77]])
        assert self._svc()._queue_entry_matches(payload, "77", set()) is False

    def test_rejects_garbage_payload(self):
        assert self._svc()._queue_entry_matches("not-a-signed-package", "77", set()) is False


@pytest.mark.django_db
class TestAbortAndDelete:
    def _make_sms(self, with_task: bool = True):
        from apps.automation.models import CourtSMS, ScraperTask, ScraperTaskStatus, ScraperTaskType

        sms = CourtSMS.objects.create(content="测试短信", received_at=timezone.now())
        if with_task:
            task = ScraperTask.objects.create(
                task_type=ScraperTaskType.COURT_DOCUMENT,
                url="https://example.com/doc",
                status=ScraperTaskStatus.RUNNING,
                config={"court_sms_id": sms.id, "source": "court_sms"},
            )
            sms.scraper_task = task
            sms.save(update_fields=["scraper_task"])
        return sms

    def _svc(self):
        from apps.automation.services.sms.court_sms_abort_service import CourtSmsAbortService

        return CourtSmsAbortService()

    def test_not_found_raises(self):
        from apps.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            self._svc().abort_and_delete(99999)

    def test_deletes_sms_and_owned_scraper_task(self):
        from apps.automation.models import CourtSMS, ScraperTask

        sms = self._make_sms()
        task_id = sms.scraper_task_id
        svc = self._svc()

        with patch.object(svc, "_remove_queued_tasks", return_value=(0, None)) as mock_queue:
            summary = svc.abort_and_delete(sms.id)
        mock_queue.assert_called_once()

        assert summary["scraper_task_deleted"] is True
        assert not CourtSMS.objects.filter(id=sms.id).exists()
        assert not ScraperTask.objects.filter(id=task_id).exists()

    def test_keeps_foreign_scraper_task(self):
        """config 无回溯标识的任务只解除关联，不删本体"""
        from apps.automation.models import CourtSMS, ScraperTask

        sms = self._make_sms()
        sms.scraper_task.config = {}
        sms.scraper_task.save(update_fields=["config"])
        task_id = sms.scraper_task_id
        svc = self._svc()

        with patch.object(svc, "_remove_queued_tasks", return_value=(0, None)):
            summary = svc.abort_and_delete(sms.id)

        assert summary["scraper_task_deleted"] is False
        assert not CourtSMS.objects.filter(id=sms.id).exists()
        assert ScraperTask.objects.filter(id=task_id).exists()

    def test_removes_sms_level_and_task_level_retry_schedules(self):
        from django_q.models import Schedule

        sms = self._make_sms()
        task_id = sms.scraper_task_id
        Schedule.objects.create(
            func="apps.automation.workers.court_sms_tasks.retry_download_task",
            args=str(sms.id),
            name=f"court_sms_retry_download_{sms.id}",
            schedule_type=Schedule.ONCE,
            next_run=timezone.now() + timedelta(seconds=60),
        )
        Schedule.objects.create(
            func="apps.automation.tasks.execute_scraper_task",
            args=str(task_id),
            name=f"retry_task_{task_id}_1",
            schedule_type=Schedule.ONCE,
            next_run=timezone.now() + timedelta(seconds=60),
        )
        # 无关调度不应被误删
        other = Schedule.objects.create(
            func="apps.automation.workers.court_sms_tasks.retry_download_task",
            args=str(sms.id + 1000),
            name=f"court_sms_retry_download_{sms.id + 1000}",
            schedule_type=Schedule.ONCE,
            next_run=timezone.now(),
        )
        svc = self._svc()

        with patch.object(svc, "_remove_queued_tasks", return_value=(0, None)):
            summary = svc.abort_and_delete(sms.id)

        assert summary["removed_schedules"] == 2
        assert Schedule.objects.filter(id=other.id).exists()
        assert not Schedule.objects.filter(name=f"court_sms_retry_download_{sms.id}").exists()

    def test_remove_orm_entries_deletes_matching_only(self):
        """ORM broker 队列条目按签名 payload 解析后精确删除"""
        sms = self._make_sms()
        task_id = sms.scraper_task_id

        OrmQ.objects.create(
            key="default",
            payload=_queue_payload(
                "apps.core.tasking.entries.run_task",
                ["apps.automation.workers.court_sms_tasks.process_sms", [sms.id]],
            ),
        )
        OrmQ.objects.create(
            key="default",
            payload=_queue_payload(
                "apps.core.tasking.entries.run_task",
                ["apps.automation.tasks.execute_scraper_task", [task_id]],
            ),
        )
        unrelated = OrmQ.objects.create(
            key="default",
            payload=_queue_payload(
                "apps.core.tasking.entries.run_task",
                ["apps.automation.workers.court_sms_tasks.process_sms", [sms.id + 1000]],
            ),
        )

        removed = self._svc()._remove_orm_entries(str(sms.id), {str(task_id)})
        assert removed == 2
        assert OrmQ.objects.filter(id=unrelated.id).exists()
        assert OrmQ.objects.count() == 1

    def test_remove_redis_entries_uses_connection_attribute(self):
        """Redis broker 的 connection 是实例属性（redis 客户端）而非方法；
        用假 broker 验证 遍历→签名解析→lrem 路径，不触碰真实 Redis"""
        match_raw = _queue_payload(
            "apps.core.tasking.entries.run_task",
            ["apps.automation.workers.court_sms_tasks.process_sms", [77]],
        )
        other_raw = _queue_payload(
            "apps.core.tasking.entries.run_task",
            ["apps.automation.tasks.execute_scraper_task", [999]],
        )

        class FakeConn:
            def __init__(self) -> None:
                self.removed: list[tuple[str, int, str]] = []

            def lrange(self, key: str, start: int, end: int) -> list[str]:
                return [match_raw, other_raw]

            def lrem(self, key: str, count: int, value: str) -> int:
                self.removed.append((key, count, value))
                return 1

        fake_conn = FakeConn()
        broker = SimpleNamespace(connection=fake_conn, list_key="django_q:default:q")

        removed = self._svc()._remove_redis_entries(broker, "77", {"321"})

        assert removed == 1
        assert fake_conn.removed == [("django_q:default:q", 1, match_raw)]
