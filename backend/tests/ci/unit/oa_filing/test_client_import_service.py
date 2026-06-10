"""Tests for oa_filing.client_import_service - static and property methods."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.oa_filing.services.client_import_service import ClientImportService, ImportResult


class TestImportResult:
    def test_fields(self) -> None:
        r = ImportResult(status="created", message="ok")
        assert r.status == "created"
        assert r.message == "ok"

    def test_skipped(self) -> None:
        r = ImportResult(status="skipped", message="already exists")
        assert r.status == "skipped"

    def test_error(self) -> None:
        r = ImportResult(status="error", message="db error")
        assert r.status == "error"


class TestClientImportService:
    def test_to_int_valid(self) -> None:
        assert ClientImportService._to_int("42") == 42
        assert ClientImportService._to_int(3.7) == 3
        assert ClientImportService._to_int(10) == 10

    def test_to_int_invalid(self) -> None:
        assert ClientImportService._to_int("abc") == 0
        assert ClientImportService._to_int(None) == 0
        assert ClientImportService._to_int("") == 0

    def test_credential_property(self) -> None:
        mock_session = MagicMock()
        mock_cred = MagicMock()
        mock_session.credential = mock_cred

        svc = ClientImportService.__new__(ClientImportService)
        svc._session = mock_session
        svc._credential = None

        assert svc.credential is mock_cred
        assert svc._credential is mock_cred

    def test_credential_cached(self) -> None:
        """Second access returns cached value without re-fetching."""
        mock_session = MagicMock()
        mock_cred = MagicMock()
        mock_session.credential = mock_cred

        svc = ClientImportService.__new__(ClientImportService)
        svc._session = mock_session
        svc._credential = mock_cred

        assert svc.credential is mock_cred

    def test_update_session_empty_fields(self) -> None:
        """_update_session with no fields should be a no-op."""
        svc = ClientImportService.__new__(ClientImportService)
        svc._session = MagicMock()
        svc._update_session()

    def test_update_session_updates_fields(self) -> None:
        mock_session = MagicMock()
        mock_session.pk = 42

        svc = ClientImportService.__new__(ClientImportService)
        svc._session = mock_session

        with patch("apps.oa_filing.services.client_import_service.ClientImportSession") as mock_model:
            svc._update_session(status="in_progress", phase="discovering")
            mock_model.objects.filter.assert_called_once_with(pk=42)

    def test_handle_script_progress_discovery_started(self) -> None:
        svc = ClientImportService.__new__(ClientImportService)
        svc._session = MagicMock()
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({"event": "discovery_started", "message": "开始查找"})
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args[1]
            assert call_kwargs["phase"] == "discovering"

    def test_handle_script_progress_discovery_progress(self) -> None:
        svc = ClientImportService.__new__(ClientImportService)
        svc._session = MagicMock()
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({
                "event": "discovery_progress",
                "discovered_count": 5,
                "page": 2,
                "message": "查找中",
            })
            mock_update.assert_called_once()

    def test_handle_script_progress_discovery_completed(self) -> None:
        svc = ClientImportService.__new__(ClientImportService)
        svc._session = MagicMock()
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({
                "event": "discovery_completed",
                "total_count": 10,
            })
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args[1]
            assert call_kwargs["total_count"] == 10

    def test_handle_script_progress_import_started(self) -> None:
        svc = ClientImportService.__new__(ClientImportService)
        svc._session = MagicMock()
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({
                "event": "import_started",
                "total_count": 10,
            })
            mock_update.assert_called_once()

    def test_handle_script_progress_import_progress(self) -> None:
        svc = ClientImportService.__new__(ClientImportService)
        svc._session = MagicMock()
        svc._session.total_count = 10
        svc._session.discovered_count = 10
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({
                "event": "import_progress",
                "index": 5,
                "name": "张三",
                "total_count": 10,
            })
            mock_update.assert_called_once()

    def test_handle_script_progress_unknown_event(self) -> None:
        """Unknown events should not cause errors."""
        svc = ClientImportService.__new__(ClientImportService)
        svc._session = MagicMock()
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({"event": "unknown_event"})
            mock_update.assert_not_called()
