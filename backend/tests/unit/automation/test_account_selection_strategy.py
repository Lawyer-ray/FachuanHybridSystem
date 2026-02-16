"""
账号选择策略服务单元测试
"""
import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timedelta
from django.utils import timezone

from apps.automation.services.token.account_selection_strategy import AccountSelectionStrategy
from apps.core.interfaces import AccountCredentialDTO
from apps.core.exceptions import ValidationException


@pytest.mark.django_db
class TestAccountSelectionStrategy:
    """账号选择策略测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.strategy = AccountSelectionStrategy()
    
    def test_init_with_default_blacklist_duration(self):
        """测试默认黑名单持续时间初始化"""
        strategy = AccountSelectionStrategy()
        assert strategy.blacklist_duration_hours == 1
        assert strategy._blacklist == []
    
    def test_init_with_custom_blacklist_duration(self):
        """测试自定义黑名单持续时间初始化"""
        strategy = AccountSelectionStrategy(blacklist_duration_hours=2)
        assert strategy.blacklist_duration_hours == 2
    
    @pytest.mark.anyio
    async def test_select_account_empty_site_name(self):
        """测试空网站名称抛出异常"""
        with pytest.raises(ValidationException, match="网站名称不能为空"):
            await self.strategy.select_account("")
    
    def test_blacklist_operations(self):
        """测试黑名单操作"""
        # 添加到黑名单
        self.strategy.add_to_blacklist("test_account")
        assert "test_account" in self.strategy.get_blacklist()
        
        # 重复添加不会重复
        self.strategy.add_to_blacklist("test_account")
        assert self.strategy.get_blacklist().count("test_account") == 1
        
        # 从黑名单移除
        self.strategy.remove_from_blacklist("test_account")
        assert "test_account" not in self.strategy.get_blacklist()
        
        # 移除不存在的账号不会报错
        self.strategy.remove_from_blacklist("non_existent")
        
        # 清空黑名单
        self.strategy.add_to_blacklist("account1")
        self.strategy.add_to_blacklist("account2")
        self.strategy.clear_blacklist()
        assert self.strategy.get_blacklist() == []
    
    def test_select_best_account_empty_list(self):
        """测试空账号列表抛出异常"""
        with pytest.raises(ValidationException, match="没有可用账号"):
            self.strategy._select_best_account([])
    
    def test_select_best_account_single_account(self):
        """测试单个账号选择"""
        account = AccountCredentialDTO(
            id=1,
            lawyer_id=1,
            site_name="test_site",
            url="http://test.com",
            account="test_account",
            password="password",
            login_success_count=5,
            login_failure_count=1,
            is_preferred=False
        )
        
        result = self.strategy._select_best_account([account])
        assert result == account
    
    def test_select_best_account_preferred_priority(self):
        """测试优先账号优先级"""
        now = timezone.now()
        
        # 普通账号，但最近登录过
        normal_account = AccountCredentialDTO(
            id=1,
            lawyer_id=1,
            site_name="test_site",
            url="http://test.com",
            account="normal_account",
            password="password",
            last_login_success_at=now.isoformat(),
            login_success_count=10,
            login_failure_count=0,
            is_preferred=False
        )
        
        # 优先账号，但从未登录过
        preferred_account = AccountCredentialDTO(
            id=2,
            lawyer_id=2,
            site_name="test_site",
            url="http://test.com",
            account="preferred_account",
            password="password",
            last_login_success_at=None,
            login_success_count=0,
            login_failure_count=0,
            is_preferred=True
        )
        
        result = self.strategy._select_best_account([normal_account, preferred_account])
        assert result == preferred_account  # 优先账号应该被选中
    
    def test_select_best_account_recency_priority(self):
        """测试最近登录时间优先级"""
        now = timezone.now()
        recent_time = now - timedelta(hours=1)
        old_time = now - timedelta(days=1)
        
        # 最近登录的账号
        recent_account = AccountCredentialDTO(
            id=1,
            lawyer_id=1,
            site_name="test_site",
            url="http://test.com",
            account="recent_account",
            password="password",
            last_login_success_at=recent_time.isoformat(),
            login_success_count=5,
            login_failure_count=1,
            is_preferred=False
        )
        
        # 较早登录的账号
        old_account = AccountCredentialDTO(
            id=2,
            lawyer_id=2,
            site_name="test_site",
            url="http://test.com",
            account="old_account",
            password="password",
            last_login_success_at=old_time.isoformat(),
            login_success_count=5,
            login_failure_count=1,
            is_preferred=False
        )
        
        result = self.strategy._select_best_account([old_account, recent_account])
        assert result == recent_account  # 最近登录的账号应该被选中
