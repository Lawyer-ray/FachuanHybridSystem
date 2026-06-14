"""Tests for smoke_check management command uncovered branches."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from django.test import Client


class TestMaybeSwitchSqliteDb:
    """Cover _maybe_switch_sqlite_db branches."""

    def _cmd(self):
        from apps.automation.management.commands.smoke_check import Command
        return Command()

    def test_none_path_returns_early(self):
        cmd = self._cmd()
        cmd._maybe_switch_sqlite_db(None)
        assert not hasattr(cmd, "_database_path") or cmd._database_path is None

    def test_non_sqlite_engine_ignored(self):
        cmd = self._cmd()
        with patch("apps.automation.management.commands.smoke_check.settings") as mock_settings:
            mock_settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql"}}
            cmd._maybe_switch_sqlite_db("/tmp/test.db")
        assert not hasattr(cmd, "_database_path") or cmd._database_path is None

    def test_sqlite_switches_db(self):
        cmd = self._cmd()
        with patch("apps.automation.management.commands.smoke_check.settings") as mock_settings, \
             patch("apps.automation.management.commands.smoke_check.connections") as mock_conn, \
             patch("apps.automation.management.commands.smoke_check.Path") as mock_path_cls:
            mock_settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3"}}
            mock_path_instance = MagicMock()
            mock_path_instance.parent = MagicMock()
            mock_path_cls.return_value = mock_path_instance
            mock_conn.all.return_value = []

            cmd._maybe_switch_sqlite_db("/tmp/test.db")


class TestEnsureSmokeSuperuser:
    """Cover _ensure_smoke_superuser branches."""

    def _cmd(self):
        from apps.automation.management.commands.smoke_check import Command
        return Command()

    def test_existing_user_not_staff(self):
        cmd = self._cmd()
        mock_user = MagicMock()
        mock_user.is_staff = False
        mock_user.save = MagicMock()

        with patch("apps.automation.management.commands.smoke_check.get_user_model") as mock_get_model:
            mock_model = MagicMock()
            mock_model.objects.filter.return_value.first.return_value = mock_user
            mock_get_model.return_value = mock_model

            result = cmd._ensure_smoke_superuser()
            mock_user.save.assert_called_once_with(update_fields=["is_staff"])

    def test_existing_user_already_staff(self):
        cmd = self._cmd()
        mock_user = MagicMock()
        mock_user.is_staff = True

        with patch("apps.automation.management.commands.smoke_check.get_user_model") as mock_get_model:
            mock_model = MagicMock()
            mock_model.objects.filter.return_value.first.return_value = mock_user
            mock_get_model.return_value = mock_model

            result = cmd._ensure_smoke_superuser()
            mock_user.save.assert_not_called()

    def test_creates_new_superuser(self):
        cmd = self._cmd()
        with patch("apps.automation.management.commands.smoke_check.get_user_model") as mock_get_model, \
             patch("apps.automation.management.commands.smoke_check.settings") as mock_settings:
            mock_model = MagicMock()
            mock_model.objects.filter.return_value.first.return_value = None
            mock_model.objects.create_superuser.return_value = "new_user"
            mock_get_model.return_value = mock_model
            mock_settings.SMOKE_ADMIN_PASSWORD = "test_pass"

            result = cmd._ensure_smoke_superuser()
            assert result == "new_user"
            mock_model.objects.create_superuser.assert_called_once()


class TestCheckAdminPages:
    """Cover _check_admin_pages."""

    def _cmd(self):
        from apps.automation.management.commands.smoke_check import Command
        return Command()

    def test_success(self):
        cmd = self._cmd()
        client = MagicMock()
        client.get.return_value = MagicMock(status_code=200)
        cmd._check_admin_pages(client)

    def test_failure_raises(self):
        from django.core.management.base import CommandError

        cmd = self._cmd()
        client = MagicMock()
        client.get.return_value = MagicMock(status_code=403)
        with pytest.raises(CommandError, match="Admin 冒烟失败"):
            cmd._check_admin_pages(client)


class TestCheckWebsocket:
    """Cover _check_websocket (should be a no-op now)."""

    def _cmd(self):
        from apps.automation.management.commands.smoke_check import Command
        return Command()

    def test_websocket_check_skipped(self):
        cmd = self._cmd()
        client = MagicMock()
        user = MagicMock()
        # Should not raise
        cmd._check_websocket(client, user)


class TestCheckDiskSpace:
    """Cover _check_disk_space branches."""

    def _cmd(self):
        from apps.automation.management.commands.smoke_check import Command
        return Command()

    def test_critical_raises(self):
        from django.core.management.base import CommandError

        cmd = self._cmd()
        cmd.stdout = MagicMock()
        with patch("apps.core.tasking.cleanup_tasks.check_disk_space") as mock_check:
            mock_check.return_value = {"status": "critical", "used_pct": 96, "available_gb": 1, "total_gb": 50}
            with pytest.raises(CommandError, match="磁盘空间严重不足"):
                cmd._check_disk_space(85.0, 95.0)

    def test_warning_prints(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        with patch("apps.core.tasking.cleanup_tasks.check_disk_space") as mock_check:
            mock_check.return_value = {"status": "warning", "used_pct": 90, "available_gb": 5, "total_gb": 50}
            cmd._check_disk_space(85.0, 95.0)
        assert cmd.stdout.write.called

    def test_ok_prints(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        with patch("apps.core.tasking.cleanup_tasks.check_disk_space") as mock_check:
            mock_check.return_value = {"status": "ok", "used_pct": 50, "available_gb": 25, "total_gb": 50}
            cmd._check_disk_space(85.0, 95.0)
        assert cmd.stdout.write.called


class TestSmokeQTask:
    """Cover smoke_q_task."""

    def test_addition(self):
        from apps.automation.management.commands.smoke_check import smoke_q_task
        assert smoke_q_task(20, 22) == 42


class TestDummyServices:
    """Cover _DummyAutoNamerService and _DummyDocumentProcessorService."""

    def test_dummy_auto_namer(self):
        from apps.automation.management.commands.smoke_check import _DummyAutoNamerService
        svc = _DummyAutoNamerService()
        file_mock = MagicMock()
        file_mock.name = "test.pdf"
        result = svc.process_document_for_naming(file_mock, None, None)
        assert result["text"] == "ok"

    def test_dummy_doc_processor(self):
        from apps.automation.management.commands.smoke_check import _DummyDocumentProcessorService
        svc = _DummyDocumentProcessorService()
        file_mock = MagicMock()
        file_mock.name = "test.pdf"
        result = svc.process_uploaded_file(file_mock)
        assert result.success is True
        assert result.file_info["name"] == "test.pdf"


class TestCheckDjangoQ:
    """_check_django_q is too tightly coupled to test in isolation.
    It spawns subprocesses and polls django-q Task objects.
    Coverage for this method is intentionally left to integration tests.
    """

    pass
