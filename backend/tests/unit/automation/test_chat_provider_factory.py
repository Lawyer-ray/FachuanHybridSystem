"""
ChatProviderFactory 单元测试

测试群聊提供者工厂类的核心功能，包括注册、获取和管理提供者实例。
"""

import pytest
from unittest.mock import Mock, patch

from apps.automation.services.chat.factory import ChatProviderFactory
from apps.automation.services.chat.base import ChatProvider, ChatResult
from apps.core.enums import ChatPlatform
from apps.core.exceptions import UnsupportedPlatformException, ConfigurationException


class MockChatProvider(ChatProvider):
    """测试用的模拟群聊提供者"""
    
    def __init__(self, platform=ChatPlatform.FEISHU, available=True):
        self._platform = platform
        self._available = available
    
    @property
    def platform(self):
        return self._platform
    
    def is_available(self):
        return self._available
    
    def create_chat(self, chat_name, owner_id=None):
        return ChatResult(success=True, chat_id="test_chat_id", chat_name=chat_name)
    
    def send_message(self, chat_id, content):
        return ChatResult(success=True, message="Message sent")
    
    def send_file(self, chat_id, file_path):
        return ChatResult(success=True, message="File sent")
    
    def get_chat_info(self, chat_id):
        return ChatResult(success=True, chat_name="Test Chat")


