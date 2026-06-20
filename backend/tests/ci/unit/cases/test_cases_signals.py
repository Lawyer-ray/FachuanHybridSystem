"""Tests for cases/signals.py - post_delete file cleanup."""

import pytest
from unittest.mock import MagicMock


@pytest.mark.django_db
class TestCleanupLogAttachmentFile:
    """Test _cleanup_log_attachment_file signal handler."""

    def test_deletes_file_on_attachment_delete(self):
        """Deleting CaseLogAttachment triggers physical file deletion."""
        from unittest.mock import patch as _patch

        from apps.cases.signals import _cleanup_log_attachment_file

        mock_file = MagicMock()
        mock_file.__bool__ = lambda self: True
        mock_file.__str__ = lambda self: "test.pdf"

        instance = MagicMock()
        instance.pk = 1
        instance.file = mock_file

        with _patch("apps.cases.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            _cleanup_log_attachment_file(sender=MagicMock, instance=instance)
        mock_file.delete.assert_called_once_with(save=False)

    def test_handles_no_file_gracefully(self):
        """Signal handler does nothing when file is empty/None."""
        from apps.cases.signals import _cleanup_log_attachment_file

        instance = MagicMock()
        instance.pk = 1
        instance.file = None

        # Should not raise
        _cleanup_log_attachment_file(sender=MagicMock, instance=instance)

    def test_handles_file_delete_exception(self):
        """Signal handler catches exceptions during file deletion."""
        from apps.cases.signals import _cleanup_log_attachment_file

        mock_file = MagicMock()
        mock_file.__bool__ = lambda self: True
        mock_file.__str__ = lambda self: "test.pdf"
        mock_file.delete.side_effect = OSError("Permission denied")

        instance = MagicMock()
        instance.pk = 1
        instance.file = mock_file

        # Should not raise
        _cleanup_log_attachment_file(sender=MagicMock, instance=instance)


@pytest.mark.django_db
class TestCleanupCaseNumberDocumentFile:
    """Test _cleanup_case_number_document_file signal handler."""

    def test_deletes_document_file_on_case_number_delete(self):
        """Deleting CaseNumber triggers document file deletion."""
        from unittest.mock import patch as _patch

        from apps.cases.signals import _cleanup_case_number_document_file

        mock_file = MagicMock()
        mock_file.__bool__ = lambda self: True
        mock_file.__str__ = lambda self: "judgment.pdf"

        instance = MagicMock()
        instance.pk = 1
        instance.document_file = mock_file

        with _patch("apps.cases.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            _cleanup_case_number_document_file(sender=MagicMock, instance=instance)
        mock_file.delete.assert_called_once_with(save=False)

    def test_handles_no_document_file(self):
        """Signal handler does nothing when document_file is None."""
        from apps.cases.signals import _cleanup_case_number_document_file

        instance = MagicMock()
        instance.pk = 1
        instance.document_file = None

        # Should not raise
        _cleanup_case_number_document_file(sender=MagicMock, instance=instance)

    def test_handles_document_file_delete_exception(self):
        """Signal handler catches exceptions during document file deletion."""
        from apps.cases.signals import _cleanup_case_number_document_file

        mock_file = MagicMock()
        mock_file.__bool__ = lambda self: True
        mock_file.__str__ = lambda self: "judgment.pdf"
        mock_file.delete.side_effect = Exception("File system error")

        instance = MagicMock()
        instance.pk = 1
        instance.document_file = mock_file

        # Should not raise
        _cleanup_case_number_document_file(sender=MagicMock, instance=instance)
