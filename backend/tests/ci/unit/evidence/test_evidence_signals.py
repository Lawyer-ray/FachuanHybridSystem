"""Tests for evidence/signals.py - post_delete file cleanup."""

from unittest.mock import MagicMock

import pytest


@pytest.mark.django_db
class TestCleanupEvidenceItemFile:
    """Test cleanup_evidence_item_file signal handler."""

    def test_deletes_file_on_evidence_item_delete(self):
        """Signal handler deletes EvidenceItem file."""
        from unittest.mock import patch as _patch

        from apps.evidence.models import EvidenceItem
        from apps.evidence.signals import cleanup_evidence_item_file

        mock_file = MagicMock()
        mock_file.__bool__ = lambda self: True

        instance = MagicMock()
        instance.file = mock_file

        with _patch("apps.evidence.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            cleanup_evidence_item_file(
                sender=EvidenceItem,
                instance=instance,
            )
        mock_file.delete.assert_called_once_with(save=False)

    def test_handles_no_file(self):
        """Does nothing when file is None."""
        from unittest.mock import patch as _patch

        from apps.evidence.models import EvidenceItem
        from apps.evidence.signals import cleanup_evidence_item_file

        instance = MagicMock()
        instance.file = None

        with (
            _patch("apps.evidence.signals.transaction") as mock_txn,
            _patch("apps.evidence.signals._delete_file") as mock_del,
        ):
            mock_txn.on_commit.side_effect = lambda fn: fn()
            # Should not raise: on_commit 回调把 None 交给 _delete_file（其内部早退）
            assert cleanup_evidence_item_file(sender=EvidenceItem, instance=instance) is None
        mock_del.assert_called_once_with(None)

    def test_handles_delete_exception(self):
        """Catches exception from file.delete."""
        from unittest.mock import patch as _patch

        from apps.evidence.models import EvidenceItem
        from apps.evidence.signals import cleanup_evidence_item_file

        mock_file = MagicMock()
        mock_file.__bool__ = lambda self: True
        mock_file.delete.side_effect = OSError("Permission denied")

        instance = MagicMock()
        instance.file = mock_file

        # on_commit 立即执行，让异常路径真正被走到
        with _patch("apps.evidence.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            # Should not raise
            assert cleanup_evidence_item_file(sender=EvidenceItem, instance=instance) is None
        mock_file.delete.assert_called_once_with(save=False)

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
        from unittest.mock import patch as _patch

        from apps.evidence.models import EvidenceList
        from apps.evidence.signals import cleanup_evidence_list_merged_pdf

        mock_pdf = MagicMock()
        mock_pdf.__bool__ = lambda self: True

        instance = MagicMock()
        instance.merged_pdf = mock_pdf

        with _patch("apps.evidence.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            cleanup_evidence_list_merged_pdf(
                sender=EvidenceList,
                instance=instance,
            )
        mock_pdf.delete.assert_called_once_with(save=False)

    def test_handles_no_merged_pdf(self):
        """Does nothing when merged_pdf is None."""
        from unittest.mock import patch as _patch

        from apps.evidence.models import EvidenceList
        from apps.evidence.signals import cleanup_evidence_list_merged_pdf

        instance = MagicMock()
        instance.merged_pdf = None

        with (
            _patch("apps.evidence.signals.transaction") as mock_txn,
            _patch("apps.evidence.signals._delete_file") as mock_del,
        ):
            mock_txn.on_commit.side_effect = lambda fn: fn()
            # Should not raise: 回调把 None 交给 _delete_file（内部早退）
            assert cleanup_evidence_list_merged_pdf(sender=EvidenceList, instance=instance) is None
        mock_del.assert_called_once_with(None)

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

        # Should not raise: falsy 早退
        assert _delete_file(None) is None
