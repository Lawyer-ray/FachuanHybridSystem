"""
财产保险询价服务自动Token获取集成测试

测试PreservationQuoteService与AutoTokenAcquisitionService的集成
"""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest

from apps.automation.exceptions import AutoTokenAcquisitionError
from apps.automation.models import PreservationQuote, QuoteStatus
from apps.automation.services.insurance.exceptions import TokenError
from apps.automation.services.insurance.preservation_quote_service_adapter import (
    EnhancedPreservationQuoteService,
    PreservationQuoteServiceAdapter,
)
from apps.core.interfaces import (
    AccountCredentialDTO,
    IAutoTokenAcquisitionService,
    LoginAttemptResult,
    TokenAcquisitionResult,
)


@pytest.mark.django_db
class TestPreservationQuoteAutoTokenIntegration:
    """财产保险询价自动Token获取集成测试"""

    def setup_method(self):
        """测试前准备"""
        # 创建Mock服务
        self.mock_token_service = Mock()
        self.mock_insurance_client = Mock()
        self.mock_auto_token_service = Mock(spec=IAutoTokenAcquisitionService)

        # 创建服务适配器
        self.adapter = PreservationQuoteServiceAdapter(
            token_service=self.mock_token_service,
            insurance_client=self.mock_insurance_client,
            auto_token_service=self.mock_auto_token_service,
        )

    def test_service_adapter_initialization(self):
        """测试服务适配器初始化"""
        # 测试延迟加载
        adapter = PreservationQuoteServiceAdapter()

        # 验证属性访问会触发延迟加载
        assert adapter.token_service is not None
        assert adapter.insurance_client is not None
        assert adapter.auto_token_service is not None
        assert adapter.service is not None

        # 验证服务类型
        assert isinstance(adapter.service, EnhancedPreservationQuoteService)

    def test_enhanced_service_initialization(self):
        """测试增强版服务初始化"""
        service = EnhancedPreservationQuoteService(
            token_service=self.mock_token_service,
            insurance_client=self.mock_insurance_client,
            auto_token_service=self.mock_auto_token_service,
        )

        assert service.token_service == self.mock_token_service
        assert service.insurance_client == self.mock_insurance_client
        assert service.auto_token_service == self.mock_auto_token_service

    @pytest.mark.anyio
    async def test_get_valid_token_success_with_credential_id(self):
        """测试指定凭证ID成功获取Token"""
        # 准备测试数据
        credential_id = 1
        expected_token = "test_token_123"

        # 配置Mock
        self.mock_auto_token_service.acquire_token_if_needed = AsyncMock(return_value=expected_token)

        # 创建增强版服务
        service = EnhancedPreservationQuoteService(
            token_service=self.mock_token_service,
            insurance_client=self.mock_insurance_client,
            auto_token_service=self.mock_auto_token_service,
        )

        # 执行测试
        token = await service._get_valid_token(credential_id)

        # 验证结果
        assert token == expected_token

        # 验证调用
        self.mock_auto_token_service.acquire_token_if_needed.assert_called_once_with(
            site_name="court_zxfw", credential_id=credential_id
        )

    @pytest.mark.anyio
    async def test_get_valid_token_success_without_credential_id(self):
        """测试不指定凭证ID成功获取Token"""
        # 准备测试数据
        expected_token = "auto_selected_token_456"

        # 配置Mock
        self.mock_auto_token_service.acquire_token_if_needed = AsyncMock(return_value=expected_token)

        # 创建增强版服务
        service = EnhancedPreservationQuoteService(
            token_service=self.mock_token_service,
            insurance_client=self.mock_insurance_client,
            auto_token_service=self.mock_auto_token_service,
        )

        # 执行测试
        token = await service._get_valid_token()

        # 验证结果
        assert token == expected_token

        # 验证调用
        self.mock_auto_token_service.acquire_token_if_needed.assert_called_once_with(
            site_name="court_zxfw", credential_id=None
        )

    @pytest.mark.anyio
    async def test_get_valid_token_auto_acquisition_error(self):
        """测试自动Token获取失败的错误处理"""
        # 准备测试数据
        credential_id = 1
        error_message = "所有账号登录失败"

        # 配置Mock抛出异常
        self.mock_auto_token_service.acquire_token_if_needed = AsyncMock(
            side_effect=AutoTokenAcquisitionError(message=error_message, errors={"login_failed": True})
        )

        # 创建增强版服务
        service = EnhancedPreservationQuoteService(
            token_service=self.mock_token_service,
            insurance_client=self.mock_insurance_client,
            auto_token_service=self.mock_auto_token_service,
        )

        # 执行测试并验证异常
        with pytest.raises(TokenError) as exc_info:
            await service._get_valid_token(credential_id)

        # 验证异常信息
        assert "自动Token获取失败" in str(exc_info.value)
        assert error_message in str(exc_info.value)

        # 验证调用
        self.mock_auto_token_service.acquire_token_if_needed.assert_called_once_with(
            site_name="court_zxfw", credential_id=credential_id
        )

    @pytest.mark.anyio
    async def test_get_valid_token_unexpected_error(self):
        """测试意外错误的处理"""
        # 准备测试数据
        credential_id = 1

        # 配置Mock抛出意外异常
        self.mock_auto_token_service.acquire_token_if_needed = AsyncMock(side_effect=ValueError("意外错误"))

        # 创建增强版服务
        service = EnhancedPreservationQuoteService(
            token_service=self.mock_token_service,
            insurance_client=self.mock_insurance_client,
            auto_token_service=self.mock_auto_token_service,
        )

        # 执行测试并验证异常直接重新抛出
        with pytest.raises(ValueError) as exc_info:
            await service._get_valid_token(credential_id)

        assert "意外错误" in str(exc_info.value)

    def test_adapter_method_delegation(self):
        """测试适配器方法代理"""
        # 配置Mock
        mock_quote = Mock()
        self.adapter.service.create_quote = Mock(return_value=mock_quote) # type: ignore[method-assign]
        self.adapter.service.get_quote = Mock(return_value=mock_quote) # type: ignore[method-assign]
        self.adapter.service.list_quotes = Mock(return_value=([], 0)) # type: ignore[method-assign]

        # 测试create_quote代理
        result = self.adapter.create_quote(
            preserve_amount=Decimal("10000"), corp_id="test_corp", category_id="test_category", credential_id=1
        )
        assert result == mock_quote

        # 测试get_quote代理
        result = self.adapter.get_quote(1)
        assert result == mock_quote

        # 测试list_quotes代理
        quotes, total = self.adapter.list_quotes(page=1, page_size=20)
        assert quotes == []
        assert total == 0

    @pytest.mark.anyio
    async def test_adapter_async_method_delegation(self):
        """测试适配器异步方法代理"""
        # 配置Mock
        mock_result = {"success_count": 5, "failed_count": 0}
        self.adapter.service.execute_quote = AsyncMock(return_value=mock_result) # type: ignore[method-assign]
        self.adapter.service.retry_quote = AsyncMock(return_value=mock_result) # type: ignore[method-assign]

        # 测试execute_quote代理
        result = await self.adapter.execute_quote(1)
        assert result == mock_result

        # 测试retry_quote代理
        result = await self.adapter.retry_quote(1)
        assert result == mock_result


