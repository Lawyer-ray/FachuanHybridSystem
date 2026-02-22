"""
自动登录服务集成测试
"""

from unittest.mock import Mock, patch

import pytest

from apps.automation.exceptions import LoginFailedError
from apps.automation.services.token.auto_login_service import AutoLoginService, RetryConfig
from apps.core.exceptions import NetworkError
from apps.core.interfaces import AccountCredentialDTO, ServiceLocator


@pytest.mark.django_db
class TestAutoLoginServiceIntegration:
    """自动登录服务集成测试"""

    def test_service_locator_integration(self):
        """测试通过ServiceLocator获取服务"""
        # 清除缓存
        ServiceLocator.clear()

        # 获取服务
        service = ServiceLocator.get_auto_login_service()

        assert isinstance(service, AutoLoginService)
        assert service.retry_config.max_network_retries == 3
        assert service.retry_config.max_captcha_retries == 3

        # 再次获取应该是同一个实例（单例）
        service2 = ServiceLocator.get_auto_login_service()
        assert service is service2

    def test_service_creation_with_dependencies(self):
        """测试服务创建时的依赖注入"""
        # 创建自定义配置
        custom_config = RetryConfig(max_network_retries=5, max_captcha_retries=2, login_timeout=30.0)

        # 创建Mock浏览器服务
        mock_browser_service = Mock()

        # 创建服务实例
        service = AutoLoginService(retry_config=custom_config, browser_service=mock_browser_service)

        assert service.retry_config.max_network_retries == 5
        assert service.retry_config.max_captcha_retries == 2
        assert service.retry_config.login_timeout == 30.0
        assert service._browser_service is mock_browser_service

    @pytest.mark.anyio
    async def test_error_classification(self):
        """测试错误分类功能"""
        service = AutoLoginService()

        credential = AccountCredentialDTO(
            id=1,
            lawyer_id=1,
            site_name="court_zxfw",
            url="https://zxfw.court.gov.cn",
            account="test_user",
            password="test_password",
        )

        # 测试网络错误识别
        with patch.object(service, "_sync_login_attempt") as mock_login:
            mock_login.side_effect = Exception("connection timeout")

            with pytest.raises(NetworkError):
                await service.login_and_get_token(credential)

        # 测试非网络错误
        with patch.object(service, "_sync_login_attempt") as mock_login:
            mock_login.side_effect = Exception("验证码错误")

            with pytest.raises(LoginFailedError):
                await service.login_and_get_token(credential)

    def test_browser_service_lazy_loading(self):
        """测试浏览器服务的延迟加载"""
        service = AutoLoginService()

        # 初始时浏览器服务应该为None
        assert service._browser_service is None

        # 访问browser_service属性时应该自动创建（通过ServiceLocator）
        with patch.object(ServiceLocator, "get_browser_service") as mock_get_browser:
            mock_instance = Mock()
            mock_get_browser.return_value = mock_instance

            browser_service = service.browser_service

            assert browser_service is mock_instance
            mock_get_browser.assert_called_once()

    def test_login_attempts_management(self):
        """测试登录尝试记录管理"""
        service = AutoLoginService()

        # 初始应该为空
        assert len(service.get_login_attempts()) == 0

        # 模拟添加一些记录
        from apps.core.interfaces import LoginAttemptResult

        attempt1 = LoginAttemptResult(
            success=False,
            token=None,
            account="test_user",
            error_message="验证码错误",
            attempt_duration=1.5,
            retry_count=1,
        )

        attempt2 = LoginAttemptResult(
            success=True, token="token123", account="test_user", error_message=None, attempt_duration=2.0, retry_count=2
        )

        service._login_attempts.extend([attempt1, attempt2])

        # 获取记录
        attempts = service.get_login_attempts()
        assert len(attempts) == 2
        assert attempts[0].success is False
        assert attempts[1].success is True

        # 清空记录
        service.clear_login_attempts()
        assert len(service.get_login_attempts()) == 0

    def test_service_interface_compliance(self):
        """测试服务是否符合接口规范"""
        from apps.core.interfaces import IAutoLoginService

        service = AutoLoginService()

        # 检查是否实现了所有必需的方法
        assert hasattr(service, "login_and_get_token")
        assert callable(service.login_and_get_token)

        # 检查方法签名（通过尝试调用来验证）
        import inspect

        sig = inspect.signature(service.login_and_get_token)
        params = list(sig.parameters.keys())
        assert "credential" in params

    @pytest.mark.anyio
    async def test_concurrent_login_attempts(self):
        """测试并发登录尝试的隔离性"""
        import asyncio

        service1 = AutoLoginService()
        service2 = AutoLoginService()

        credential = AccountCredentialDTO(
            id=1,
            lawyer_id=1,
            site_name="court_zxfw",
            url="https://zxfw.court.gov.cn",
            account="test_user",
            password="test_password",
        )

        # Mock不同的登录结果
        with (
            patch.object(service1, "_sync_login_attempt") as mock1,
            patch.object(service2, "_sync_login_attempt") as mock2,
        ):
            mock1.return_value = "token1"
            mock2.return_value = "token2"

            # 并发执行
            results = await asyncio.gather(
                service1.login_and_get_token(credential),
                service2.login_and_get_token(credential),
                return_exceptions=True,
            )

            assert results[0] == "token1"
            assert results[1] == "token2"

            # 验证各自的登录记录是独立的
            attempts1 = service1.get_login_attempts()
            attempts2 = service2.get_login_attempts()

            assert len(attempts1) == 1
            assert len(attempts2) == 1
            assert attempts1[0].token == "token1"
            assert attempts2[0].token == "token2"