class TestChatProviderFactory:
    """ChatProviderFactory 测试类"""
    
    def setup_method(self):
        """每个测试方法前的设置"""
        # 清除工厂状态
        ChatProviderFactory._providers.clear()
        ChatProviderFactory._instances.clear()
    
    def teardown_method(self):
        """每个测试方法后的清理"""
        # 清除工厂状态
        ChatProviderFactory._providers.clear()
        ChatProviderFactory._instances.clear()
    
    def test_register_provider_success(self):
        """测试成功注册提供者"""
        # 注册提供者
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        
        # 验证注册成功
        assert ChatPlatform.FEISHU in ChatProviderFactory._providers
        assert ChatProviderFactory._providers[ChatPlatform.FEISHU] == MockChatProvider
        assert ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU)
    
    def test_register_invalid_provider_raises_error(self):
        """测试注册无效提供者抛出异常"""
        class InvalidProvider:
            pass
        
        with pytest.raises(TypeError, match="必须继承 ChatProvider"):
            ChatProviderFactory.register(ChatPlatform.FEISHU, InvalidProvider)
    
    def test_get_provider_success(self):
        """测试成功获取提供者实例"""
        # 注册提供者
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        
        # 获取提供者实例
        provider = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        
        # 验证实例正确
        assert isinstance(provider, MockChatProvider)
        assert provider.platform == ChatPlatform.FEISHU
    
    def test_get_provider_caching(self):
        """测试提供者实例缓存机制"""
        # 注册提供者
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        
        # 获取两次实例
        provider1 = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        provider2 = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        
        # 验证是同一个实例
        assert provider1 is provider2
    
    def test_get_provider_unregistered_platform_raises_error(self):
        """测试获取未注册平台抛出异常"""
        with pytest.raises(UnsupportedPlatformException) as exc_info:
            ChatProviderFactory.get_provider(ChatPlatform.SLACK)
        
        # 验证异常信息
        assert "不支持的群聊平台: slack" in str(exc_info.value)
        assert exc_info.value.platform == "slack"
    
    def test_get_provider_platform_mismatch_raises_error(self):
        """测试提供者平台属性不匹配抛出异常"""
        # 创建平台属性不匹配的提供者
        class MismatchedProvider(MockChatProvider):
            def __init__(self):
                super().__init__(platform=ChatPlatform.DINGTALK)  # 注册为FEISHU但返回DINGTALK
        
        ChatProviderFactory.register(ChatPlatform.FEISHU, MismatchedProvider)
        
        with pytest.raises(ConfigurationException) as exc_info:
            ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        
        # 检查异常信息（可能在 errors 字段中）
        exception = exc_info.value
        assert "无法创建群聊提供者实例" in str(exception) or "提供者实例的平台属性不匹配" in str(exception.errors.get('original_error', ''))
    
    def test_get_available_platforms_empty(self):
        """测试获取可用平台列表（空）"""
        platforms = ChatProviderFactory.get_available_platforms()
        assert platforms == []
    
    def test_get_available_platforms_with_available_provider(self):
        """测试获取可用平台列表（有可用提供者）"""
        # 注册可用提供者
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        
        platforms = ChatProviderFactory.get_available_platforms()
        assert platforms == [ChatPlatform.FEISHU]
    
    def test_get_available_platforms_with_unavailable_provider(self):
        """测试获取可用平台列表（有不可用提供者）"""
        # 创建不可用的提供者
        class UnavailableProvider(MockChatProvider):
            def __init__(self):
                super().__init__(available=False)
        
        ChatProviderFactory.register(ChatPlatform.FEISHU, UnavailableProvider)
        
        platforms = ChatProviderFactory.get_available_platforms()
        assert platforms == []
    
    def test_get_available_platforms_mixed(self):
        """测试获取可用平台列表（混合情况）"""
        # 注册可用和不可用的提供者
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        
        class UnavailableProvider(MockChatProvider):
            def __init__(self):
                super().__init__(platform=ChatPlatform.DINGTALK, available=False)
        
        ChatProviderFactory.register(ChatPlatform.DINGTALK, UnavailableProvider)
        
        platforms = ChatProviderFactory.get_available_platforms()
        assert platforms == [ChatPlatform.FEISHU]
    
    def test_get_registered_platforms(self):
        """测试获取已注册平台列表"""
        # 注册多个提供者
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        
        class DingtalkProvider(MockChatProvider):
            def __init__(self):
                super().__init__(platform=ChatPlatform.DINGTALK)
        
        ChatProviderFactory.register(ChatPlatform.DINGTALK, DingtalkProvider)
        
        platforms = ChatProviderFactory.get_registered_platforms()
        assert set(platforms) == {ChatPlatform.FEISHU, ChatPlatform.DINGTALK}
    
    def test_clear_cache(self):
        """测试清除缓存"""
        # 注册提供者并获取实例
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        provider1 = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        
        # 清除缓存
        ChatProviderFactory.clear_cache()
        
        # 再次获取实例，应该是新的实例
        provider2 = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        assert provider1 is not provider2
    
    def test_unregister_platform(self):
        """测试注销平台提供者"""
        # 注册提供者
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        assert ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU)
        
        # 注销提供者
        result = ChatProviderFactory.unregister(ChatPlatform.FEISHU)
        assert result is True
        assert not ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU)
        
        # 再次注销不存在的提供者
        result = ChatProviderFactory.unregister(ChatPlatform.FEISHU)
        assert result is False
    
    def test_unregister_clears_cache(self):
        """测试注销提供者时清除缓存"""
        # 注册提供者并获取实例
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        
        # 验证缓存中有实例
        assert ChatPlatform.FEISHU in ChatProviderFactory._instances
        
        # 注销提供者
        ChatProviderFactory.unregister(ChatPlatform.FEISHU)
        
        # 验证缓存被清除
        assert ChatPlatform.FEISHU not in ChatProviderFactory._instances
    
    @patch('apps.automation.services.chat.factory.logger')
    def test_logging_on_register(self, mock_logger):
        """测试注册时的日志记录"""
        ChatProviderFactory.register(ChatPlatform.FEISHU, MockChatProvider)
        
        mock_logger.debug.assert_called_once_with(
            "已注册群聊提供者: feishu -> MockChatProvider"
        )
    
    @patch('apps.automation.services.chat.factory.logger')
    def test_logging_on_get_provider_error(self, mock_logger):
        """测试获取提供者失败时的日志记录"""
        # 创建会抛出异常的提供者类
        class ErrorProvider(MockChatProvider):
            def __init__(self):
                raise ValueError("Test error")
        
        ChatProviderFactory.register(ChatPlatform.FEISHU, ErrorProvider)
        
        with pytest.raises(ConfigurationException):
            ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
        
        mock_logger.error.assert_called_once()
        assert "创建群聊提供者实例失败" in mock_logger.error.call_args[0][0]
