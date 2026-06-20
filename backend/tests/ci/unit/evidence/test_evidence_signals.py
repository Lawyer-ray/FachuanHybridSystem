"""Tests for evidence/signals.py - post_delete file cleanup."""

import pytest
from unittest.mock import MagicMock


@pytest.mark.django_db
class TestCleanupEvidenceItemFile:
    """Test cleanup_evidence_item_file signal handler."""

    def test_deletes_file_on_evidence_item_delete(self):
        """Signal handler deletes EvidenceItem file."""
        from apps.evidence.signals import cleanup_evidence_item_file
        from apps.evidence.models import EvidenceItem

        mock_file = MagicMock()
        mock_file.__bool__ = lambda self: True

        instance = MagicMock()
        instance.file = mock_file

        cleanup_evidence_item_file(
            sender=EvidenceItem,
            instance=instance,
        )
        mock_file.delete.assert_called_once_with(save=False)

    def test_handles_no_file(self):
        """Does nothing when file is None."""
        from apps.evidence.signals import cleanup_evidence_item_file
        from apps.evidence.models import EvidenceItem

        instance = MagicMock()
        instance.file = None

        # Should not raise
        cleanup_evidence_item_file(
            sender=EvidenceItem,
            instance=instance,
        )

    def test_handles_delete_exception(self):
        """Catches exception from file.delete."""
        from apps.evidence.signals import cleanup_evidence_item_file
        from apps.evidence.models import EvidenceItem

        mock_file = MagicMock()
        mock_file.__bool__ = lambda self: True
        mock_file.delete.side_effect = OSError("Permission denied")

        instance = MagicMock()
        instance.file = mock_file

        # Should not raise
        cleanup_evidence_item_file(
            sender=EvidenceItem,
            instance=instance,
        )

    def test_ignores_wrong_sender(self):
        """Signal handler ignores non-EvidenceItem senders."""
        from apps.evidence.signals import cleanup_evidence_item_file

        mock_file = MagicMock()

        class WrongModel:
            pass

        instance = MagicMock()
        instance.file = mock_file

        cleanup_evidence_item_file(
            sender=WrongModel,
            instance=instance,
        )
        mock_file.delete.assert_not_called()


@pytest.mark.django_db
class TestCleanupEvidenceListMergedPdf:
    """Test cleanup_evidence_list_merged_pdf signal handler."""

    def test_deletes_merged_pdf_on_evidence_list_delete(self):
        """Signal handler deletes EvidenceList merged_pdf."""
        from apps.evidence.signals import cleanup_evidence_list_merged_pdf
        from apps.evidence.models import EvidenceList

        mock_pdf = MagicMock()
        mock_pdf.__bool__ = lambda self: True

        instance = MagicMock()
        instance.merged_pdf = mock_pdf

        cleanup_evidence_list_merged_pdf(
            sender=EvidenceList,
            instance=instance,
        )
        mock_pdf.delete.assert_called_once_with(save=False)

    def test_handles_no_merged_pdf(self):
        """Does nothing when merged_pdf is None."""
        from apps.evidence.signals import cleanup_evidence_list_merged_pdf
        from apps.evidence.models import EvidenceList

        instance = MagicMock()
        instance.merged_pdf = None

        # Should not raise
        cleanup_evidence_list_merged_pdf(
            sender=EvidenceList,
            instance=instance,
        )

    def test_ignores_wrong_sender(self):
        """Signal handler ignores non-EvidenceList senders."""
        from apps.evidence.signals import cleanup_evidence_list_merged_pdf

        mock_pdf = MagicMock()

        class WrongModel:
            pass

        instance = MagicMock()
        instance.merged_pdf = mock_pdf

        cleanup_evidence_list_merged_pdf(
            sender=WrongModel,
            instance=instance,
        )
        mock_pdf.delete.assert_not_called()


@pytest.mark.django_db
class TestDeleteFileHelper:
    """Test _delete_file helper."""

    def test_deletes_field_file(self):
        """_delete_file calls delete on the field file."""
        from apps.evidence.signals import _delete_file

        mock_file = MagicMock()
        mock_file.__bool__ = lambda self: True
        _delete_file(mock_file)
        mock_file.delete.assert_called_once_with(save=False)

    def test_handles_none(self):
        """_delete_file handles None gracefully."""
        from apps.evidence.signals import _delete_file

        _delete_file(None)  # Should not raise
