"""Coverage tests for core.infrastructure.health._checkers."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch, PropertyMock
from types import SimpleNamespace

import pytest


# ── check_database ────────────────────────────────────────────────────────────

class TestCheckDatabase:
    @patch("apps.core.infrastructure.health._checkers.connection")
    @patch("apps.core.infrastructure.health._checkers.settings")
    def test_healthy_sqlite(self, mock_settings, mock_conn):
        from apps.core.infrastructure.health._checkers import check_database
        from apps.core.infrastructure.health._models import HealthStatus

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.vendor = "sqlite"
        mock_conn.queries = []

        mock_settings.DATABASES = {"default": {"NAME": "/tmp/test.db"}}
        mock_settings.CACHES = {"default": {}}

        with patch("apps.core.infrastructure.health._checkers.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.stat.return_value = SimpleNamespace(st_size=1024 * 1024, st_mtime=100000)
            MockPath.return_value = mock_path

            with patch("apps.core.infrastructure.health._checkers.os.access", return_value=True):
                result = check_database()

        assert result.status == HealthStatus.HEALTHY
        assert result.name == "database"
        assert "database_path" in result.diagnostic_info

    @patch("apps.core.infrastructure.health._checkers.connection")
    @patch("apps.core.infrastructure.health._checkers.settings")
    def test_healthy_non_sqlite(self, mock_settings, mock_conn):
        from apps.core.infrastructure.health._checkers import check_database
        from apps.core.infrastructure.health._models import HealthStatus

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.vendor = "postgresql"
        mock_conn.queries = []

        mock_settings.DATABASES = {"default": {"NAME": "mydb", "HOST": "localhost", "PORT": 5432}}

        result = check_database()
        assert result.status == HealthStatus.HEALTHY
        assert result.diagnostic_info.get("database_name") == "mydb"

    @patch("apps.core.infrastructure.health._checkers.connection")
    @patch("apps.core.infrastructure.health._checkers.settings")
    def test_unhealthy_db_error_sqlite(self, mock_settings, mock_conn):
        from apps.core.infrastructure.health._checkers import check_database
        from apps.core.infrastructure.health._models import HealthStatus

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("connection refused")
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.vendor = "sqlite"
        mock_settings.DATABASES = {"default": {"NAME": "/tmp/test.db"}}

        with patch("apps.core.infrastructure.health._checkers.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_path.parent = MagicMock()
            mock_path.parent.exists.return_value = True
            MockPath.return_value = mock_path

            with patch("apps.core.infrastructure.health._checkers.os.access", return_value=True):
                result = check_database()

        assert result.status == HealthStatus.UNHEALTHY
        assert "connection refused" in result.message

    @patch("apps.core.infrastructure.health._checkers.connection")
    @patch("apps.core.infrastructure.health._checkers.settings")
    def test_unhealthy_db_error_non_sqlite(self, mock_settings, mock_conn):
        from apps.core.infrastructure.health._checkers import check_database
        from apps.core.infrastructure.health._models import HealthStatus

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("pg down")
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.vendor = "postgresql"
        mock_settings.DATABASES = {"default": {"NAME": "mydb", "HOST": "db-host", "PORT": 5432}}

        result = check_database()
        assert result.status == HealthStatus.UNHEALTHY
        assert result.diagnostic_info.get("database_host") == "db-host"

    @patch("apps.core.infrastructure.health._checkers.connection")
    @patch("apps.core.infrastructure.health._checkers.settings")
    def test_healthy_sqlite_file_not_exists(self, mock_settings, mock_conn):
        from apps.core.infrastructure.health._checkers import check_database
        from apps.core.infrastructure.health._models import HealthStatus

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.vendor = "sqlite"
        mock_conn.queries = []
        mock_settings.DATABASES = {"default": {"NAME": "/tmp/nonexistent.db"}}

        with patch("apps.core.infrastructure.health._checkers.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path
            result = check_database()

        assert result.status == HealthStatus.HEALTHY

    @patch("apps.core.infrastructure.health._checkers.connection")
    @patch("apps.core.infrastructure.health._checkers.settings")
    def test_healthy_diagnostic_error(self, mock_settings, mock_conn):
        from apps.core.infrastructure.health._checkers import check_database
        from apps.core.infrastructure.health._models import HealthStatus

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.vendor = "sqlite"
        mock_conn.queries = []
        type(mock_settings).DATABASES = PropertyMock(side_effect=Exception("bad config"))

        result = check_database()
        assert result.status == HealthStatus.HEALTHY
        assert "diagnostic_error" in result.diagnostic_info

    @patch("apps.core.infrastructure.health._checkers.connection")
    @patch("apps.core.infrastructure.health._checkers.settings")
    def test_unhealthy_sqlite_with_parent_dir(self, mock_settings, mock_conn):
        from apps.core.infrastructure.health._checkers import check_database
        from apps.core.infrastructure.health._models import HealthStatus

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("db error")
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.vendor = "sqlite"
        mock_settings.DATABASES = {"default": {"NAME": "/data/test.db"}}

        with patch("apps.core.infrastructure.health._checkers.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_parent = MagicMock()
            mock_parent.exists.return_value = True
            mock_path.parent = mock_parent
            MockPath.return_value = mock_path

            with patch("apps.core.infrastructure.health._checkers.os.access", return_value=True):
                result = check_database()

        assert result.status == HealthStatus.UNHEALTHY
        assert "path_exists" in result.diagnostic_info

    @patch("apps.core.infrastructure.health._checkers.connection")
    @patch("apps.core.infrastructure.health._checkers.settings")
    def test_unhealthy_diagnostic_collection_error(self, mock_settings, mock_conn):
        from apps.core.infrastructure.health._checkers import check_database
        from apps.core.infrastructure.health._models import HealthStatus

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("db error")
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.vendor = "sqlite"
        type(mock_settings).DATABASES = PropertyMock(side_effect=Exception("conf err"))

        result = check_database()
        assert result.status == HealthStatus.UNHEALTHY
        assert "diagnostic_collection_error" in result.diagnostic_info


# ── check_cache ──────────────────────────────────────────────────────────────

class TestCheckCache:
    @patch("apps.core.infrastructure.health._checkers.cache")
    @patch("apps.core.infrastructure.health._checkers.settings")
    def test_healthy_cache(self, mock_settings, mock_cache):
        from apps.core.infrastructure.health._checkers import check_cache
        from apps.core.infrastructure.health._models import HealthStatus

        mock_settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "test"}}
        mock_cache.get.return_value = "ok"

        result = check_cache()
        assert result.status == HealthStatus.HEALTHY
        assert result.name == "cache"

    @patch("apps.core.infrastructure.health._checkers.cache")
    @patch("apps.core.infrastructure.health._checkers.settings")
    def test_degraded_cache_mismatch(self, mock_settings, mock_cache):
        from apps.core.infrastructure.health._checkers import check_cache
        from apps.core.infrastructure.health._models import HealthStatus

        mock_settings.CACHES = {"default": {"BACKEND": "locmem", "LOCATION": ""}}
        mock_cache.get.return_value = "wrong_value"

        result = check_cache()
        assert result.status == HealthStatus.DEGRADED
        assert "mismatch" in result.message.lower()

    @patch("apps.core.infrastructure.health._checkers.cache")
    @patch("apps.core.infrastructure.health._checkers.settings")
    def test_cache_exception(self, mock_settings, mock_cache):
        from apps.core.infrastructure.health._checkers import check_cache
        from apps.core.infrastructure.health._models import HealthStatus

        mock_settings.CACHES = {"default": {"BACKEND": "locmem"}}
        mock_cache.set.side_effect = Exception("cache down")

        result = check_cache()
        assert result.status == HealthStatus.DEGRADED
        assert "cache down" in result.message


# ── check_disk_space ──────────────────────────────────────────────────────────

class TestCheckDiskSpace:
    @patch("apps.core.infrastructure.health._checkers.connection")
    @patch("apps.core.infrastructure.health._checkers.settings")
    @patch("apps.core.infrastructure.health._checkers.os.statvfs")
    def test_healthy_disk(self, mock_statvfs, mock_settings, mock_conn):
        from apps.core.infrastructure.health._checkers import check_disk_space
        from apps.core.infrastructure.health._models import HealthStatus

        stat_result = SimpleNamespace(
            f_blocks=1000, f_frsize=4096, f_bavail=500, f_files=10000, f_ffree=5000
        )
        mock_statvfs.return_value = stat_result
        mock_settings.MEDIA_ROOT = "/tmp"
        mock_settings.STATIC_ROOT = "/tmp/static"
        mock_conn.vendor = "sqlite"
        mock_settings.DATABASES = {"default": {"NAME": "/tmp/test.db"}}

        with patch("apps.core.infrastructure.health._checkers.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_path.parent = MagicMock()
            mock_path.parent.exists.return_value = False
            MockPath.return_value = mock_path
            result = check_disk_space()

        assert result.status == HealthStatus.HEALTHY
        assert result.name == "disk"

    @patch("apps.core.infrastructure.health._checkers.settings")
    @patch("apps.core.infrastructure.health._checkers.os.statvfs")
    def test_degraded_disk(self, mock_statvfs, mock_settings):
        from apps.core.infrastructure.health._checkers import check_disk_space
        from apps.core.infrastructure.health._models import HealthStatus

        stat_result = SimpleNamespace(
            f_blocks=1000, f_frsize=4096, f_bavail=150, f_files=10000, f_ffree=1000
        )
        mock_statvfs.return_value = stat_result
        mock_settings.MEDIA_ROOT = "/tmp"

        result = check_disk_space()
        assert result.status == HealthStatus.DEGRADED

    @patch("apps.core.infrastructure.health._checkers.settings")
    @patch("apps.core.infrastructure.health._checkers.os.statvfs")
    def test_unhealthy_disk(self, mock_statvfs, mock_settings):
        from apps.core.infrastructure.health._checkers import check_disk_space
        from apps.core.infrastructure.health._models import HealthStatus

        stat_result = SimpleNamespace(
            f_blocks=1000, f_frsize=4096, f_bavail=50, f_files=10000, f_ffree=100
        )
        mock_statvfs.return_value = stat_result
        mock_settings.MEDIA_ROOT = "/tmp"

        result = check_disk_space()
        assert result.status == HealthStatus.UNHEALTHY

    @patch("apps.core.infrastructure.health._checkers.settings")
    @patch("apps.core.infrastructure.health._checkers.os.statvfs")
    def test_disk_check_exception(self, mock_statvfs, mock_settings):
        from apps.core.infrastructure.health._checkers import check_disk_space
        from apps.core.infrastructure.health._models import HealthStatus

        mock_statvfs.side_effect = OSError("permission denied")
        mock_settings.MEDIA_ROOT = "/no/such/path"

        result = check_disk_space()
        assert result.status == HealthStatus.DEGRADED
        assert "permission denied" in result.message

    @patch("apps.core.infrastructure.health._checkers.connection")
    @patch("apps.core.infrastructure.health._checkers.settings")
    @patch("apps.core.infrastructure.health._checkers.os.statvfs")
    def test_disk_with_important_paths_error(self, mock_statvfs, mock_settings, mock_conn):
        from apps.core.infrastructure.health._checkers import check_disk_space
        from apps.core.infrastructure.health._models import HealthStatus

        stat_result = SimpleNamespace(
            f_blocks=1000, f_frsize=4096, f_bavail=500, f_files=10000, f_ffree=5000
        )
        mock_statvfs.return_value = stat_result
        mock_settings.MEDIA_ROOT = "/tmp"
        mock_settings.STATIC_ROOT = "/tmp/static"
        mock_conn.vendor = "sqlite"
        mock_settings.DATABASES = {"default": {"NAME": "/tmp/test.db"}}

        call_count = 0

        def statvfs_side_effect(path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return stat_result
            raise OSError("statvfs error")

        mock_statvfs.side_effect = statvfs_side_effect

        with patch("apps.core.infrastructure.health._checkers.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            MockPath.return_value = mock_path
            result = check_disk_space()

        assert result.status == HealthStatus.HEALTHY

    @patch("apps.core.infrastructure.health._checkers.settings")
    @patch("apps.core.infrastructure.health._checkers.os.statvfs")
    def test_disk_total_zero(self, mock_statvfs, mock_settings):
        from apps.core.infrastructure.health._checkers import check_disk_space
        from apps.core.infrastructure.health._models import HealthStatus

        stat_result = SimpleNamespace(
            f_blocks=0, f_frsize=4096, f_bavail=0, f_files=0, f_ffree=0
        )
        mock_statvfs.return_value = stat_result
        mock_settings.MEDIA_ROOT = "/tmp"

        result = check_disk_space()
        assert result.status == HealthStatus.HEALTHY
        assert result.details["used_percent"] == 0.0


# ── check_dependencies ────────────────────────────────────────────────────────

class TestCheckDependencies:
    @patch("apps.core.infrastructure.health._checkers.os")
    def test_dependencies_exception(self, mock_os):
        from apps.core.infrastructure.health._checkers import check_dependencies
        from apps.core.infrastructure.health._models import HealthStatus

        mock_os.environ.get.side_effect = Exception("env error")

        result = check_dependencies()
        assert result.status == HealthStatus.DEGRADED
        assert "env error" in result.message

    def test_healthy_with_real_env(self):
        from apps.core.infrastructure.health._checkers import check_dependencies
        from apps.core.infrastructure.health._models import HealthStatus

        # This test uses the real environment (DJANGO_SECRET_KEY is set by conftest)
        result = check_dependencies()
        # Status depends on environment (HEALTHY/DEGRADED/UNHEALTHY all valid)
        assert result.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY)
        assert "environment_variables" in result.diagnostic_info
        assert "important_paths" in result.diagnostic_info
        assert "installed_apps" in result.diagnostic_info

    def test_diagnostic_info_structure(self):
        from apps.core.infrastructure.health._checkers import check_dependencies

        result = check_dependencies()
        env_vars = result.diagnostic_info.get("environment_variables", {})
        assert "DJANGO_SECRET_KEY" in env_vars
        assert "set" in env_vars["DJANGO_SECRET_KEY"]
        assert "empty" in env_vars["DJANGO_SECRET_KEY"]
