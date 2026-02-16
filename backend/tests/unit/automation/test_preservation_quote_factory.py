"""
财产保险询价服务工厂函数测试

测试API层工厂函数的依赖注入配置是否正确
"""
import pytest
from unittest.mock import Mock

from apps.automation.api.preservation_quote_api import _get_preservation_quote_service
from apps.automation.services.insurance.preservation_quote_service_adapter import PreservationQuoteServiceAdapter
from apps.automation.services.scraper.core.token_service import TokenService
from apps.automation.services.insurance.court_insurance_client import CourtInsuranceClient
from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
from apps.core.interfaces import ServiceLocator, IAutoTokenAcquisitionService


class TestPreservationQuoteFactory:
    """财产保险询价服务工厂函数测试"""
    
    def setup_method(self):
        """每个测试前清理ServiceLocator"""
        ServiceLocator.clear()
    
    def teardown_method(self):
        """每个测试后清理ServiceLocator"""
        ServiceLocator.clear()
    
    def test_factory_creates_service_with_correct_dependencies(self):
        """测试工厂函数创建服务并正确注入依赖"""
        # 执行工厂函数
        service = _get_preservation_quote_service()
        
        # 验证返回的是正确的适配器类型
        assert isinstance(service, PreservationQuoteServiceAdapter)
        
        # 验证依赖注入是否正确
        assert isinstance(service.token_service, TokenService)
        assert isinstance(service.insurance_client, CourtInsuranceClient)
        assert isinstance(service.auto_token_service, AutoTokenAcquisitionService)
    
    def test_factory_uses_service_locator_for_auto_token_service(self):
        """测试工厂函数通过ServiceLocator获取自动Token服务"""
        # 注册Mock服务到ServiceLocator
        mock_auto_token_service = Mock(spec=IAutoTokenAcquisitionService)
        ServiceLocator.register("auto_token_acquisition_service", mock_auto_token_service)
        
        # 执行工厂函数
        service = _get_preservation_quote_service()
        
        # 验证使用了ServiceLocator中的Mock服务
        assert service.auto_token_service is mock_auto_token_service
    
    def test_service_locator_creates_correct_services(self):
        """测试ServiceLocator创建正确的服务实例"""
        # 测试自动Token获取服务
        auto_token_service = ServiceLocator.get_auto_token_acquisition_service()
        assert isinstance(auto_token_service, AutoTokenAcquisitionService)
        
        # 测试账号选择策略
        from apps.automation.services.token.account_selection_strategy import AccountSelectionStrategy
        account_strategy = ServiceLocator.get_account_selection_strategy()
        assert isinstance(account_strategy, AccountSelectionStrategy)
        
        # 测试自动登录服务
        from apps.automation.services.token.auto_login_service import AutoLoginService
        auto_login_service = ServiceLocator.get_auto_login_service()
        assert isinstance(auto_login_service, AutoLoginService)
    
    def test_service_locator_caching(self):
        """测试ServiceLocator的缓存机制"""
        # 第一次获取
        service1 = ServiceLocator.get_auto_token_acquisition_service()
        
        # 第二次获取应该返回同一实例
        service2 = ServiceLocator.get_auto_token_acquisition_service()
        
        assert service1 is service2
    
    def test_service_locator_clear_functionality(self):
        """测试ServiceLocator的清理功能"""
        # 获取服务实例
        service1 = ServiceLocator.get_auto_token_acquisition_service()
        
        # 清理特定服务
        ServiceLocator.clear("auto_token_acquisition_service")
        
        # 再次获取应该是新实例
        service2 = ServiceLocator.get_auto_token_acquisition_service()
        
        assert service1 is not service2
    
    def test_factory_function_independence(self):
        """测试工厂函数的独立性（每次调用创建新实例）"""
        # 多次调用工厂函数
        service1 = _get_preservation_quote_service()
        service2 = _get_preservation_quote_service()
        
        # 应该创建不同的适配器实例
        assert service1 is not service2
        
        # 但底层的自动Token服务应该是同一实例（通过ServiceLocator缓存）
        assert service1.auto_token_service is service2.auto_token_service
    
    def test_mock_injection_for_testing(self):
        """测试Mock对象注入，便于单元测试"""
        # 创建Mock依赖
        mock_token_service = Mock()
        mock_insurance_client = Mock()
        mock_auto_token_service = Mock(spec=IAutoTokenAcquisitionService)
        
        # 注册Mock服务
        ServiceLocator.register("auto_token_acquisition_service", mock_auto_token_service)
        
        # 创建适配器（手动注入其他Mock）
        from apps.automation.services.insurance.preservation_quote_service_adapter import PreservationQuoteServiceAdapter
        
        service = PreservationQuoteServiceAdapter(
            token_service=mock_token_service,
            insurance_client=mock_insurance_client,
            auto_token_service=mock_auto_token_service
        )
        
        # 验证Mock注入成功
        assert service.token_service is mock_token_service
        assert service.insurance_client is mock_insurance_client
        assert service.auto_token_service is mock_auto_token_service