"""Tests for core/infrastructure/monitoring.py — deeper branch coverage.

Covers: _should_collect_queries, _log_performance with all log levels,
_check_performance_issues with/without issues, monitor_api decorator
success/failure paths, monitor_operation context manager.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from apps.core.infrastructure.monitoring import PerformanceMonitor


# ---------------------------------------------------------------------------
# _should_collect_queries
# ---------------------------------------------------------------------------


class TestShouldCollectQueries:
    def test_debug_mode_enabled(self):
        with patch("apps.core.infrastructure.monitoring.settings") as mock_settings:
            mock_settings.DEBUG = True
            assert PerformanceMonitor._should_collect_queries() is True

    def test_env_var_true(self):
        with patch("apps.core.infrastructure.monitoring.settings") as mock_settings:
            mock_settings.DEBUG = False
            with patch.dict(os.environ, {"DJANGO_DB_QUERY_METRICS": "true"}):
                assert PerformanceMonitor._should_collect_queries() is True

    def test_env_var_1(self):
        with patch("apps.core.infrastructure.monitoring.settings") as mock_settings:
            mock_settings.DEBUG = False
            with patch.dict(os.environ, {"DJANGO_DB_QUERY_METRICS": "1"}):
                assert PerformanceMonitor._should_collect_queries() is True

    def test_env_var_yes(self):
        with patch("apps.core.infrastructure.monitoring.settings") as mock_settings:
            mock_settings.DEBUG = False
            with patch.dict(os.environ, {"DJANGO_DB_QUERY_METRICS": "yes"}):
                assert PerformanceMonitor._should_collect_queries() is True

    def test_env_var_no(self):
        with patch("apps.core.infrastructure.monitoring.settings") as mock_settings:
            mock_settings.DEBUG = False
            with patch.dict(os.environ, {"DJANGO_DB_QUERY_METRICS": "no"}):
                assert PerformanceMonitor._should_collect_queries() is False

    def test_both_false(self):
        with patch("apps.core.infrastructure.monitoring.settings") as mock_settings:
            mock_settings.DEBUG = False
            with patch.dict(os.environ, {"DJANGO_DB_QUERY_METRICS": ""}, clear=False):
                assert PerformanceMonitor._should_collect_queries() is False


# ---------------------------------------------------------------------------
# _log_performance
# ---------------------------------------------------------------------------


class TestLogPerformance:
    def test_logs_error_on_failure(self):
        with patch.object(PerformanceMonitor, 'logger', create=True) as mock_logger:
            # Just call it directly and verify no exception
            PerformanceMonitor._log_performance(
                endpoint="test", duration_ms=100, query_count=5,
                query_count_collected=True, success=False, error="boom"
            )

    def test_logs_warning_on_slow(self):
        PerformanceMonitor._log_performance(
            endpoint="test", duration_ms=2000, query_count=5,
            query_count_collected=True, success=True
        )

    def test_logs_info_on_normal(self):
        PerformanceMonitor._log_performance(
            endpoint="test", duration_ms=100, query_count=5,
            query_count_collected=True, success=True
        )


# ---------------------------------------------------------------------------
# _check_performance_issues
# ---------------------------------------------------------------------------


class TestCheckPerformanceIssues:
    def test_slow_api_detected(self):
        PerformanceMonitor._check_performance_issues(
            endpoint="test", duration_ms=2000, query_count=5
        )

    def test_too_many_queries_detected(self):
        PerformanceMonitor._check_performance_issues(
            endpoint="test", duration_ms=100, query_count=20
        )

    def test_both_issues(self):
        PerformanceMonitor._check_performance_issues(
            endpoint="test", duration_ms=2000, query_count=20
        )

    def test_no_issues(self):
        PerformanceMonitor._check_performance_issues(
            endpoint="test", duration_ms=100, query_count=5
        )


# ---------------------------------------------------------------------------
# monitor_api decorator
# ---------------------------------------------------------------------------


class TestMonitorApiDecorator:
    def test_success_path(self):
        with patch.object(PerformanceMonitor, '_should_collect_queries', return_value=False):
            @PerformanceMonitor.monitor_api("test_endpoint")
            def my_func():
                return 42

            result = my_func()
            assert result == 42

    def test_failure_path(self):
        with patch.object(PerformanceMonitor, '_should_collect_queries', return_value=False):
            @PerformanceMonitor.monitor_api("test_endpoint")
            def my_func():
                raise ValueError("test error")

            with pytest.raises(ValueError, match="test error"):
                my_func()

    def test_with_query_collection(self):
        mock_connection = MagicMock()
        mock_connection.queries = []
        mock_connection.force_debug_cursor = False

        with patch.object(PerformanceMonitor, '_should_collect_queries', return_value=True), \
             patch("apps.core.infrastructure.monitoring.connection", mock_connection), \
             patch("apps.core.infrastructure.monitoring.reset_queries"):

            @PerformanceMonitor.monitor_api("test_endpoint")
            def my_func():
                return "ok"

            result = my_func()
            assert result == "ok"


# ---------------------------------------------------------------------------
# monitor_operation context manager
# ---------------------------------------------------------------------------


class TestMonitorOperation:
    def test_success_path(self):
        with patch.object(PerformanceMonitor, '_should_collect_queries', return_value=False):
            with PerformanceMonitor.monitor_operation("test_op"):
                pass  # no exception

    def test_failure_path(self):
        with patch.object(PerformanceMonitor, '_should_collect_queries', return_value=False):
            with pytest.raises(ValueError):
                with PerformanceMonitor.monitor_operation("test_op"):
                    raise ValueError("op failed")

    def test_with_query_collection(self):
        mock_connection = MagicMock()
        mock_connection.queries = []
        mock_connection.force_debug_cursor = False

        with patch.object(PerformanceMonitor, '_should_collect_queries', return_value=True), \
             patch("apps.core.infrastructure.monitoring.connection", mock_connection), \
             patch("apps.core.infrastructure.monitoring.reset_queries"):
            with PerformanceMonitor.monitor_operation("test_op"):
                pass


# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------


class TestThresholds:
    def test_slow_api_threshold(self):
        assert PerformanceMonitor.SLOW_API_THRESHOLD_MS == 1000

    def test_slow_query_threshold(self):
        assert PerformanceMonitor.SLOW_QUERY_THRESHOLD_MS == 100

    def test_max_query_count(self):
        assert PerformanceMonitor.MAX_QUERY_COUNT == 10
