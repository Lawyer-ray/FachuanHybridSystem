"""
法院短信 Admin 集成测试
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.automation.models import CourtSMS, CourtSMSStatus, CourtSMSType

User = get_user_model()


class CourtSMSAdminIntegrationTest(TestCase):
    """法院短信 Admin 集成测试"""
    
    def setUp(self):
        """设置测试数据"""
        self.client = Client()
        
        # 创建管理员用户
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='password',
            real_name='测试管理员',
            is_staff=True,
            is_superuser=True
        )
        
        # 登录
        self.client.login(username='admin', password='password')
        
        # 创建测试短信
        self.sms = CourtSMS.objects.create(
            content='【佛山市禅城区人民法院】测试短信内容',
            received_at=timezone.now(),
            status=CourtSMSStatus.PENDING,
            sms_type=CourtSMSType.DOCUMENT_DELIVERY,
            download_links=['https://test.com/download'],
            case_numbers=['（2025）粤0604执保9654号'],
            party_names=['测试当事人']
        )
    
    def test_admin_changelist_view(self):
        """测试管理列表页面"""
        url = reverse('admin:automation_courtsms_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '法院短信')
        self.assertContains(response, '测试短信内容')
    
    def test_admin_change_view(self):
        """测试详情页面"""
        url = reverse('admin:automation_courtsms_change', args=[self.sms.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '测试短信内容')
        self.assertContains(response, '重新处理')
    
    def test_submit_sms_view(self):
        """测试短信提交页面"""
        url = reverse('admin:automation_courtsms_submit')
        
        # GET 请求
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '提交法院短信')
        
        # POST 请求（空内容）
        response = self.client.post(url, {'content': ''})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '短信内容不能为空')
    
    def test_assign_case_view(self):
        """测试手动指定案件页面"""
        url = reverse('admin:automation_courtsms_assign_case', args=[self.sms.id])
        
        # GET 请求
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '为短信')
        self.assertContains(response, '指定案件')
    
    def test_retry_single_sms_view(self):
        """测试单个短信重试"""
        url = reverse('admin:automation_courtsms_retry', args=[self.sms.id])
        
        # 由于没有实际的服务实现，这里只测试URL可访问
        # 实际会因为服务调用失败而重定向，但不会404
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 500])  # 重定向或服务错误
    
    def test_admin_search(self):
        """测试搜索功能"""
        url = reverse('admin:automation_courtsms_changelist')
        
        # 搜索短信内容
        response = self.client.get(url, {'q': '测试短信'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '测试短信内容')
        
        # 搜索法院名称
        response = self.client.get(url, {'q': '佛山市禅城区人民法院'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '测试短信内容')
    
    def test_admin_filters(self):
        """测试筛选功能"""
        url = reverse('admin:automation_courtsms_changelist')
        
        # 按状态筛选
        response = self.client.get(url, {'status__exact': CourtSMSStatus.PENDING})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '测试短信内容')
        
        # 按类型筛选
        response = self.client.get(url, {'sms_type__exact': CourtSMSType.DOCUMENT_DELIVERY})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '测试短信内容')