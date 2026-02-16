"""
Token获取管理界面集成测试
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.automation.models import TokenAcquisitionHistory, TokenAcquisitionStatus
from apps.organization.models import AccountCredential, LawFirm


User = get_user_model()


@pytest.mark.django_db
class TestTokenAcquisitionAdmin(TestCase):
    """Token获取管理界面测试"""
    
    def setUp(self):
        """设置测试数据"""
        # 创建管理员用户
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        
        # 创建律所和律师
        self.law_firm = LawFirm.objects.create(name="测试律所")
        self.lawyer = User.objects.create_user(
            username='lawyer1',
            email='lawyer1@test.com',
            password='testpass123',
            law_firm=self.law_firm
        )
        
        # 创建账号凭证
        self.credential = AccountCredential.objects.create(
            lawyer=self.lawyer,
            site_name="court_zxfw",
            url="https://zxfw.court.gov.cn",
            account="test_account",
            password="test_password",
            login_success_count=5,
            login_failure_count=1,
            last_login_success_at=timezone.now() - timedelta(hours=1)
        )
        
        # 创建Token获取历史记录
        self.create_test_history_records()
        
        # 创建客户端并登录
        self.client = Client()
        self.client.login(username='admin', password='testpass123')
    
    def create_test_history_records(self):
        """创建测试历史记录"""
        now = timezone.now()
        
        # 成功记录
        for i in range(3):
            TokenAcquisitionHistory.objects.create(
                site_name="court_zxfw",
                account="test_account",
                credential_id=self.credential.id,
                status=TokenAcquisitionStatus.SUCCESS,
                trigger_reason="test_trigger",
                attempt_count=1,
                total_duration=10.5 + i,
                login_duration=8.0 + i,
                captcha_attempts=1,
                network_retries=0,
                token_preview="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                created_at=now - timedelta(hours=i),
                started_at=now - timedelta(hours=i),
                finished_at=now - timedelta(hours=i) + timedelta(seconds=10)
            )
        
        # 失败记录
        TokenAcquisitionHistory.objects.create(
            site_name="court_zxfw",
            account="test_account",
            credential_id=self.credential.id,
            status=TokenAcquisitionStatus.FAILED,
            trigger_reason="test_trigger",
            attempt_count=3,
            total_duration=30.0,
            captcha_attempts=3,
            network_retries=2,
            error_message="登录失败：验证码错误",
            error_details={
                "error_type": "CaptchaError",
                "attempts": 3
            },
            created_at=now - timedelta(hours=4),
            started_at=now - timedelta(hours=4),
            finished_at=now - timedelta(hours=4) + timedelta(seconds=30)
        )
    
    def test_token_acquisition_history_list_view(self):
        """测试Token获取历史列表页面"""
        url = reverse('admin:automation_tokenacquisitionhistory_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Token获取历史记录')
        self.assertContains(response, 'test_account')
        self.assertContains(response, '成功')
        self.assertContains(response, '失败')
        
        # 检查统计信息
        self.assertContains(response, '总记录数')
        self.assertContains(response, '成功记录')
        self.assertContains(response, '成功率')
    
    def test_token_acquisition_history_dashboard_view(self):
        """测试Token获取仪表板页面"""
        url = reverse('admin:automation_tokenacquisitionhistory_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Token获取仪表板')
        self.assertContains(response, '总获取次数')
        self.assertContains(response, '成功次数')
        self.assertContains(response, '总体成功率')
        self.assertContains(response, '平均耗时')
        
        # 检查图表和统计表格
        self.assertContains(response, '最近7天趋势')
        self.assertContains(response, '状态分布')
        self.assertContains(response, '网站统计')
        self.assertContains(response, '账号统计')
    
    def test_account_credential_list_view(self):
        """测试账号凭证列表页面"""
        url = reverse('admin:organization_accountcredential_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'test_account')
        self.assertContains(response, 'court_zxfw')
        
        # 检查登录统计显示
        self.assertContains(response, '成功/失败次数')
        self.assertContains(response, '成功率')
        self.assertContains(response, '最后成功登录')
        
        # 检查操作按钮
        self.assertContains(response, '测试登录')
        self.assertContains(response, '查看历史')
    
    def test_account_credential_auto_login_button_link(self):
        """测试账号凭证自动登录按钮链接"""
        url = reverse('admin:organization_accountcredential_changelist')
        response = self.client.get(url)
        
        # 检查自动登录链接
        auto_login_url = f'/admin/organization/accountcredential/{self.credential.id}/auto_login/'
        self.assertContains(response, auto_login_url)
        
        # 检查查看历史链接
        history_url = f'/admin/automation/tokenacquisitionhistory/?credential_id={self.credential.id}'
        self.assertContains(response, history_url)
    
    def test_token_acquisition_history_export_csv(self):
        """测试导出CSV功能"""
        # 先获取changelist页面
        changelist_url = reverse('admin:automation_tokenacquisitionhistory_changelist')
        response = self.client.get(changelist_url)
        self.assertEqual(response.status_code, 200)
        
        # 测试导出功能（通过POST请求模拟批量操作）
        history_ids = list(TokenAcquisitionHistory.objects.values_list('id', flat=True))
        
        export_data = {
            'action': 'export_to_csv',
            '_selected_action': history_ids,
        }
        
        response = self.client.post(changelist_url, export_data)
        
        # 检查响应
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertTrue(response['Content-Disposition'].startswith('attachment; filename="token_acquisition_history_'))
        
        # 检查CSV内容
        content = response.content.decode('utf-8-sig')  # 处理BOM
        self.assertIn('ID', content)
        self.assertIn('网站名称', content)
        self.assertIn('账号', content)
        self.assertIn('test_account', content)
    
    def test_token_acquisition_history_cleanup_old_records(self):
        """测试清理旧记录功能"""
        # 创建一个记录
        old_record = TokenAcquisitionHistory.objects.create(
            site_name="court_zxfw",
            account="old_account",
            status=TokenAcquisitionStatus.SUCCESS,
            trigger_reason="old_test",
            attempt_count=1,
            total_duration=10.0
        )
        
        # 使用 update() 设置 created_at 为35天前（绕过 auto_now_add）
        old_date = timezone.now() - timedelta(days=35)
        TokenAcquisitionHistory.objects.filter(id=old_record.id).update(created_at=old_date)
        
        # 执行清理操作
        changelist_url = reverse('admin:automation_tokenacquisitionhistory_changelist')
        cleanup_data = {
            'action': 'cleanup_old_records',
            '_selected_action': [old_record.id],
        }
        
        response = self.client.post(changelist_url, cleanup_data)
        
        # 检查响应
        self.assertEqual(response.status_code, 302)  # 重定向回列表页面
        
        # 检查记录是否被删除
        self.assertFalse(
            TokenAcquisitionHistory.objects.filter(id=old_record.id).exists()
        )
    
    def test_token_acquisition_history_reanalyze_performance(self):
        """测试重新分析性能功能"""
        changelist_url = reverse('admin:automation_tokenacquisitionhistory_changelist')
        history_ids = list(TokenAcquisitionHistory.objects.values_list('id', flat=True))
        
        analyze_data = {
            'action': 'reanalyze_performance',
            '_selected_action': history_ids,
        }
        
        response = self.client.post(changelist_url, analyze_data)
        
        # 检查响应
        self.assertEqual(response.status_code, 302)  # 重定向回列表页面
        
        # 跟随重定向检查消息
        response = self.client.get(changelist_url)
        self.assertContains(response, '分析完成')
    
    def test_account_credential_batch_trigger_auto_login(self):
        """测试批量触发自动登录功能"""
        changelist_url = reverse('admin:organization_accountcredential_changelist')
        
        batch_data = {
            'action': 'trigger_auto_login',
            '_selected_action': [self.credential.id],
        }
        
        # 注意：这个测试可能会失败，因为实际的自动登录需要浏览器环境
        # 但我们可以测试请求是否正确处理
        response = self.client.post(changelist_url, batch_data)
        
        # 检查响应（可能是重定向或错误页面）
        self.assertIn(response.status_code, [200, 302])
    
    def test_dashboard_statistics_calculation(self):
        """测试仪表板统计计算"""
        url = reverse('admin:automation_tokenacquisitionhistory_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # 检查上下文数据
        context = response.context
        self.assertEqual(context['total_records'], 4)  # 3成功 + 1失败
        self.assertEqual(context['success_records'], 3)
        self.assertEqual(context['success_rate'], 75.0)  # 3/4 * 100
        
        # 检查时间范围统计
        self.assertIn('time_stats', context)
        self.assertIn('24h', context['time_stats'])
        
        # 检查性能统计
        self.assertIn('performance_stats', context)
        self.assertIsNotNone(context['performance_stats']['avg_duration'])
    
    def test_empty_dashboard_view(self):
        """测试空数据时的仪表板"""
        # 删除所有历史记录
        TokenAcquisitionHistory.objects.all().delete()
        
        url = reverse('admin:automation_tokenacquisitionhistory_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # 检查空数据处理
        context = response.context
        self.assertEqual(context['total_records'], 0)
        self.assertEqual(context['success_records'], 0)
        self.assertEqual(context['success_rate'], 0)
    
    def test_admin_permissions(self):
        """测试管理界面权限"""
        # 创建普通用户
        normal_user = User.objects.create_user(
            username='normal',
            email='normal@test.com',
            password='testpass123'
        )
        
        # 使用普通用户登录
        client = Client()
        client.login(username='normal', password='testpass123')
        
        # 尝试访问管理界面
        url = reverse('admin:automation_tokenacquisitionhistory_changelist')
        response = client.get(url)
        
        # 应该被重定向到登录页面或显示权限错误
        self.assertIn(response.status_code, [302, 403])
    
    def tearDown(self):
        """清理测试数据"""
        # Django测试会自动回滚数据库，但我们可以在这里做额外清理
        pass


@pytest.mark.django_db
class TestTokenAcquisitionAdminIntegration(TestCase):
    """Token获取管理界面集成测试"""
    
    def test_admin_integration_with_services(self):
        """测试管理界面与服务的集成"""
        # 这个测试验证管理界面能正确导入和使用服务
        from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
        from apps.automation.services.token.account_selection_strategy import AccountSelectionStrategy
        from apps.automation.services.token.auto_login_service import AutoLoginService
        
        # 验证服务可以正常实例化
        auto_login_service = AutoLoginService()
        account_strategy = AccountSelectionStrategy()
        token_service = AutoTokenAcquisitionService(
            auto_login_service=auto_login_service,
            account_selection_strategy=account_strategy
        )
        
        # 验证服务有正确的方法
        self.assertTrue(hasattr(token_service, 'acquire_token_if_needed'))
        self.assertTrue(hasattr(account_strategy, 'select_account'))
        self.assertTrue(hasattr(auto_login_service, 'login_and_get_token'))
    
    def test_admin_url_patterns(self):
        """测试管理界面URL模式"""
        # 测试标准admin URL
        changelist_url = reverse('admin:automation_tokenacquisitionhistory_changelist')
        self.assertTrue(changelist_url.startswith('/admin/'))
        
        # 测试自定义dashboard URL
        dashboard_url = reverse('admin:automation_tokenacquisitionhistory_dashboard')
        self.assertTrue(dashboard_url.endswith('/dashboard/'))
        
        # 测试账号凭证URL
        credential_url = reverse('admin:organization_accountcredential_changelist')
        self.assertTrue(credential_url.startswith('/admin/'))