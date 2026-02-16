"""
Service 层单元测试
"""
from django.test import TestCase
from unittest.mock import patch, MagicMock

from apps.core.health import HealthChecker, HealthStatus
from apps.core.throttling import RateLimiter
from apps.core.business_config import BusinessConfig, business_config, CaseTypeCode


class HealthCheckerTest(TestCase):
    """健康检查测试"""

    def test_liveness_check(self):
        """测试存活检查"""
        result = HealthChecker.liveness_check()
        self.assertEqual(result["status"], "ok")

    def test_check_database(self):
        """测试数据库检查"""
        result = HealthChecker.check_database()
        self.assertEqual(result.name, "database")
        self.assertEqual(result.status, HealthStatus.HEALTHY)
        self.assertIsNotNone(result.latency_ms)

    def test_check_cache(self):
        """测试缓存检查"""
        result = HealthChecker.check_cache()
        self.assertEqual(result.name, "cache")
        # 使用本地内存缓存时应该是 healthy
        self.assertIn(result.status, [HealthStatus.HEALTHY, HealthStatus.DEGRADED])

    def test_get_system_health(self):
        """测试系统健康状态"""
        health = HealthChecker.get_system_health()
        self.assertIn(health.status, [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY])
        self.assertIsNotNone(health.version)
        self.assertGreater(health.uptime_seconds, 0)
        self.assertGreater(len(health.components), 0)

    def test_health_to_dict(self):
        """测试健康状态转字典"""
        health = HealthChecker.get_system_health()
        result = health.to_dict()
        self.assertIn("status", result)
        self.assertIn("version", result)
        self.assertIn("components", result)


class RateLimiterTest(TestCase):
    """限流器测试"""

    def test_rate_limiter_allows_requests(self):
        """测试限流器允许请求"""
        import uuid
        limiter = RateLimiter(requests=10, window=60, key_prefix=f"test_{uuid.uuid4().hex[:8]}")

        # 创建模拟请求
        mock_request = MagicMock()
        mock_request.META = {"REMOTE_ADDR": "127.0.0.1"}
        mock_request.path = "/test-allow"

        # 前10次请求应该被允许
        for i in range(10):
            allowed, info = limiter.is_allowed(mock_request)
            self.assertTrue(allowed, f"Request {i+1} should be allowed")

    def test_rate_limiter_blocks_excess_requests(self):
        """测试限流器阻止超额请求"""
        import uuid
        limiter = RateLimiter(requests=5, window=60, key_prefix=f"test_{uuid.uuid4().hex[:8]}")

        mock_request = MagicMock()
        mock_request.META = {"REMOTE_ADDR": "192.168.1.1"}
        mock_request.path = "/test-block"

        # 发送5次请求
        for _ in range(5):
            limiter.is_allowed(mock_request)

        # 第6次应该被阻止
        allowed, info = limiter.is_allowed(mock_request)
        self.assertFalse(allowed)
        self.assertEqual(info["remaining"], 0)

    def test_get_client_ip_direct(self):
        """测试直接获取客户端IP"""
        limiter = RateLimiter()

        mock_request = MagicMock()
        mock_request.META = {"REMOTE_ADDR": "10.0.0.1"}

        ip = limiter.get_client_ip(mock_request)
        self.assertEqual(ip, "10.0.0.1")

    def test_get_client_ip_forwarded(self):
        """测试通过代理获取客户端IP"""
        limiter = RateLimiter()

        mock_request = MagicMock()
        mock_request.META = {
            "HTTP_X_FORWARDED_FOR": "203.0.113.1, 70.41.3.18",
            "REMOTE_ADDR": "127.0.0.1"
        }

        with patch.dict(
            "os.environ",
            {"DJANGO_TRUST_X_FORWARDED_FOR": "1", "DJANGO_TRUSTED_PROXY_IPS": "127.0.0.1"},
            clear=False,
        ):
            ip = limiter.get_client_ip(mock_request)
        self.assertEqual(ip, "203.0.113.1")


class BusinessConfigTest(TestCase):
    """业务配置测试"""

    def test_singleton(self):
        """测试单例模式"""
        config1 = BusinessConfig()
        config2 = BusinessConfig()
        self.assertIs(config1, config2)

    def test_get_stages_for_civil(self):
        """测试获取民事案件阶段"""
        stages = business_config.get_stages_for_case_type(CaseTypeCode.CIVIL)
        self.assertGreater(len(stages), 0)

        # 民事案件应该包含一审、二审
        stage_values = [s[0] for s in stages]
        self.assertIn("first_trial", stage_values)
        self.assertIn("second_trial", stage_values)

    def test_get_stages_for_criminal(self):
        """测试获取刑事案件阶段"""
        stages = business_config.get_stages_for_case_type(CaseTypeCode.CRIMINAL)
        stage_values = [s[0] for s in stages]

        # 刑事案件应该包含侦查、审查起诉
        self.assertIn("investigation", stage_values)
        self.assertIn("prosecution_review", stage_values)

    def test_get_legal_statuses_for_civil(self):
        """测试获取民事案件诉讼地位"""
        statuses = business_config.get_legal_statuses_for_case_type(CaseTypeCode.CIVIL)
        status_values = [s[0] for s in statuses]

        # 民事案件应该包含原告、被告
        self.assertIn("plaintiff", status_values)
        self.assertIn("defendant", status_values)

    def test_get_stage_label(self):
        """测试获取阶段标签"""
        label = business_config.get_stage_label("first_trial")
        self.assertEqual(label, "一审")

        # 未知阶段返回原值
        label = business_config.get_stage_label("unknown")
        self.assertEqual(label, "unknown")

    def test_is_stage_valid_for_case_type(self):
        """测试阶段有效性检查"""
        # 一审对民事案件有效
        self.assertTrue(
            business_config.is_stage_valid_for_case_type("first_trial", CaseTypeCode.CIVIL)
        )

        # 劳动仲裁对民事案件无效
        self.assertFalse(
            business_config.is_stage_valid_for_case_type("labor_arbitration", CaseTypeCode.CIVIL)
        )
