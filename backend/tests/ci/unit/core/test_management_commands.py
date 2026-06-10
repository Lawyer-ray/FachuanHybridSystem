"""Tests for core management commands."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.management.base import CommandError


class TestCheckDbPerformanceCommand:
    def test_sqlite_vendor(self) -> None:
        from apps.core.management.commands.check_db_performance import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x
        cmd.style.WARNING = lambda x: x

        mock_connection = MagicMock()
        mock_connection.vendor = "sqlite"

        # Track cursor calls to return appropriate results
        call_count = [0]
        fetchone_results = [
            [1024 * 1024],  # DB size
            [42],  # row count for test_table
        ]
        fetchall_table_results = [
            [("test_table", 2)],  # table list
        ]
        fetchall_index_results = [
            [("idx_test", "test_table", "CREATE INDEX idx_test ON test_table(id)")],
        ]

        def mock_fetchone() -> list:
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(fetchone_results):
                return fetchone_results[idx]
            return [0]

        fetchall_count = [0]
        def mock_fetchall() -> list:
            idx = fetchall_count[0]
            fetchall_count[0] += 1
            if idx == 0:
                return fetchall_table_results[0]
            if idx == 1:
                return fetchall_index_results[0]
            return []

        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone = mock_fetchone
        mock_cursor.fetchall = mock_fetchall
        mock_connection.cursor.return_value = mock_cursor

        with patch("apps.core.management.commands.check_db_performance.connection", mock_connection):
            cmd.handle()
        cmd.stdout.write.assert_called()

    def test_unsupported_vendor(self) -> None:
        from apps.core.management.commands.check_db_performance import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x
        cmd.style.WARNING = lambda x: x

        mock_connection = MagicMock()
        mock_connection.vendor = "mysql"

        with patch("apps.core.management.commands.check_db_performance.connection", mock_connection):
            cmd.handle()


class TestAnalyzePerformanceCommand:
    def test_no_log_file(self) -> None:
        from apps.core.management.commands.analyze_performance import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x
        cmd.style.WARNING = lambda x: x
        cmd.style.ERROR = lambda x: x

        cmd.handle(log_file="/nonexistent/file.log", threshold=1000, top=10, hours=24)
        cmd.stdout.write.assert_called()

    def test_parse_logs_with_data(self) -> None:
        from apps.core.management.commands.analyze_performance import Command

        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write('{"metric_type":"api_performance","path":"/api/test","method":"GET","duration_ms":150,"query_count":3,"status_code":200}\n')
            f.flush()
            cmd = Command()
            result = cmd._parse_logs(f.name, 24)
            assert "GET /api/test" in result
            assert result["GET /api/test"]["count"] == 1
            assert result["GET /api/test"]["total_time"] == 150

    def test_analyze_performance(self) -> None:
        from apps.core.management.commands.analyze_performance import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x
        cmd.style.WARNING = lambda x: x

        api_stats = {
            "GET /api/test": {
                "count": 10,
                "total_time": 5000,
                "total_queries": 30,
                "max_time": 800,
                "max_queries": 5,
                "errors": 1,
            }
        }
        cmd._analyze_performance(api_stats, threshold=1000, top_n=5)
        cmd.stdout.write.assert_called()


class TestInitSystemConfigCommand:
    @pytest.mark.django_db
    def test_handle_creates_configs(self) -> None:
        from apps.core.management.commands.init_system_config import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x

        mock_defaults = [
            {
                "key": "TEST_KEY",
                "value": "test_value",
                "category": "test",
                "description": "test desc",
                "is_secret": False,
            }
        ]

        with (
            patch("apps.core.models.SystemConfig") as mock_config,
            patch("apps.core.admin._system_config_data.get_default_configs", return_value=mock_defaults),
        ):
            mock_obj = MagicMock()
            mock_config.objects.get_or_create.return_value = (mock_obj, True)
            cmd.handle(sync_env=False, force=False, cleanup=False)
            cmd.stdout.write.assert_called()


class TestEncryptSystemConfigSecretsCommand:
    def test_no_secrets_to_encrypt(self) -> None:
        from apps.core.management.commands.encrypt_system_config_secrets import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x

        with (
            patch("apps.core.management.commands.encrypt_system_config_secrets.SystemConfig") as mock_config,
            patch("apps.core.management.commands.encrypt_system_config_secrets.SecretCodec") as mock_codec,
        ):
            mock_qs = MagicMock()
            mock_qs.exclude.return_value = mock_qs
            mock_qs.__iter__ = MagicMock(return_value=iter([]))
            mock_config.objects.filter.return_value = mock_qs

            codec_instance = MagicMock()
            mock_codec.return_value = codec_instance

            cmd.handle()
            cmd.stdout.write.assert_called()


class TestScanOrphanFilesCommand:
    def test_media_root_not_exists(self) -> None:
        from apps.core.management.commands.scan_orphan_files import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.stderr = MagicMock()
        cmd.style = MagicMock()
        cmd.style.ERROR = lambda x: x

        with patch("apps.core.management.commands.scan_orphan_files.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = "/nonexistent/media"
            cmd.handle(delete=False, older_than=0, exclude_dirs=["tmp"])
            cmd.stderr.write.assert_called()
