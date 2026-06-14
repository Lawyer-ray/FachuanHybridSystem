"""Tests for optimize_token_performance management command uncovered branches."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOptimizeTokenPerformanceCommand:
    """Cover branches in optimize_token_performance command."""

    def _cmd(self):
        from apps.automation.management.commands.optimize_token_performance import Command
        return Command()

    def test_task_cleanup_history_positive_days(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"cleanup_days": 30}

        with patch("apps.automation.management.commands.optimize_token_performance.history_recorder") as mock_rec:
            mock_rec.cleanup_old_records = AsyncMock(return_value=5)
            asyncio.run(cmd._task_cleanup_history(options))
        cmd.stdout.write.assert_any_call("正在清理历史记录...")

    def test_task_cleanup_history_zero_days_skips(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"cleanup_days": 0}
        asyncio.run(cmd._task_cleanup_history(options))
        # Should not write anything
        cmd.stdout.write.assert_not_called()

    def test_task_cleanup_history_exception(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"cleanup_days": 30}

        with patch("apps.automation.management.commands.optimize_token_performance.history_recorder") as mock_rec:
            mock_rec.cleanup_old_records = AsyncMock(side_effect=Exception("db error"))
            asyncio.run(cmd._task_cleanup_history(options))
        # Should print error
        assert any("失败" in str(c) for c in cmd.stdout.write.call_args_list)

    def test_task_warm_cache_none_skips(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"warm_cache": None}
        asyncio.run(cmd._task_warm_cache(options))
        cmd.stdout.write.assert_not_called()

    def test_task_warm_cache_with_sites(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"warm_cache": ["site_a", "site_b"]}

        with patch("apps.automation.management.commands.optimize_token_performance.cache_manager") as mock_cache:
            asyncio.run(cmd._task_warm_cache(options))
        assert cmd.stdout.write.call_count >= 2

    def test_task_warm_cache_exception(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"warm_cache": ["site_a"]}

        with patch("apps.automation.management.commands.optimize_token_performance.cache_manager") as mock_cache:
            mock_cache.warm_up_cache.side_effect = Exception("cache error")
            asyncio.run(cmd._task_warm_cache(options))
        assert any("失败" in str(c) for c in cmd.stdout.write.call_args_list)

    def test_task_health_check_disabled(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"health_check": False}
        cmd._task_health_check(options)
        cmd.stdout.write.assert_not_called()

    def test_task_health_check_healthy(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"health_check": True}

        with patch("apps.automation.management.commands.optimize_token_performance.performance_monitor") as mock_perf:
            mock_perf.check_health.return_value = {
                "status": "healthy",
                "alerts": [],
                "metrics": {
                    "success_rate": 95.0,
                    "avg_duration": 2.5,
                    "concurrent_acquisitions": 0,
                    "cache_hit_rate": 80.0,
                },
            }
            cmd._task_health_check(options)
        assert any("健康" in str(c) for c in cmd.stdout.write.call_args_list)

    def test_task_health_check_with_alerts(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"health_check": True}

        with patch("apps.automation.management.commands.optimize_token_performance.performance_monitor") as mock_perf:
            mock_perf.check_health.return_value = {
                "status": "degraded",
                "alerts": [
                    {"severity": "high", "message": "High failure rate"},
                    {"severity": "medium", "message": "Slow response"},
                    {"severity": "low", "message": "Cache miss"},
                ],
                "metrics": {
                    "success_rate": 50.0,
                    "avg_duration": 10.0,
                    "concurrent_acquisitions": 5,
                    "cache_hit_rate": 30.0,
                },
            }
            cmd._task_health_check(options)
        assert cmd.stdout.write.call_count >= 3

    def test_task_health_check_exception(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"health_check": True}

        with patch("apps.automation.management.commands.optimize_token_performance.performance_monitor") as mock_perf:
            mock_perf.check_health.side_effect = Exception("health error")
            cmd._task_health_check(options)
        assert any("失败" in str(c) for c in cmd.stdout.write.call_args_list)

    def test_task_optimize_concurrency_disabled(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"optimize_concurrency": False}
        asyncio.run(cmd._task_optimize_concurrency(options))
        cmd.stdout.write.assert_not_called()

    def test_task_optimize_concurrency_with_recommendations(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"optimize_concurrency": True}

        with patch("apps.automation.management.commands.optimize_token_performance.concurrency_optimizer") as mock_opt:
            mock_opt.optimize_concurrency = AsyncMock(return_value={
                "recommendations": [
                    {"reason": "Too many concurrent", "recommended": "Reduce to 2"},
                    {"reason": "Queue too long"},
                ],
                "current_usage": {"total_acquisitions": 10, "queue_size": 5},
            })
            asyncio.run(cmd._task_optimize_concurrency(options))
        assert cmd.stdout.write.call_count >= 3

    def test_task_optimize_concurrency_no_recommendations(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"optimize_concurrency": True}

        with patch("apps.automation.management.commands.optimize_token_performance.concurrency_optimizer") as mock_opt:
            mock_opt.optimize_concurrency = AsyncMock(return_value={
                "recommendations": [],
                "current_usage": {"total_acquisitions": 2, "queue_size": 0},
            })
            asyncio.run(cmd._task_optimize_concurrency(options))
        assert any("已优化" in str(c) for c in cmd.stdout.write.call_args_list)

    def test_task_optimize_concurrency_exception(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {"optimize_concurrency": True}

        with patch("apps.automation.management.commands.optimize_token_performance.concurrency_optimizer") as mock_opt:
            mock_opt.optimize_concurrency = AsyncMock(side_effect=Exception("opt error"))
            asyncio.run(cmd._task_optimize_concurrency(options))
        assert any("失败" in str(c) for c in cmd.stdout.write.call_args_list)

    def test_run_optimization_tasks_reset_metrics(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {
            "cleanup_days": 0,
            "warm_cache": None,
            "health_check": False,
            "optimize_concurrency": False,
            "reset_metrics": True,
        }

        with patch("apps.automation.management.commands.optimize_token_performance.performance_monitor") as mock_perf, \
             patch("apps.automation.management.commands.optimize_token_performance.concurrency_optimizer") as mock_opt, \
             patch("apps.automation.management.commands.optimize_token_performance.history_recorder") as mock_rec, \
             patch("apps.automation.management.commands.optimize_token_performance.cache_manager") as mock_cache:
            mock_opt.cleanup_resources = AsyncMock()
            mock_rec.get_recent_statistics = AsyncMock(return_value={
                "total_acquisitions": 5,
                "success_rate": 80.0,
                "avg_duration": 3.0,
            })
            mock_cache.get_cache_statistics.return_value = {"cache_backend": "redis"}
            asyncio.run(cmd._run_optimization_tasks(options))
        mock_perf.reset_metrics.assert_called_once()

    def test_run_optimization_tasks_reset_metrics_exception(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {
            "cleanup_days": 0,
            "warm_cache": None,
            "health_check": False,
            "optimize_concurrency": False,
            "reset_metrics": True,
        }

        with patch("apps.automation.management.commands.optimize_token_performance.performance_monitor") as mock_perf, \
             patch("apps.automation.management.commands.optimize_token_performance.concurrency_optimizer") as mock_opt, \
             patch("apps.automation.management.commands.optimize_token_performance.history_recorder") as mock_rec, \
             patch("apps.automation.management.commands.optimize_token_performance.cache_manager") as mock_cache:
            mock_perf.reset_metrics.side_effect = Exception("reset error")
            mock_opt.cleanup_resources = AsyncMock()
            mock_rec.get_recent_statistics = AsyncMock(return_value={
                "total_acquisitions": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0,
            })
            mock_cache.get_cache_statistics.return_value = {}
            asyncio.run(cmd._run_optimization_tasks(options))
        assert any("重置性能指标失败" in str(c) for c in cmd.stdout.write.call_args_list)

    def test_run_optimization_tasks_cleanup_exception(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {
            "cleanup_days": 0,
            "warm_cache": None,
            "health_check": False,
            "optimize_concurrency": False,
            "reset_metrics": False,
        }

        with patch("apps.automation.management.commands.optimize_token_performance.concurrency_optimizer") as mock_opt, \
             patch("apps.automation.management.commands.optimize_token_performance.history_recorder") as mock_rec, \
             patch("apps.automation.management.commands.optimize_token_performance.cache_manager") as mock_cache:
            mock_opt.cleanup_resources = AsyncMock(side_effect=Exception("cleanup error"))
            mock_rec.get_recent_statistics = AsyncMock(return_value={
                "total_acquisitions": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0,
            })
            mock_cache.get_cache_statistics.return_value = {}
            asyncio.run(cmd._run_optimization_tasks(options))
        assert any("清理并发资源失败" in str(c) for c in cmd.stdout.write.call_args_list)

    def test_run_optimization_tasks_stats_exception(self):
        cmd = self._cmd()
        cmd.stdout = MagicMock()
        options = {
            "cleanup_days": 0,
            "warm_cache": None,
            "health_check": False,
            "optimize_concurrency": False,
            "reset_metrics": False,
        }

        with patch("apps.automation.management.commands.optimize_token_performance.concurrency_optimizer") as mock_opt, \
             patch("apps.automation.management.commands.optimize_token_performance.history_recorder") as mock_rec, \
             patch("apps.automation.management.commands.optimize_token_performance.cache_manager") as mock_cache:
            mock_opt.cleanup_resources = AsyncMock()
            mock_rec.get_recent_statistics = AsyncMock(side_effect=Exception("stats error"))
            mock_cache.get_cache_statistics.return_value = {}
            asyncio.run(cmd._run_optimization_tasks(options))
        assert any("获取统计信息失败" in str(c) for c in cmd.stdout.write.call_args_list)

    def test_add_arguments(self):
        cmd = self._cmd()
        import argparse
        parser = argparse.ArgumentParser()
        cmd.add_arguments(parser)
        args = parser.parse_args(["--cleanup-days", "7", "--health-check", "--reset-metrics"])
        assert args.cleanup_days == 7
        assert args.health_check is True
        assert args.reset_metrics is True