@pytest.mark.django_db
class TestPreservationQuoteAPIIntegration:
    """财产保险询价API集成测试"""

    def test_api_uses_service_adapter(self):
        """测试API使用服务适配器"""
        from apps.automation.api.preservation_quote_api import _get_preservation_quote_service

        # 调用工厂函数
        service = _get_preservation_quote_service()

        # 验证返回的是适配器实例
        assert isinstance(service, PreservationQuoteServiceAdapter)

        # 验证适配器包含增强版服务
        assert isinstance(service.service, EnhancedPreservationQuoteService)

        # 验证自动Token服务已注入
        assert service.auto_token_service is not None


class TestServiceIntegrationProperties:
    """服务集成属性测试"""

    def test_adapter_preserves_original_interface(self):
        """测试适配器保持原有接口"""
        adapter = PreservationQuoteServiceAdapter()

        # 验证适配器具有所有必要的方法
        assert hasattr(adapter, "create_quote")
        assert hasattr(adapter, "execute_quote")
        assert hasattr(adapter, "get_quote")
        assert hasattr(adapter, "retry_quote")
        assert hasattr(adapter, "list_quotes")

        # 验证方法是可调用的
        assert callable(adapter.create_quote)
        assert callable(adapter.execute_quote)
        assert callable(adapter.get_quote)
        assert callable(adapter.retry_quote)
        assert callable(adapter.list_quotes)

    def test_enhanced_service_extends_original(self):
        """测试增强版服务扩展原有功能"""
        mock_token_service = Mock()
        mock_insurance_client = Mock()
        mock_auto_token_service = Mock()

        service = EnhancedPreservationQuoteService(
            token_service=mock_token_service,
            insurance_client=mock_insurance_client,
            auto_token_service=mock_auto_token_service,
        )

        # 验证继承了原有方法
        assert hasattr(service, "create_quote")
        assert hasattr(service, "execute_quote")
        assert hasattr(service, "get_quote")
        assert hasattr(service, "retry_quote")
        assert hasattr(service, "list_quotes")

        # 验证增强了_get_valid_token方法
        assert hasattr(service, "_get_valid_token")
        assert hasattr(service, "auto_token_service")

    def test_dependency_injection_pattern(self):
        """测试依赖注入模式"""
        # 测试构造函数注入
        mock_token_service = Mock()
        mock_insurance_client = Mock()
        mock_auto_token_service = Mock()

        adapter = PreservationQuoteServiceAdapter(
            token_service=mock_token_service,
            insurance_client=mock_insurance_client,
            auto_token_service=mock_auto_token_service,
        )

        # 验证依赖正确注入
        assert adapter.token_service == mock_token_service
        assert adapter.insurance_client == mock_insurance_client
        assert adapter.auto_token_service == mock_auto_token_service

        # 测试延迟加载
        adapter_lazy = PreservationQuoteServiceAdapter()

        # 验证延迟加载创建了实例
        assert adapter_lazy.token_service is not None
        assert adapter_lazy.insurance_client is not None
        assert adapter_lazy.auto_token_service is not None
