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
        from plugins.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(socket.gaierror("Name resolution failed")) is True

    def test_identifies_timeout_error(self):
        """Timeout errors are expected."""
        from plugins.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(TimeoutError("Connection timed out")) is True

    def test_identifies_connection_error(self):
        """Connection errors are expected."""
        from plugins.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(ConnectionError("Connection refused")) is True

    def test_identifies_err_internet_disconnected(self):
        """Internet disconnected errors are expected."""
        from plugins.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(Exception("ERR_INTERNET_DISCONNECTED")) is True

    def test_identifies_greenlet_error(self):
        """Greenlet errors are expected."""
        from plugins.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(Exception("greenlet.error: cannot switch")) is True

    def test_identifies_target_closed(self):
        """Target closed errors are expected."""
        from plugins.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(Exception("Target closed")) is True

    def test_identifies_browser_closed(self):
        """Browser closed errors are expected."""
        from plugins.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(Exception("Browser has been closed")) is True

    def test_rejects_unexpected_error(self):
        """Unexpected errors are not expected."""
        from plugins.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(ValueError("Some unexpected error")) is False

    def test_rejects_generic_runtime_error(self):
        """Generic runtime errors are not expected."""
        from plugins.message_hub.tasks import _is_expected_sync_error

        assert _is_expected_sync_error(RuntimeError("Something went wrong")) is False


class TestSyncSourceById:
    """Test sync_source_by_id task."""

    def test_syncs_single_source(self, db):
        """Fetches new messages from a single source."""
        from plugins.message_hub.tasks import sync_source_by_id

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("plugins.message_hub.services.get_fetcher") as mock_get_fetcher,
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
        from plugins.message_hub.tasks import sync_all_sources

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("django_q.tasks.async_task") as mock_async_task,
        ):
            mock_qs = MagicMock()
            mock_qs.values_list.return_value = [1, 2, 3]
            MockSource.objects.filter.return_value = mock_qs

            sync_all_sources()

            assert mock_async_task.call_count == 3
            mock_async_task.assert_any_call(
                "plugins.message_hub.tasks.sync_source_by_id", 1, q_options={"group": "message_hub"}
            )

    def test_handles_not_implemented_source(self, db):
        """Skips sources that raise NotImplementedError."""
        from plugins.message_hub.tasks import sync_all_sources

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("plugins.message_hub.services.get_fetcher") as mock_get_fetcher,
        ):
            mock_source = MagicMock()
            mock_source.display_name = "Unsupported Source"
            mock_source.source_type = "unknown"
            MockSource.objects.filter.return_value.select_related.return_value = [mock_source]

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_new_messages.side_effect = NotImplementedError("Not supported")
            mock_get_fetcher.return_value = mock_fetcher

            # Should not raise
            sync_all_sources()

    def test_handles_expected_network_error(self, db):
        """Logs warning for expected network errors."""
        from plugins.message_hub.tasks import sync_all_sources

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("plugins.message_hub.services.get_fetcher") as mock_get_fetcher,
        ):
            mock_source = MagicMock()
            mock_source.display_name = "Flaky Source"
            MockSource.objects.filter.return_value.select_related.return_value = [mock_source]

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_new_messages.side_effect = ConnectionError("Connection refused")
            mock_get_fetcher.return_value = mock_fetcher

            # Should not raise
            sync_all_sources()

    def test_handles_unexpected_error(self, db):
        """Logs exception for unexpected errors."""
        from plugins.message_hub.tasks import sync_all_sources

        with (
            patch("apps.message_hub.models.MessageSource") as MockSource,
            patch("plugins.message_hub.services.get_fetcher") as mock_get_fetcher,
        ):
            mock_source = MagicMock()
            mock_source.display_name = "Broken Source"
            MockSource.objects.filter.return_value.select_related.return_value = [mock_source]

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_new_messages.side_effect = RuntimeError("Unexpected error")
            mock_get_fetcher.return_value = mock_fetcher

            # Should not raise
            sync_all_sources()
