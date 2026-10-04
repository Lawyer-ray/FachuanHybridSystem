"""Tests for organization/signals.py - post_delete file cleanup."""

from unittest.mock import MagicMock, patch

import pytest


class TestCleanupLawyerLicensePdf:
    """Test _cleanup_lawyer_license_pdf signal handler."""

    @patch("apps.organization.signals.transaction")
    def test_deletes_license_pdf_on_lawyer_delete(self, mock_txn):
        """Deleting Lawyer cleans up license PDF."""
        from apps.organization.signals import _cleanup_lawyer_license_pdf

        mock_txn.on_commit.side_effect = lambda fn: fn()
        mock_pdf = MagicMock()
        mock_pdf.__bool__ = lambda self: True
        mock_pdf.__str__ = lambda self: "lawyers/licenses/license.pdf"

        instance = MagicMock()
        instance.pk = 1
        instance.license_pdf = mock_pdf

        _cleanup_lawyer_license_pdf(sender=MagicMock, instance=instance)
        mock_pdf.delete.assert_called_once_with(save=False)

    @patch("apps.organization.signals.transaction")
    def test_handles_no_license_pdf(self, mock_txn):
        """Does nothing when license_pdf is None/empty."""
        from apps.organization.signals import _cleanup_lawyer_license_pdf

        mock_txn.on_commit.side_effect = lambda fn: fn()
        instance = MagicMock()
        instance.pk = 1
        instance.license_pdf = None

        # Should not raise；无文件时不应调度任何清理
        assert _cleanup_lawyer_license_pdf(sender=MagicMock, instance=instance) is None
        mock_txn.on_commit.assert_not_called()

    @patch("apps.organization.signals.transaction")
    def test_handles_delete_exception(self, mock_txn):
        """Catches exception from license_pdf.delete."""
        from apps.organization.signals import _cleanup_lawyer_license_pdf

        mock_txn.on_commit.side_effect = lambda fn: fn()
        mock_pdf = MagicMock()
        mock_pdf.__bool__ = lambda self: True
        mock_pdf.__str__ = lambda self: "license.pdf"
        mock_pdf.delete.side_effect = OSError("File locked")

        instance = MagicMock()
        instance.pk = 1
        instance.license_pdf = mock_pdf

        # Should not raise（删除失败被吞掉且仍调度了清理）
        assert _cleanup_lawyer_license_pdf(sender=MagicMock, instance=instance) is None
        mock_txn.on_commit.assert_called_once()
        mock_pdf.delete.assert_called_once_with(save=False)


class TestCleanupLawyerAvatar:
    """Test _cleanup_lawyer_avatar signal handler."""

    @patch("apps.organization.signals.transaction")
    def test_deletes_avatar_on_lawyer_delete(self, mock_txn):
        """Deleting Lawyer cleans up avatar."""
        from apps.organization.signals import _cleanup_lawyer_avatar

        mock_txn.on_commit.side_effect = lambda fn: fn()
        mock_avatar = MagicMock()
        mock_avatar.__bool__ = lambda self: True
        mock_avatar.__str__ = lambda self: "avatars/avatar.jpg"

        instance = MagicMock()
        instance.pk = 1
        instance.avatar = mock_avatar

        _cleanup_lawyer_avatar(sender=MagicMock, instance=instance)
        mock_avatar.delete.assert_called_once_with(save=False)

    @patch("apps.organization.signals.transaction")
    def test_handles_no_avatar(self, mock_txn):
        """Does nothing when avatar is None/empty."""
        from apps.organization.signals import _cleanup_lawyer_avatar

        mock_txn.on_commit.side_effect = lambda fn: fn()
        instance = MagicMock()
        instance.pk = 1
        instance.avatar = None

        # Should not raise；无头像时不应调度任何清理
        assert _cleanup_lawyer_avatar(sender=MagicMock, instance=instance) is None
        mock_txn.on_commit.assert_not_called()

    @patch("apps.organization.signals.transaction")
    def test_handles_delete_exception(self, mock_txn):
        """Catches exception from avatar.delete."""
        from apps.organization.signals import _cleanup_lawyer_avatar

        mock_txn.on_commit.side_effect = lambda fn: fn()
        mock_avatar = MagicMock()
        mock_avatar.__bool__ = lambda self: True
        mock_avatar.__str__ = lambda self: "avatar.jpg"
        mock_avatar.delete.side_effect = Exception("Storage error")

        instance = MagicMock()
        instance.pk = 1
        instance.avatar = mock_avatar

        # Should not raise（删除失败被吞掉且仍调度了清理）
        assert _cleanup_lawyer_avatar(sender=MagicMock, instance=instance) is None
        mock_txn.on_commit.assert_called_once()
        mock_avatar.delete.assert_called_once_with(save=False)
