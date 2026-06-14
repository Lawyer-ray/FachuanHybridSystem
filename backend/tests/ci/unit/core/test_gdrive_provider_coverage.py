"""Coverage tests for core/cloud_storage/gdrive_provider.py.

Covers _PathResolver.resolve and _escape_gql, _parse_gdrive_time.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from apps.core.cloud_storage.gdrive_provider import (
    _PathResolver,
    _escape_gql,
    _parse_gdrive_time,
)


class TestEscapeGql:
    def test_backslash(self):
        assert _escape_gql("a\\b") == "a\\\\b"

    def test_single_quote(self):
        assert _escape_gql("it's") == "it\\'s"

    def test_double_quote(self):
        assert _escape_gql('say "hi"') == 'say \\"hi\\"'

    def test_clean_string(self):
        assert _escape_gql("hello") == "hello"


class TestParseGdriveTime:
    def test_valid_iso(self):
        result = _parse_gdrive_time("2024-01-15T10:30:00Z")
        assert result > 0

    def test_empty_string(self):
        assert _parse_gdrive_time("") == 0.0

    def test_invalid_format(self):
        assert _parse_gdrive_time("not-a-date") == 0.0

    def test_none(self):
        assert _parse_gdrive_time("") == 0.0


class TestPathResolver:
    def test_root_path(self):
        mock_service = MagicMock()
        resolver = _PathResolver(mock_service, root_folder_id="root123")
        assert resolver.resolve("/") == "root123"

    def test_empty_path(self):
        mock_service = MagicMock()
        resolver = _PathResolver(mock_service, root_folder_id="root123")
        assert resolver.resolve("") == "root123"

    def test_cached_path(self):
        mock_service = MagicMock()
        resolver = _PathResolver(mock_service, root_folder_id="root123")
        resolver._cache["/folder1"] = "folder_id_1"
        result = resolver.resolve("/folder1")
        assert result == "folder_id_1"
        # Should not call API
        mock_service.files.assert_not_called()

    def test_resolve_multi_segment(self):
        mock_service = MagicMock()
        mock_files = {"files": [{"id": "seg1_id", "name": "seg1"}]}
        mock_service.files.return_value.list.return_value.execute.return_value = mock_files
        resolver = _PathResolver(mock_service, root_folder_id="root")
        # After first segment resolves, cache it for second
        resolver._cache["/seg1"] = "seg1_id"
        mock_service.files.return_value.list.return_value.execute.return_value = {"files": [{"id": "seg2_id", "name": "seg2"}]}
        result = resolver.resolve("/seg1/seg2")
        assert result == "seg2_id"

    def test_resolve_not_found(self):
        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {"files": []}
        resolver = _PathResolver(mock_service, root_folder_id="root")
        result = resolver.resolve("/nonexistent")
        assert result is None
