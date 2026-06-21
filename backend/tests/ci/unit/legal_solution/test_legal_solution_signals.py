"""Tests for legal_solution/signals.py - post_delete file cleanup."""

import pytest
from unittest.mock import MagicMock, patch


class TestCleanupSolutionTaskPdf:
    """Test _cleanup_solution_task_pdf signal handler."""

    @patch("apps.legal_solution.signals.transaction")
    def test_deletes_pdf_file_on_task_delete(self, mock_txn):
        """Deleting SolutionTask cleans up PDF file."""
        from apps.legal_solution.signals import _cleanup_solution_task_pdf

        mock_txn.on_commit.side_effect = lambda fn: fn()
        mock_pdf = MagicMock()
        mock_pdf.__bool__ = lambda self: True
        mock_pdf.__str__ = lambda self: "legal_solution/report.pdf"

        instance = MagicMock()
        instance.pk = 42
        instance.pdf_file = mock_pdf

        _cleanup_solution_task_pdf(sender=MagicMock, instance=instance)
        mock_pdf.delete.assert_called_once_with(save=False)

    @patch("apps.legal_solution.signals.transaction")
    def test_handles_no_pdf_file(self, mock_txn):
        """Does nothing when pdf_file is None/empty."""
        from apps.legal_solution.signals import _cleanup_solution_task_pdf

        mock_txn.on_commit.side_effect = lambda fn: fn()
        instance = MagicMock()
        instance.pk = 42
        instance.pdf_file = None

        # Should not raise
        _cleanup_solution_task_pdf(sender=MagicMock, instance=instance)

    @patch("apps.legal_solution.signals.transaction")
    def test_handles_delete_exception(self, mock_txn):
        """Catches exception from pdf_file.delete."""
        from apps.legal_solution.signals import _cleanup_solution_task_pdf

        mock_txn.on_commit.side_effect = lambda fn: fn()
        mock_pdf = MagicMock()
        mock_pdf.__bool__ = lambda self: True
        mock_pdf.__str__ = lambda self: "legal_solution/report.pdf"
        mock_pdf.delete.side_effect = OSError("File system error")

        instance = MagicMock()
        instance.pk = 42
        instance.pdf_file = mock_pdf

        # Should not raise
        _cleanup_solution_task_pdf(sender=MagicMock, instance=instance)
