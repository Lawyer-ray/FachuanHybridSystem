"""
性能监控测试
"""

import time
from unittest.mock import Mock, patch

import pytest
from django.test import RequestFactory

from apps.core.monitoring import PerformanceMonitor, monitor_api, monitor_operation


@pytest.mark.django_db
class TestPerformanceMonitor:
    """性能监控器测试"""

    def test_monitor_api_decorator_success(self):
        """测试 API 监控装饰器（成功场景）"""

        @monitor_api("test_endpoint")
        def test_function():
            time.sleep(0.01)  # 模拟耗时操作
            return "success"

        # 执行函数
        result = test_function()

        # 验证结果
        assert result == "success"

    def test_monitor_api_decorator_with_exception(self):
        """测试 API 监控装饰器（异常场景）"""

        @monitor_api("test_endpoint")
        def test_function():
            raise ValueError("Test error")

        # 验证异常被正确抛出
        with pytest.raises(ValueError) as exc_info:
            test_function()

        assert "Test error" in str(exc_info.value)

    def test_monitor_operation_context_manager(self):
        """测试操作监控上下文管理器"""

        with monitor_operation("test_operation"):
            time.sleep(0.01)  # 模拟耗时操作
            result = "success"

        assert result == "success"

    def test_monitor_operation_with_exception(self):
        """测试操作监控上下文管理器（异常场景）"""

        with pytest.raises(ValueError):
            with monitor_operation("test_operation"):
                raise ValueError("Test error")

    @patch("apps.core.monitoring.logger")
    def test_performance_logging(self, mock_logger):
        """测试性能日志记录"""

        @monitor_api("test_endpoint")
        def test_function():
            return "success"

        # 执行函数
        test_function()

        # 验证日志被调用
        assert mock_logger.info.called or mock_logger.warning.called

    def test_get_query_details_in_debug_mode(self, settings):
        """测试获取查询详情（DEBUG 模式）"""
        settings.DEBUG = True

        # 执行一些数据库操作
        from apps.cases.models import Case

        list(Case.objects.all())

        # 获取查询详情
        queries = PerformanceMonitor.get_query_details()

        # 验证返回了查询信息
        assert isinstance(queries, list)

    def test_analyze_queries_in_debug_mode(self, settings):
        """测试查询分析（DEBUG 模式）"""
        settings.DEBUG = True

        # 执行一些数据库操作
        from apps.cases.models import Case

        list(Case.objects.all())

        # 分析查询
        analysis = PerformanceMonitor.analyze_queries()

        # 验证分析结果
        assert "total_queries" in analysis
        assert "total_time_ms" in analysis
        assert "slow_queries" in analysis


@pytest.mark.django_db
class TestPerformanceOptimization:
    """性能优化测试"""

    def test_monitoring_system_available(self):
        """测试性能监控系统可用"""
        from apps.core.monitoring import PerformanceMonitor, monitor_api, monitor_operation

        # 验证监控类和函数可用
        assert PerformanceMonitor is not None
        assert monitor_api is not None
        assert monitor_operation is not None

    def test_query_analysis_in_debug_mode(self, settings):
        """测试查询分析功能（DEBUG 模式）"""
        from django.db import connection, reset_queries
        from django.test.utils import override_settings

        from apps.cases.models import Case
        from apps.core.monitoring import PerformanceMonitor

        settings.DEBUG = True

        # 重置查询计数
        with override_settings(DEBUG=True):
            reset_queries()

            # 执行一些查询
            list(Case.objects.all())

            # 分析查询
            analysis = PerformanceMonitor.analyze_queries()

            # 验证分析结果
            assert "total_queries" in analysis
            assert "total_time_ms" in analysis
            assert "slow_queries" in analysis
            assert isinstance(analysis["total_queries"], int)
            assert analysis["total_queries"] >= 0
