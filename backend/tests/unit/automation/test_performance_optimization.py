"""
Token获取性能优化功能测试
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.automation.services.token.cache_manager import TokenCacheManager
from apps.automation.services.token.concurrency_optimizer import ConcurrencyConfig, ConcurrencyOptimizer
from apps.automation.services.token.history_recorder import TokenHistoryRecorder
from apps.automation.services.token.performance_monitor import AlertThresholds, PerformanceMetrics, PerformanceMonitor
from apps.core.interfaces import LoginAttemptResult, TokenAcquisitionResult


class TestPerformanceMonitor(TestCase):
    """性能监控器测试"""

    def setUp(self):
        self.monitor = PerformanceMonitor()

    def test_record_acquisition_lifecycle(self):
        """测试获取生命周期记录"""
        acquisition_id = "test_001"
        site_name = "court_zxfw"
        account = "test_account"

        # 记录开始
        self.monitor.record_acquisition_start(acquisition_id, site_name, account)

        # 记录结束（成功）
        self.monitor.record_acquisition_end(acquisition_id, True, 10.5, 8.2, None)

        # 验证指标
        metrics = self.monitor.get_real_time_metrics()
        self.assertIsInstance(metrics, PerformanceMetrics)
        self.assertGreaterEqual(metrics.total_acquisitions, 1)

    def test_cache_access_recording(self):
        """测试缓存访问记录"""
        # 记录缓存命中
        self.monitor.record_cache_access("test_key_1", True)
        self.monitor.record_cache_access("test_key_2", False)
        self.monitor.record_cache_access("test_key_3", True)

        # 验证缓存统计
        metrics = self.monitor.get_real_time_metrics()
        self.assertGreaterEqual(metrics.cache_hit_rate, 0)

    def test_health_check_with_alerts(self):
        """测试健康检查和告警"""
        # 设置低阈值以触发告警
        thresholds = AlertThresholds(min_success_rate=90.0, max_avg_duration=5.0)
        monitor = PerformanceMonitor(thresholds)

        # 模拟一些失败的获取
        for i in range(5):
            monitor.record_acquisition_end(f"test_{i}", False, 15.0, error_type="timeout")

        health_report = monitor.check_health()

        self.assertIn("status", health_report)
        self.assertIn("alerts", health_report)
        self.assertIsInstance(health_report["alerts"], list)

    def test_statistics_report_generation(self):
        """测试统计报告生成"""
        start_date = timezone.now() - timezone.timedelta(days=1)  # type: ignore[attr-defined]
        end_date = timezone.now()

        with patch("apps.automation.models.TokenAcquisitionHistory.objects") as mock_queryset:
            mock_queryset.filter.return_value = mock_queryset
            mock_queryset.count.return_value = 10
            mock_queryset.values.return_value = mock_queryset
            mock_queryset.annotate.return_value = mock_queryset
            mock_queryset.aggregate.return_value = {"total_duration__avg": 12.5, "login_duration__avg": 8.2}
            mock_queryset.order_by.return_value = []

            report = self.monitor.get_statistics_report(start_date, end_date)

            self.assertIn("period", report)
            self.assertIn("summary", report)
            self.assertIn("real_time_metrics", report)


class TestTokenCacheManager(TestCase):
    """Token缓存管理器测试"""

    def setUp(self):
        self.cache_manager = TokenCacheManager()

    @patch("apps.automation.services.token.cache_manager.cache")
    def test_token_caching(self, mock_cache):
        """测试Token缓存"""
        site_name = "court_zxfw"
        account = "test_account"
        token = "test_token_12345"

        # 模拟缓存未命中
        mock_cache.get.return_value = None

        result = self.cache_manager.get_cached_token(site_name, account)
        self.assertIsNone(result)

        # 缓存Token
        self.cache_manager.cache_token(site_name, account, token)
        mock_cache.set.assert_called()

        # 模拟缓存命中
        mock_cache.get.return_value = {"token": token}

        result = self.cache_manager.get_cached_token(site_name, account)
        self.assertEqual(result, token)

    @patch("apps.automation.services.token.cache_manager.cache")
    def test_credentials_caching(self, mock_cache):
        """测试凭证缓存"""
        from apps.core.interfaces import AccountCredentialDTO

        site_name = "court_zxfw"
        credentials = [
            AccountCredentialDTO(
                id=1,
                lawyer_id=1,
                site_name=site_name,
                url=None,
                account="test1",
                password="p1",
                login_success_count=5,
                login_failure_count=1,
            )
        ]

        # 缓存凭证
        self.cache_manager.cache_credentials(site_name, credentials)
        mock_cache.set.assert_called()

        # 模拟缓存命中
        mock_cache.get.return_value = [
            {
                "id": 1,
                "lawyer_id": 1,
                "site_name": site_name,
                "url": None,
                "account": "test1",
                "password": "",
                "last_login_success_at": None,
                "login_success_count": 5,
                "login_failure_count": 1,
                "is_preferred": False,
                "created_at": None,
                "updated_at": None,
            }
        ]

        result = self.cache_manager.get_cached_credentials(site_name)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)  # type: ignore[arg-type]
        self.assertEqual(result[0].account, "test1")  # type: ignore[index]

    def test_cache_key_generation(self):
        """测试缓存键生成"""
        site_name = "court_zxfw"
        account = "test_account"

        token_key = self.cache_manager._get_token_cache_key(site_name, account)
        self.assertIn(site_name, token_key)
        self.assertNotIn(account, token_key)

        creds_key = self.cache_manager._get_credentials_cache_key(site_name)
        self.assertIn(site_name, creds_key)


class TestConcurrencyOptimizer(TestCase):
    """并发优化器测试"""

    def setUp(self):
        self.optimizer = ConcurrencyOptimizer()

    @pytest.mark.anyio
    async def test_resource_acquisition_and_release(self):
        """测试资源获取和释放"""
        acquisition_id = "test_001"
        site_name = "court_zxfw"
        account = "test_account"

        # 获取资源
        success = await self.optimizer.acquire_resource(acquisition_id, site_name, account)
        self.assertTrue(success)

        # 检查资源使用情况
        usage = await self.optimizer.get_resource_usage()
        self.assertGreater(usage["total_acquisitions"], 0)

        # 释放资源
        await self.optimizer.release_resource(acquisition_id, site_name, account)

        # 验证资源已释放
        usage_after = await self.optimizer.get_resource_usage()
        self.assertEqual(usage_after["total_acquisitions"], 0)

    @pytest.mark.anyio
    async def test_concurrency_limits(self):
        """测试并发限制"""
        config = ConcurrencyConfig(max_concurrent_acquisitions=2)
        optimizer = ConcurrencyOptimizer(config)

        # 获取最大数量的资源
        await optimizer.acquire_resource("test_1", "site1", "account1")
        await optimizer.acquire_resource("test_2", "site2", "account2")

        # 第三个请求应该被限制（这里简化测试，实际会进入队列）
        usage = await optimizer.get_resource_usage()
        self.assertEqual(usage["total_acquisitions"], 2)

    @pytest.mark.anyio
    async def test_optimization_recommendations(self):
        """测试优化建议"""
        # 模拟高负载情况
        config = ConcurrencyConfig(max_concurrent_acquisitions=2)
        optimizer = ConcurrencyOptimizer(config)

        # 获取接近上限的资源
        await optimizer.acquire_resource("test_1", "site1", "account1")
        await optimizer.acquire_resource("test_2", "site1", "account2")

        optimization_result = await optimizer.optimize_concurrency()

        self.assertIn("current_usage", optimization_result)
        self.assertIn("recommendations", optimization_result)
        self.assertIsInstance(optimization_result["recommendations"], list)


class TestTokenHistoryRecorder(TestCase):
    """Token历史记录器测试"""

    @pytest.mark.anyio
    async def test_record_acquisition_history(self):
        """测试记录获取历史"""
        acquisition_id = "test_001"
        site_name = "court_zxfw"
        account = "test_account"
        credential_id = 1

        # 创建成功的获取结果
        result = TokenAcquisitionResult(
            success=True,
            token="test_token_12345",
            acquisition_method="auto_login",
            total_duration=10.5,
            login_attempts=[
                LoginAttemptResult(
                    success=True,
                    token="test_token_12345",
                    account=account,
                    error_message=None,
                    attempt_duration=8.2,
                    retry_count=1,
                )
            ],
        )

        with patch("apps.automation.services.token.history_recorder.TokenAcquisitionHistory.objects") as mock_objects:
            mock_objects.create.return_value = Mock(id=1)

            # 记录历史
            await TokenHistoryRecorder.record_acquisition_history(  # type: ignore[call-arg]
                acquisition_id,
                site_name,
                account,
                credential_id,
                result,  # type: ignore[arg-type]
            )

            # 验证创建调用
            mock_objects.create.assert_called_once()
            call_args = mock_objects.create.call_args[1]
            self.assertEqual(call_args["site_name"], site_name)
            self.assertEqual(call_args["account"], account)
            self.assertEqual(call_args["status"], "success")

    @pytest.mark.anyio
    async def test_get_recent_statistics(self):
        """测试获取最近统计"""
        with patch("apps.automation.models.TokenAcquisitionHistory.objects") as mock_objects:
            mock_queryset = Mock()
            mock_objects.filter.return_value = mock_queryset
            mock_queryset.count.return_value = 10
            mock_queryset.filter.return_value = mock_queryset
            mock_queryset.values.return_value = mock_queryset
            mock_queryset.annotate.return_value = mock_queryset
            mock_queryset.order_by.return_value = []
            mock_queryset.aggregate.side_effect = [
                {"total_duration__avg": 12.5},
                {"login_duration__avg": 8.0},
            ]

            stats = await TokenHistoryRecorder.get_recent_statistics(hours=24)  # type: ignore[call-arg]

            self.assertIn("total_acquisitions", stats)
            self.assertIn("success_rate", stats)
            self.assertEqual(stats["total_acquisitions"], 10)

    @pytest.mark.anyio
    async def test_cleanup_old_records(self):
        """测试清理旧记录"""
        with patch("apps.automation.models.TokenAcquisitionHistory.objects") as mock_objects:
            mock_queryset = Mock()
            mock_objects.filter.return_value = mock_queryset
            mock_queryset.delete.return_value = (5, {})

            deleted_count = await TokenHistoryRecorder.cleanup_old_records(days=30)  # type: ignore[call-arg]

            self.assertEqual(deleted_count, 5)
            mock_objects.filter.assert_called_once()


# 集成测试
class TestPerformanceOptimizationIntegration(TestCase):
    """性能优化集成测试"""

    @pytest.mark.anyio
    async def test_full_optimization_workflow(self):
        """测试完整的优化工作流"""
        # 这里可以添加端到端的集成测试
        # 测试各个组件之间的协作
        pass
