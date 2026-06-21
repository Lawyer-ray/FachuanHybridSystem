"""Tests for chat_records/signals.py - post_delete file cleanup."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


class TestDeleteFieldFile:
    """Test _delete_field_file helper."""

    def test_deletes_file_and_prunes_empty_dirs(self):
        """File deletion triggers empty directory pruning."""
        from apps.chat_records.signals import _delete_field_file

        mock_field = MagicMock()
        mock_field.path = "/media/chat_records/test.mp4"
        mock_field.delete.return_value = None

        with patch("apps.chat_records.signals._safe_prune_empty_parents") as mock_prune:
            _delete_field_file(mock_field)
            mock_field.delete.assert_called_once_with(save=False)
            mock_prune.assert_called_once_with("/media/chat_records/test.mp4")

    def test_handles_no_field(self):
        """Does nothing when field is None/empty."""
        from apps.chat_records.signals import _delete_field_file

        # Should not raise
        _delete_field_file(None)
        _delete_field_file(MagicMock(__bool__=lambda self: False))

    def test_handles_path_exception(self):
        """Handles case where field.path raises."""
        from apps.chat_records.signals import _delete_field_file

        mock_field = MagicMock()
        type(mock_field).path = PropertyMock(side_effect=ValueError("no path"))
        mock_field.delete.return_value = None

        with patch("apps.chat_records.signals._safe_prune_empty_parents") as mock_prune:
            _delete_field_file(mock_field)
            mock_field.delete.assert_called_once_with(save=False)
            mock_prune.assert_called_once_with(None)

    def test_handles_delete_exception(self):
        """Handles case where field.delete raises."""
        from apps.chat_records.signals import _delete_field_file

        mock_field = MagicMock()
        mock_field.path = "/media/test.mp4"
        mock_field.delete.side_effect = OSError("permission denied")

        with patch("apps.chat_records.signals._safe_prune_empty_parents") as mock_prune:
            # Should not raise
            _delete_field_file(mock_field)
            mock_prune.assert_not_called()


class TestDeleteFieldFileByName:
    """Test _delete_field_file_by_name helper."""

    def test_deletes_existing_file(self):
        """Deletes file from storage when it exists."""
        from apps.chat_records.signals import _delete_field_file_by_name

        with (
            patch("django.core.files.storage.default_storage") as mock_storage,
            patch("apps.chat_records.signals._safe_prune_empty_parents"),
        ):
            mock_storage.exists.return_value = True
            mock_storage.path.return_value = "/media/chat_records/test.mp4"

            _delete_field_file_by_name("chat_records/test.mp4")
            mock_storage.exists.assert_called_once_with("chat_records/test.mp4")
            mock_storage.delete.assert_called_once_with("chat_records/test.mp4")

    def test_handles_empty_name(self):
        """Does nothing when name is empty/None."""
        from apps.chat_records.signals import _delete_field_file_by_name

        _delete_field_file_by_name(None)
        _delete_field_file_by_name("")


class TestSafePruneEmptyParents:
    """Test _safe_prune_empty_parents helper."""

    def test_returns_early_for_none_path(self):
        """Does nothing when file_path is None."""
        from apps.chat_records.signals import _safe_prune_empty_parents

        # Should not raise
        _safe_prune_empty_parents(None)

    def test_returns_early_for_empty_path(self):
        """Does nothing when file_path is empty string."""
        from apps.chat_records.signals import _safe_prune_empty_parents

        _safe_prune_empty_parents("")

    def test_returns_early_for_relative_path(self):
        """Does nothing for relative paths."""
        from apps.chat_records.signals import _safe_prune_empty_parents

        _safe_prune_empty_parents("relative/path/file.txt")

    def test_returns_early_when_not_under_media_root(self):
        """Does nothing when file is not under MEDIA_ROOT."""
        from apps.chat_records.signals import _safe_prune_empty_parents

        _safe_prune_empty_parents("/tmp/some/file.txt")


class TestSignalReceivers:
    """Test the signal receiver registrations."""

    def test_recording_post_delete_calls_delete_field_file(self):
        """ChatRecordRecording post_delete signal calls _delete_field_file with video."""
        from apps.chat_records.signals import _delete_recording_file

        instance = MagicMock()
        instance.video = MagicMock()

        with (
            patch("apps.chat_records.signals._delete_field_file") as mock_delete,
            patch("apps.chat_records.signals.transaction") as mock_txn,
        ):
            mock_txn.on_commit.side_effect = lambda fn: fn()
            _delete_recording_file(sender=MagicMock, instance=instance)
            mock_delete.assert_called_once_with(instance.video)

    def test_screenshot_post_delete_calls_delete_field_file(self):
        """ChatRecordScreenshot post_delete signal calls _delete_field_file with image."""
        from apps.chat_records.signals import _delete_screenshot_file

        instance = MagicMock()
        instance.image = MagicMock()

        with (
            patch("apps.chat_records.signals._delete_field_file") as mock_delete,
            patch("apps.chat_records.signals.transaction") as mock_txn,
        ):
            mock_txn.on_commit.side_effect = lambda fn: fn()
            _delete_screenshot_file(sender=MagicMock, instance=instance)
            mock_delete.assert_called_once_with(instance.image)

    def test_export_task_post_delete_calls_delete_field_file(self):
        """ChatRecordExportTask post_delete signal calls _delete_field_file with output_file."""
        from apps.chat_records.signals import _delete_export_file

        instance = MagicMock()
        instance.output_file = MagicMock()

        with (
            patch("apps.chat_records.signals._delete_field_file") as mock_delete,
            patch("apps.chat_records.signals.transaction") as mock_txn,
        ):
            mock_txn.on_commit.side_effect = lambda fn: fn()
            _delete_export_file(sender=MagicMock, instance=instance)
            mock_delete.assert_called_once_with(instance.output_file)

    def test_signal_handles_missing_attribute(self):
        """Signal handlers handle missing attributes gracefully."""
        from apps.chat_records.signals import _delete_recording_file, _delete_screenshot_file, _delete_export_file

        instance = MagicMock(spec=[])  # No attributes

        with (
            patch("apps.chat_records.signals._delete_field_file") as mock_delete,
            patch("apps.chat_records.signals.transaction") as mock_txn,
        ):
            mock_txn.on_commit.side_effect = lambda fn: fn()
            _delete_recording_file(sender=MagicMock, instance=instance)
            _delete_screenshot_file(sender=MagicMock, instance=instance)
            _delete_export_file(sender=MagicMock, instance=instance)
            assert mock_delete.call_count == 3
