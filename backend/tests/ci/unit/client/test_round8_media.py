"""Tests for client media utils, document type resolution, and other helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.client.utils.media import resolve_media_url, _get_media_root


# ---------------------------------------------------------------------------
# _get_media_root
# ---------------------------------------------------------------------------


class TestGetMediaRoot:
    def test_returns_paths(self):
        import apps.client.utils.media as mod

        # Reset cache
        mod._cached_media_root = None
        mod._cached_media_url = None
        with patch.object(mod, "settings") as mock_settings:
            mock_settings.MEDIA_ROOT = "/tmp/media"
            mock_settings.MEDIA_URL = "/media/"
            root, root_str, media_url = _get_media_root()
            assert root == Path("/tmp/media")
            assert root_str == "/tmp/media"
            assert media_url == "/media/"

    def test_cached(self):
        import apps.client.utils.media as mod

        mod._cached_media_root = Path("/cached")
        mod._cached_media_root_str = "/cached"
        mod._cached_media_url = "/cached/"
        root, root_str, media_url = _get_media_root()
        assert root == Path("/cached")
        assert media_url == "/cached/"
        # Reset
        mod._cached_media_root = None
        mod._cached_media_url = None


# ---------------------------------------------------------------------------
# resolve_media_url
# ---------------------------------------------------------------------------


class TestResolveMediaUrl:
    def test_empty(self):
        assert resolve_media_url("") is None
        assert resolve_media_url.__wrapped__("") is None

    def test_relative_path(self):
        import apps.client.utils.media as mod

        mod._cached_media_root = None
        mod._cached_media_url = None
        with patch.object(mod, "settings") as mock_settings:
            mock_settings.MEDIA_ROOT = "/tmp/media"
            mock_settings.MEDIA_URL = "/media/"
            result = resolve_media_url.__wrapped__("uploads/file.pdf")
            assert result == "/media/uploads/file.pdf"

    def test_absolute_in_media_root(self):
        import apps.client.utils.media as mod

        mod._cached_media_root = None
        mod._cached_media_url = None
        with patch.object(mod, "settings") as mock_settings:
            mock_settings.MEDIA_ROOT = "/tmp/media"
            mock_settings.MEDIA_URL = "/media/"
            result = resolve_media_url.__wrapped__("/tmp/media/uploads/file.pdf")
            assert result == "/media/uploads/file.pdf"

    def test_absolute_outside_media_root(self):
        import apps.client.utils.media as mod

        mod._cached_media_root = None
        mod._cached_media_url = None
        with patch.object(mod, "settings") as mock_settings:
            mock_settings.MEDIA_ROOT = "/tmp/media"
            mock_settings.MEDIA_URL = "/media/"
            result = resolve_media_url.__wrapped__("/other/path/file.pdf")
            assert result is None

    def test_exception(self):
        import apps.client.utils.media as mod

        mod._cached_media_root = None
        mod._cached_media_url = None
        with patch.object(mod, "settings") as mock_settings:
            mock_settings.MEDIA_ROOT = 123  # Invalid type
            mock_settings.MEDIA_URL = "/media/"
            result = resolve_media_url.__wrapped__("test.pdf")
            assert result is None
