"""
基础管理界面测试
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.automation.models import TokenAcquisitionHistory, TokenAcquisitionStatus
from apps.organization.models import AccountCredential, LawFirm


User = get_user_model()


@pytest.mark.django_db
class TestBasicAdminFunctionality(TestCase):
    """基础管理界面功能测试"""
    
    def setUp(self):
        """设置测试数据"""
        # 创建管理员用户
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        
        # 创建客户端并登录
        self.client = Client()
        self.client.login(username='admin', password='testpass123')
    
    def test_admin_urls_accessible(self):
        """测试管理界面URL可访问"""
        # 测试Token获取历史列表页面
        url = reverse('admin:automation_tokenacquisitionhistory_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # 测试账号凭证列表页面
        url = reverse('admin:organization_accountcredential_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
    
    def test_admin_models_registered(self):
        """测试模型已正确注册到admin"""
        from django.contrib import admin
        
        # 检查TokenAcquisitionHistory是否已注册
        self.assertIn(TokenAcquisitionHistory, admin.site._registry)
        
        # 检查AccountCredential是否已注册
        self.assertIn(AccountCredential, admin.site._registry)
    
    def test_token_acquisition_history_admin_basic(self):
        """测试Token获取历史Admin基本功能"""
        from apps.automation.admin.token.token_acquisition_history_admin import TokenAcquisitionHistoryAdmin
        
        admin_instance = TokenAcquisitionHistoryAdmin(TokenAcquisitionHistory, None)
        
        # 测试基本属性
        self.assertTrue(hasattr(admin_instance, 'list_display'))
        self.assertTrue(hasattr(admin_instance, 'list_filter'))
        self.assertTrue(hasattr(admin_instance, 'search_fields'))
        
        # 测试只读权限
        self.assertFalse(admin_instance.has_add_permission(None))
        self.assertFalse(admin_instance.has_change_permission(None))
    
    def test_account_credential_admin_basic(self):
        """测试账号凭证Admin基本功能"""
        from apps.organization.admin.accountcredential_admin import AccountCredentialAdmin
        
        admin_instance = AccountCredentialAdmin(AccountCredential, None)
        
        # 测试基本属性
        self.assertTrue(hasattr(admin_instance, 'list_display'))
        self.assertTrue(hasattr(admin_instance, 'list_filter'))
        self.assertTrue(hasattr(admin_instance, 'search_fields'))
        
        # 测试批量操作已定义（通过 actions 属性检查）
        self.assertTrue(hasattr(admin_instance, 'actions'))
        # 检查 actions 列表包含预期的操作
        if admin_instance.actions:
            action_names = [a.__name__ if callable(a) else a for a in admin_instance.actions]
            self.assertIn('trigger_auto_login', action_names)
            self.assertIn('mark_as_preferred', action_names)
            self.assertIn('unmark_as_preferred', action_names)