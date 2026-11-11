"""Tests for message_hub/tasks.py - sync_all_sources and helpers."""

import socket
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_message_hub_plugin

    _HAS_MH = has_message_hub_plugin()
except ImportError:
    _HAS_MH = False

pytestmark = pytest.mark.skipif(not _HAS_MH, reason="message_hub plugin not installed")


class TestIsExpectedSyncError:
    """Test _is_expected_sync_error helper."""

    def test_identifies_socket_error(self):
        """Socket errors are expected."""
        from apps.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(socket.gaierror("Name resolution failed")) is True

    def test_identifies_timeout_error(self):
        """Timeout errors are expected."""
        from apps.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(TimeoutError("Connection timed out")) is True

    def test_identifies_connection_error(self):
        """Connection errors are expected."""
        from apps.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(ConnectionError("Connection refused")) is True

    def test_identifies_err_internet_disconnected(self):
        """Internet disconnected errors are expected."""
        from apps.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(Exception("ERR_INTERNET_DISCONNECTED")) is True

    def test_identifies_greenlet_error(self):
        """Greenlet errors are expected."""
        from apps.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(Exception("greenlet.error: cannot switch")) is True

    def test_identifies_target_closed(self):
        """Target closed errors are expected."""
        from apps.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(Exception("Target closed")) is True

    def test_identifies_browser_closed(self):
        """Browser closed errors are expected."""
        from apps.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(Exception("Browser has been closed")) is True

    def test_rejects_unexpected_error(self):
        """Unexpected errors are not expected."""
        from apps.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(ValueError("Some unexpected error")) is False

    def test_rejects_generic_runtime_error(self):
        """Generic runtime errors are not expected."""
        from apps.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(RuntimeError("Something went wrong")) is False


class TestSyncSourceById:
    """Test sync_source_by_id task."""

    def _run(self, *, window_days: int | None = None) -> tuple[MagicMock, MagicMock]:
        """跑一次 sync_source_by_id，返回 (source, fetcher) 两个 mock。"""
        from apps.message_hub.tasks import sync_source_by_id

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("apps.message_hub.services.get_fetcher") as mock_get_fetcher,
        ):
            mock_source = MagicMock()
            mock_source.display_name = "Test Source"
            MockSource.objects.select_related.return_value.filter.return_value.first.return_value = mock_source

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_new_messages.return_value = 5
            mock_get_fetcher.return_value = mock_fetcher

            sync_source_by_id(1, window_days=window_days)
        return mock_source, mock_fetcher

    def test_syncs_single_source(self, db):
        """Fetches new messages from a single source.

        ``window_days`` 是 **keyword-only** 参数（见 ``MessageFetcher.fetch_new_messages``
        与 ``sync_source_by_id`` 的显式传参）；不传时任务透传 ``None``，
        含义是「按来源的 sync_since 全量回填」，不是「没传这个参数」。
        本断言曾停在旧签名 ``fetch_new_messages(source)`` 上，改签名后长期失败。
        """
        mock_source, mock_fetcher = self._run(window_days=None)

        mock_fetcher.fetch_new_messages.assert_called_once_with(mock_source, window_days=None)

    def test_passes_window_days_through(self, db):
        """前端手动同步传的 window_days 必须原样透传给 fetcher。

        这条与上一条分开：``None`` 与一个具体天数走同一行代码，
        只测 None 的话「参数根本没传下去」也能通过。
        """
        mock_source, mock_fetcher = self._run(window_days=7)

        mock_fetcher.fetch_new_messages.assert_called_once_with(mock_source, window_days=7)


class TestIsSourceDue:
    """轮询周期判定：每个来源按自己的 poll_interval_minutes 决定是否到点。"""

    def test_never_synced_is_due(self):
        from django.utils import timezone

        from apps.message_hub.tasks import _is_source_due

        assert _is_source_due(poll_interval_minutes=60, last_sync_at=None, now=timezone.now()) is True

    def test_not_due_before_interval_elapsed(self):
        from django.utils import timezone

        from apps.message_hub.tasks import _is_source_due

        now = timezone.now()
        assert _is_source_due(poll_interval_minutes=60, last_sync_at=now - timedelta(minutes=59), now=now) is False

    def test_due_after_interval_elapsed(self):
        from django.utils import timezone

        from apps.message_hub.tasks import _is_source_due

        now = timezone.now()
        assert _is_source_due(poll_interval_minutes=60, last_sync_at=now - timedelta(minutes=60), now=now) is True

    def test_zero_interval_disables_auto_polling(self):
        """0 表示不自动轮询（手动上传 / 客户链接类来源）。"""
        from django.utils import timezone

        from apps.message_hub.tasks import _is_source_due

        assert _is_source_due(poll_interval_minutes=0, last_sync_at=None, now=timezone.now()) is False

    def test_negative_interval_disables_auto_polling(self):
        from django.utils import timezone

        from apps.message_hub.tasks import _is_source_due

        assert _is_source_due(poll_interval_minutes=-5, last_sync_at=None, now=timezone.now()) is False

    def test_long_interval_source_waits(self):
        """720 分钟（12 小时）的来源在 30 分钟内不应被反复拉取。"""
        from django.utils import timezone

        from apps.message_hub.tasks import _is_source_due

        now = timezone.now()
        assert _is_source_due(poll_interval_minutes=720, last_sync_at=now - timedelta(minutes=30), now=now) is False


