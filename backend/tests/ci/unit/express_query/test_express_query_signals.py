"""Tests for express_query/signals.py - post_delete file cleanup."""

import pytest
from unittest.mock import MagicMock, patch


class TestDeleteTaskFiles:
    """Test delete_task_files signal handler."""

    def test_deletes_waybill_and_result_files(self):
        """Deleting ExpressQueryTask cleans up both waybill_image and result_pdf."""
        from apps.express_query.signals import delete_task_files

        mock_waybill = MagicMock()
        mock_waybill.name = "waybill.jpg"
        mock_waybill.delete = MagicMock()

        mock_pdf = MagicMock()
        mock_pdf.name = "result.pdf"
        mock_pdf.delete = MagicMock()

        instance = MagicMock()
        instance.waybill_image = mock_waybill
        instance.result_pdf = mock_pdf

        with patch("apps.express_query.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            delete_task_files(sender=MagicMock, instance=instance)

        mock_waybill.delete.assert_called_once_with(save=False)
        mock_pdf.delete.assert_called_once_with(save=False)

    def test_handles_empty_file_fields(self):
        """Handles case where file fields are empty/None."""
        from apps.express_query.signals import delete_task_files

        instance = MagicMock()
        instance.waybill_image = None
        instance.result_pdf = None

        with patch("apps.express_query.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            # Should not raise
            delete_task_files(sender=MagicMock, instance=instance)

    def test_handles_file_not_found(self):
        """Handles FileNotFoundError gracefully."""
        from apps.express_query.signals import delete_task_files

        mock_waybill = MagicMock()
        mock_waybill.name = "waybill.jpg"
        mock_waybill.delete.side_effect = FileNotFoundError("File not found")

        mock_pdf = MagicMock()
        mock_pdf.name = "result.pdf"

        instance = MagicMock()
        instance.waybill_image = mock_waybill
        instance.result_pdf = mock_pdf

        with patch("apps.express_query.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            # Should not raise
            delete_task_files(sender=MagicMock, instance=instance)
        mock_pdf.delete.assert_called_once_with(save=False)


class TestSafeDeleteFileField:
    """Test _safe_delete_file_field helper."""

    def test_deletes_file_with_name(self):
        """Deletes file when it has a name."""
        from apps.express_query.signals import _safe_delete_file_field

        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.delete = MagicMock()

        _safe_delete_file_field(mock_file, "test description")
        mock_file.delete.assert_called_once_with(save=False)

    def test_skips_none_field(self):
        """Skips None field."""
        from apps.express_query.signals import _safe_delete_file_field

        _safe_delete_file_field(None, "test description")  # Should not raise

    def test_skips_field_without_name(self):
        """Skips field without name attribute."""
        from apps.express_query.signals import _safe_delete_file_field

        mock_file = type("NoName", (), {})()
        _safe_delete_file_field(mock_file, "test description")

    def test_skips_field_with_empty_name(self):
        """Skips field with empty name."""
        from apps.express_query.signals import _safe_delete_file_field

        mock_file = MagicMock()
        mock_file.name = ""
        _safe_delete_file_field(mock_file, "test description")

    def test_handles_generic_exception(self):
        """Handles generic exceptions during deletion."""
        from apps.express_query.signals import _safe_delete_file_field

        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.delete.side_effect = Exception("unexpected error")

        # Should not raise
        _safe_delete_file_field(mock_file, "test description")
