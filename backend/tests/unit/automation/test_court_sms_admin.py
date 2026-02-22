"""
法院短信 Admin 单元测试
"""

from unittest.mock import Mock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.automation.admin.sms.court_sms_admin import CourtSMSAdmin
from apps.automation.models import CourtSMS, CourtSMSStatus, CourtSMSType
from apps.organization.models import Lawyer


class CourtSMSAdminTest(TestCase):
    """法院短信 Admin 测试"""

    def setUp(self):
        """设置测试数据"""
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = CourtSMSAdmin(CourtSMS, self.site)

        # 创建测试用户
        self.user = Lawyer.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="password",
            real_name="测试管理员",
            is_staff=True,
            is_superuser=True,
        )

        # 创建测试短信
        self.sms = CourtSMS.objects.create(
            content="【佛山市禅城区人民法院】测试短信内容",
            received_at=timezone.now(),
            status=CourtSMSStatus.PENDING,
            sms_type=CourtSMSType.DOCUMENT_DELIVERY,
            download_links=["https://test.com/download"],
            case_numbers=["（2025）粤0604执保9654号"],
            party_names=["测试当事人"],
        )

    def test_list_display_methods(self):
        """测试列表显示方法"""
        # 测试状态显示
        status_display = self.admin.status_display(self.sms)
        self.assertIn("待处理", status_display)
        self.assertIn("orange", status_display)

        # 测试短信类型显示
        type_display = self.admin.sms_type_display(self.sms)
        self.assertIn("📄", type_display)
        self.assertIn("文书送达", type_display)

        # 测试内容预览
        content_preview = self.admin.content_preview(self.sms)
        self.assertIn("测试短信内容", content_preview)

        # 测试下载链接显示
        links_display = self.admin.has_download_links(self.sms)
        self.assertIn("✓ 1 个链接", links_display)

    def test_readonly_field_methods(self):
        """测试只读字段方法"""
        # 测试案号显示
        case_numbers_display = self.admin.case_numbers_display(self.sms)
        self.assertIn("（2025）粤0604执保9654号", case_numbers_display)

        # 测试当事人显示
        party_names_display = self.admin.party_names_display(self.sms)
        self.assertIn("测试当事人", party_names_display)

        # 测试下载链接详情显示
        download_links_display = self.admin.download_links_display(self.sms)
        self.assertIn("https://test.com/download", download_links_display)

        # 测试重试按钮
        retry_button = self.admin.retry_button(self.sms)
        self.assertIn("重新处理", retry_button)
        self.assertIn(f"/admin/automation/courtsms/{self.sms.id}/retry/", retry_button)

    @patch("apps.automation.admin.sms.court_sms_admin_actions._get_court_sms_service")
    def test_retry_processing_action(self, mock_get_service):
        """测试重新处理操作"""
        # 模拟服务
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 创建请求
        request = self.factory.post("/admin/automation/courtsms/")
        request.user = self.user
        request._messages = Mock()  # type: ignore[attr-defined]

        # 执行操作
        queryset = CourtSMS.objects.filter(id=self.sms.id)
        self.admin.retry_processing_action(request, queryset)

        # 验证服务调用
        mock_service.retry_processing.assert_called_once_with(self.sms.id)

    def test_submit_sms_view_get(self):
        """测试短信提交页面 GET 请求"""
        request = self.factory.get("/admin/automation/courtsms/submit/")
        request.user = self.user

        response = self.admin.submit_sms_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("提交法院短信", response.content.decode())

    @patch("apps.automation.admin.sms.court_sms_admin_actions._get_court_sms_service")
    def test_submit_sms_view_post_success(self, mock_get_service):
        """测试短信提交页面 POST 成功"""
        # 模拟服务
        mock_service = Mock()
        mock_sms = Mock()
        mock_sms.id = 123
        mock_service.submit_sms.return_value = mock_sms
        mock_get_service.return_value = mock_service

        # 创建请求
        request = self.factory.post("/admin/automation/courtsms/submit/", {"content": "测试短信内容"})
        request.user = self.user
        request._messages = Mock()  # type: ignore[attr-defined]

        response = self.admin.submit_sms_view(request)

        # 验证重定向
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/automation/courtsms/123/change/", response.url)  # type: ignore[attr-defined]

        # 验证服务调用
        mock_service.submit_sms.assert_called_once()

    def test_submit_sms_view_post_empty_content(self):
        """测试短信提交页面 POST 空内容"""
        from django.contrib.messages.storage.fallback import FallbackStorage

        request = self.factory.post("/admin/automation/courtsms/submit/", {"content": ""})
        request.user = self.user

        # 设置消息存储
        request.session = {}  # type: ignore[assignment]
        request._messages = FallbackStorage(request)  # type: ignore[attr-defined]

        response = self.admin.submit_sms_view(request)

        # 应该返回表单页面而不是重定向
        self.assertEqual(response.status_code, 200)

    def test_get_queryset_optimization(self):
        """测试查询优化"""
        request = self.factory.get("/admin/automation/courtsms/")
        request.user = self.user

        queryset = self.admin.get_queryset(request)

        # 验证使用了 select_related
        self.assertIn("case", queryset.query.select_related)  # type: ignore[arg-type]
        self.assertIn("scraper_task", queryset.query.select_related)  # type: ignore[arg-type]
        self.assertIn("case_log", queryset.query.select_related)  # type: ignore[arg-type]

    def test_custom_urls(self):
        """测试自定义 URL"""
        urls = self.admin.get_urls()

        # 检查自定义 URL 是否存在
        url_names = [url.name for url in urls if hasattr(url, "name")]

        self.assertIn("automation_courtsms_submit", url_names)
        self.assertIn("automation_courtsms_assign_case", url_names)
        self.assertIn("automation_courtsms_retry", url_names)