class TestSyncAllSources:
    """Test sync_all_sources task."""

    def _run(self, rows, *, lock_acquired=True):
        """执行 sync_all_sources，返回 (submit_task mock, source manager mock)。"""
        from apps.message_hub.tasks import sync_all_sources

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("apps.core.tasking.submit_task") as mock_submit_task,
            patch("apps.message_hub.tasks.cache") as mock_cache,
        ):
            mock_cache.add.return_value = lock_acquired
            mock_qs = MagicMock()
            mock_qs.values_list.return_value = rows
            MockSource.objects.filter.return_value = mock_qs

            sync_all_sources()

        return mock_submit_task, MockSource

    def test_dispatches_only_sources_due(self, db):
        """只有到点的来源才派发任务；未到点的跳过。"""
        from django.utils import timezone

        now = timezone.now()
        rows = [
            (1, "imap", 60, now - timedelta(minutes=90)),  # 到点
            (2, "court_inbox", 720, now - timedelta(minutes=30)),  # 未到点
            (3, "court_schedule", 720, None),  # 从未同步 -> 到点
        ]
        mock_submit_task, _ = self._run(rows)

        dispatched_ids = [c.args[1] for c in mock_submit_task.call_args_list]
        assert dispatched_ids == [1, 3]

    def test_imap_source_gets_no_timeout_override(self, db):
        """普通 IMAP 源不传超时。"""
        rows = [(1, "imap", 60, None)]
        mock_submit_task, _ = self._run(rows)

        mock_submit_task.assert_called_once_with(
            "apps.message_hub.tasks.sync_source_by_id", 1, group="message_hub", timeout=None
        )

    def test_court_source_gets_long_timeout(self, db):
        """一张网 Playwright 源单独给 1800s 超时。"""
        rows = [(2, "court_inbox", 720, None)]
        mock_submit_task, _ = self._run(rows)

        mock_submit_task.assert_called_once_with(
            "apps.message_hub.tasks.sync_source_by_id", 2, group="message_hub", timeout=1800
        )

    def test_zero_interval_source_never_auto_synced(self, db):
        """poll_interval_minutes=0 的来源不参与自动轮询。"""
        rows = [(8, "manual_upload", 0, None)]
        mock_submit_task, _ = self._run(rows)

        mock_submit_task.assert_not_called()

    def test_skips_when_lock_held(self, db):
        """上一轮调度的锁未过期时不重复提交。"""
        rows = [(1, "imap", 60, None)]
        mock_submit_task, MockSource = self._run(rows, lock_acquired=False)

        mock_submit_task.assert_not_called()
        # 拿不到锁时不应查询来源列表
        MockSource.objects.filter.assert_not_called()

    def test_no_sources_no_dispatch(self, db):
        """无启用来源时不提交任何任务。"""
        mock_submit_task, _ = self._run([])

        mock_submit_task.assert_not_called()

    def test_none_due_no_dispatch(self, db):
        """有来源但都未到点时，不提交任务。"""
        from django.utils import timezone

        now = timezone.now()
        rows = [
            (1, "imap", 60, now - timedelta(minutes=10)),
            (2, "court_inbox", 720, now - timedelta(minutes=10)),
        ]
        mock_submit_task, _ = self._run(rows)

        mock_submit_task.assert_not_called()


class TestRegisterSchedule:
    """调度心跳注册/校正：改小间隔后旧记录必须跟随更新。"""

    def test_creates_when_absent(self):
        from apps.message_hub.tasks import _SCHEDULE_HEARTBEAT_MINUTES, _register_schedule

        with patch("apps.core.tasking.ScheduleQueryService") as MockSvc:
            MockSvc.return_value.get_schedule_by_name.return_value = None
            _register_schedule()

            kwargs = MockSvc.return_value.create_interval_schedule.call_args.kwargs
            assert kwargs["minutes"] == _SCHEDULE_HEARTBEAT_MINUTES

    def test_fixes_stale_minutes(self):
        """存量 30 分钟记录必须被校正，否则改代码不生效。"""
        from apps.message_hub.tasks import _SCHEDULE_HEARTBEAT_MINUTES, TASK_FUNC, _register_schedule

        existing = MagicMock()
        existing.func = TASK_FUNC
        existing.minutes = 30

        with patch("apps.core.tasking.ScheduleQueryService") as MockSvc:
            MockSvc.return_value.get_schedule_by_name.return_value = existing
            _register_schedule()

            assert existing.minutes == _SCHEDULE_HEARTBEAT_MINUTES
            existing.save.assert_called_once()
            assert "minutes" in existing.save.call_args.kwargs["update_fields"]

    def test_no_write_when_already_correct(self):
        from apps.message_hub.tasks import _SCHEDULE_HEARTBEAT_MINUTES, TASK_FUNC, _register_schedule

        existing = MagicMock()
        existing.func = TASK_FUNC
        existing.minutes = _SCHEDULE_HEARTBEAT_MINUTES

        with patch("apps.core.tasking.ScheduleQueryService") as MockSvc:
            MockSvc.return_value.get_schedule_by_name.return_value = existing
            _register_schedule()

            existing.save.assert_not_called()

    def test_fixes_stale_func(self):
        from apps.message_hub.tasks import TASK_FUNC, _register_schedule

        existing = MagicMock()
        existing.func = "apps.message_hub.old.path"
        existing.minutes = 1

        with patch("apps.core.tasking.ScheduleQueryService") as MockSvc:
            MockSvc.return_value.get_schedule_by_name.return_value = existing
            _register_schedule()

            assert existing.func == TASK_FUNC
            assert "func" in existing.save.call_args.kwargs["update_fields"]
