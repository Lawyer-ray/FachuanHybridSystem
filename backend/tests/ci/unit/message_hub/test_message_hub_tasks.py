"""Tests for message_hub/tasks.py - sync_all_sources and helpers."""

import socket
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

    def test_syncs_single_source(self, db):
        """Fetches new messages from a single source."""
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

            # Should not raise
            sync_source_by_id(1)

            mock_fetcher.fetch_new_messages.assert_called_once_with(mock_source)


class TestSyncAllSources:
    """Test sync_all_sources task."""

    def test_syncs_enabled_sources(self, db):
        """Submits async tasks for each enabled source."""
        from apps.message_hub.tasks import sync_all_sources

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("apps.core.tasking.submit_task") as mock_submit_task,
            patch("apps.message_hub.tasks.cache") as mock_cache,
        ):
            mock_cache.add.return_value = True
            mock_qs = MagicMock()
            mock_qs.values_list.return_value = [(1, "imap"), (2, "court_inbox"), (3, "court_schedule")]
            MockSource.objects.filter.return_value = mock_qs

            sync_all_sources()

            assert mock_submit_task.call_count == 3
            # 普通 IMAP 源不传超时
            mock_submit_task.assert_any_call(
                "apps.message_hub.tasks.sync_source_by_id", 1, group="message_hub", timeout=None
            )
            # 一张网 Playwright 源单独给 1800s 超时
            mock_submit_task.assert_any_call(
                "apps.message_hub.tasks.sync_source_by_id", 2, group="message_hub", timeout=1800
            )

    def test_skips_when_lock_held(self, db):
        """上一轮调度的锁未过期时不重复提交。"""
        from apps.message_hub.tasks import sync_all_sources

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("apps.core.tasking.submit_task") as mock_submit_task,
            patch("apps.message_hub.tasks.cache") as mock_cache,
        ):
            mock_cache.add.return_value = False
            mock_qs = MagicMock()
            mock_qs.values_list.return_value = [(1, "imap")]
            MockSource.objects.filter.return_value = mock_qs

            sync_all_sources()

            mock_submit_task.assert_not_called()
            # 拿不到锁时不应查询来源列表
            MockSource.objects.filter.assert_not_called()

    def test_lock_held_skips_dispatch(self, db):
        """上一轮锁未过期时应跳过本轮派发（原错误分支测试在 submit_task 重构后失效）。"""
        from apps.message_hub.tasks import sync_all_sources

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("apps.core.tasking.submit_task") as mock_submit_task,
            patch("apps.message_hub.tasks.cache") as mock_cache,
        ):
            mock_cache.add.return_value = False  # 锁被占用
            assert sync_all_sources() is None
            # 抢锁失败时不应查询来源，也不派发任何任务
            MockSource.objects.filter.assert_not_called()
            mock_submit_task.assert_not_called()

    def test_no_sources_no_dispatch(self, db):
        """无启用来源时不提交任何任务。"""
        from apps.message_hub.tasks import sync_all_sources

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("apps.core.tasking.submit_task") as mock_submit_task,
            patch("apps.message_hub.tasks.cache") as mock_cache,
        ):
            mock_cache.add.return_value = True
            mock_qs = MagicMock()
            mock_qs.values_list.return_value = []
            MockSource.objects.filter.return_value = mock_qs

            assert sync_all_sources() is None
            mock_submit_task.assert_not_called()

    def test_dispatches_per_source_task(self, db):
        """每个启用来源各派发一个 sync_source_by_id 任务，法院来源带加长超时。"""
        from apps.message_hub.tasks import sync_all_sources

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("apps.core.tasking.submit_task") as mock_submit_task,
            patch("apps.message_hub.tasks.cache") as mock_cache,
        ):
            mock_cache.add.return_value = True
            mock_qs = MagicMock()
            mock_qs.values_list.return_value = [(7, "imap"), (8, "court_inbox")]
            MockSource.objects.filter.return_value = mock_qs

            assert sync_all_sources() is None
            assert mock_submit_task.call_count == 2
            first, second = mock_submit_task.call_args_list
            assert first.args == ("apps.message_hub.tasks.sync_source_by_id", 7)
            assert first.kwargs.get("timeout") is None
            assert second.args == ("apps.message_hub.tasks.sync_source_by_id", 8)
            assert second.kwargs.get("timeout") is not None  # 法院来源加长超时
