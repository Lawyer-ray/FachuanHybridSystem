"""Tests for doc_converter/signals.py - post_delete file cleanup.

Note: signals.py uses relative imports from .models and DocConverterStorage,
so we import the signal handler functions via the apps.doc_converter.signals path.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestCleanupJobFiles:
    """Test _cleanup_job_files signal handler."""

    def test_deletes_output_zip_and_storage(self):
        """Deleting DocConverterJob cleans up output_zip and storage."""
        from apps.doc_converter.signals import _cleanup_job_files

        mock_zip = MagicMock()
        mock_zip.__bool__ = lambda self: True

        instance = MagicMock()
        instance.id = "test-job-id"
        instance.output_zip = mock_zip

        with (
            patch("apps.doc_converter.services.storage.DocConverterStorage") as MockStorage,
            patch("apps.doc_converter.signals.transaction") as mock_txn,
        ):
            mock_storage = MockStorage.return_value
            mock_txn.on_commit.side_effect = lambda fn: fn()

            _cleanup_job_files(sender=MagicMock, instance=instance)

            mock_zip.delete.assert_called_once_with(save=False)
            mock_storage.cleanup.assert_called_once()

    def test_handles_no_output_zip(self):
        """Handles case where output_zip is empty."""
        from apps.doc_converter.signals import _cleanup_job_files

        instance = MagicMock()
        instance.id = "test-job-id"
        instance.output_zip = MagicMock(__bool__=lambda self: False)

        with (
            patch("apps.doc_converter.services.storage.DocConverterStorage") as MockStorage,
            patch("apps.doc_converter.signals.transaction") as mock_txn,
        ):
            mock_storage = MockStorage.return_value
            mock_txn.on_commit.side_effect = lambda fn: fn()

            _cleanup_job_files(sender=MagicMock, instance=instance)

            mock_storage.cleanup.assert_called_once()

    def test_handles_output_zip_delete_exception(self):
        """Catches exception from output_zip.delete and still cleans up storage."""
        from apps.doc_converter.signals import _cleanup_job_files

        mock_zip = MagicMock()
        mock_zip.__bool__ = lambda self: True
        mock_zip.delete.side_effect = OSError("File locked")

        instance = MagicMock()
        instance.id = "test-job-id"
        instance.output_zip = mock_zip

        with (
            patch("apps.doc_converter.services.storage.DocConverterStorage") as MockStorage,
            patch("apps.doc_converter.signals.transaction") as mock_txn,
        ):
            mock_storage = MockStorage.return_value
            mock_txn.on_commit.side_effect = lambda fn: fn()

            # Should not raise
            _cleanup_job_files(sender=MagicMock, instance=instance)
            mock_storage.cleanup.assert_called_once()


class TestCleanupItemFiles:
    """Test _cleanup_item_files signal handler."""

    def test_deletes_source_and_converted_files(self):
        """Deleting DocConverterItem cleans up source and converted files."""
        from apps.doc_converter.signals import _cleanup_item_files

        mock_source = MagicMock()
        mock_source.__bool__ = lambda self: True
        mock_converted = MagicMock()
        mock_converted.__bool__ = lambda self: True

        instance = MagicMock()
        instance.id = "test-item-id"
        instance.source_file = mock_source
        instance.converted_file = mock_converted

        with patch("apps.doc_converter.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            _cleanup_item_files(sender=MagicMock, instance=instance)

        mock_source.delete.assert_called_once_with(save=False)
        mock_converted.delete.assert_called_once_with(save=False)

    def test_handles_empty_files(self):
        """Handles case where files are empty/None."""
        from apps.doc_converter.signals import _cleanup_item_files

        instance = MagicMock()
        instance.id = "test-item-id"
        instance.source_file = MagicMock(__bool__=lambda self: False)
        instance.converted_file = MagicMock(__bool__=lambda self: False)

        with patch("apps.doc_converter.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            # Should not raise
            _cleanup_item_files(sender=MagicMock, instance=instance)

    def test_handles_file_delete_exception(self):
        """Catches exception from file.delete and continues."""
        from apps.doc_converter.signals import _cleanup_item_files

        mock_source = MagicMock()
        mock_source.__bool__ = lambda self: True
        mock_source.delete.side_effect = Exception("delete failed")

        mock_converted = MagicMock()
        mock_converted.__bool__ = lambda self: True

        instance = MagicMock()
        instance.id = "test-item-id"
        instance.source_file = mock_source
        instance.converted_file = mock_converted

        with patch("apps.doc_converter.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            # Should not raise, still attempts to delete converted_file
            _cleanup_item_files(sender=MagicMock, instance=instance)
        mock_converted.delete.assert_called_once_with(save=False)
