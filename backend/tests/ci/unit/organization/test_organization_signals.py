"""Tests for organization/signals.py - post_delete file cleanup."""

import pytest
from unittest.mock import MagicMock


class TestCleanupLawyerLicensePdf:
    """Test _cleanup_lawyer_license_pdf signal handler."""

    def test_deletes_license_pdf_on_lawyer_delete(self):
        """Deleting Lawyer cleans up license PDF."""
        from apps.organization.signals import _cleanup_lawyer_license_pdf

        mock_pdf = MagicMock()
        mock_pdf.__bool__ = lambda self: True
        mock_pdf.__str__ = lambda self: "lawyers/licenses/license.pdf"

        instance = MagicMock()
        instance.pk = 1
        instance.license_pdf = mock_pdf

        _cleanup_lawyer_license_pdf(sender=MagicMock, instance=instance)
        mock_pdf.delete.assert_called_once_with(save=False)

    def test_handles_no_license_pdf(self):
        """Does nothing when license_pdf is None/empty."""
        from apps.organization.signals import _cleanup_lawyer_license_pdf

        instance = MagicMock()
        instance.pk = 1
        instance.license_pdf = None

        # Should not raise
        _cleanup_lawyer_license_pdf(sender=MagicMock, instance=instance)

    def test_handles_delete_exception(self):
        """Catches exception from license_pdf.delete."""
        from apps.organization.signals import _cleanup_lawyer_license_pdf

        mock_pdf = MagicMock()
        mock_pdf.__bool__ = lambda self: True
        mock_pdf.__str__ = lambda self: "license.pdf"
        mock_pdf.delete.side_effect = OSError("File locked")

        instance = MagicMock()
        instance.pk = 1
        instance.license_pdf = mock_pdf

        # Should not raise
        _cleanup_lawyer_license_pdf(sender=MagicMock, instance=instance)


class TestCleanupLawyerAvatar:
    """Test _cleanup_lawyer_avatar signal handler."""

    def test_deletes_avatar_on_lawyer_delete(self):
        """Deleting Lawyer cleans up avatar."""
        from apps.organization.signals import _cleanup_lawyer_avatar

        mock_avatar = MagicMock()
        mock_avatar.__bool__ = lambda self: True
        mock_avatar.__str__ = lambda self: "avatars/avatar.jpg"

        instance = MagicMock()
        instance.pk = 1
        instance.avatar = mock_avatar

        _cleanup_lawyer_avatar(sender=MagicMock, instance=instance)
        mock_avatar.delete.assert_called_once_with(save=False)

    def test_handles_no_avatar(self):
        """Does nothing when avatar is None/empty."""
        from apps.organization.signals import _cleanup_lawyer_avatar

        instance = MagicMock()
        instance.pk = 1
        instance.avatar = None

        # Should not raise
        _cleanup_lawyer_avatar(sender=MagicMock, instance=instance)

    def test_handles_delete_exception(self):
        """Catches exception from avatar.delete."""
        from apps.organization.signals import _cleanup_lawyer_avatar

        mock_avatar = MagicMock()
        mock_avatar.__bool__ = lambda self: True
        mock_avatar.__str__ = lambda self: "avatar.jpg"
        mock_avatar.delete.side_effect = Exception("Storage error")

        instance = MagicMock()
        instance.pk = 1
        instance.avatar = mock_avatar

        # Should not raise
        _cleanup_lawyer_avatar(sender=MagicMock, instance=instance)
