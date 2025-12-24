"""
测试功能 Admin
提供在 Admin 后台测试登录、立案、查询等功能
"""
from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils.html import format_html
from ...models import TestCourt
from ...services.scraper.test_service import TestService


def _get_test_service():
    """工厂函数：创建测试服务实例"""
    return TestService()



@admin.register(TestCourt)
class TestCourtAdmin(admin.ModelAdmin):
    """
    测试法院系统 Admin
    
    使用 TestCourt 作为占位模型
    提供测试功能的入口，支持 Token 捕获
    """
    
    # 自定义列表页
    def changelist_view(self, request, extra_context=None):
        """自定义列表页 - 显示测试选项"""
        # 通过ServiceLocator获取organization服务
        from apps.core.interfaces import ServiceLocator
        organization_service = ServiceLocator.get_organization_service()
        
        # 获取所有账号凭证
        credentials = organization_service.get_all_credentials_internal()
        
        context = {
            'title': '测试法院系统',
            'credentials': credentials,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
            'site_header': self.admin_site.site_header,
            'site_title': self.admin_site.site_title,
        }
        
        return TemplateResponse(request, "admin/automation/test_court_list.html", context)
    
    def has_add_permission(self, request):
        """禁用添加功能"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """禁用删除功能"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """禁用修改功能"""
        return False
    
    def get_urls(self):
        """添加自定义 URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                'test-login/<int:credential_id>/',
                self.admin_site.admin_view(self.test_credential_login_view),
                name='automation_testcourt_test_login',
            ),
        ]
        return custom_urls + urls
    
    def test_credential_login_view(self, request, credential_id):
        """
        测试账号凭证登录
        
        Admin 层只负责：
        1. 参数验证
        2. 调用 Service
        3. 渲染结果
        """
        from django.contrib import messages
        
        # 1. 获取凭证（用于显示）
        try:
            # 通过ServiceLocator获取organization服务
            from apps.core.interfaces import ServiceLocator
            organization_service = ServiceLocator.get_organization_service()
            credential = organization_service.get_credential_internal(credential_id)
        except Exception:
            messages.error(request, f"凭证 ID {credential_id} 不存在")
            return redirect('admin:organization_accountcredential_changelist')
        
        # 2. 调用 Service 执行测试
        test_service = _get_test_service()
        result = test_service.test_login(credential_id)
        
        # 3. 渲染结果页面
        context = {
            "title": f"测试登录: {credential.site_name}",
            "credential": credential,
            "result": result,
            "site_header": self.admin_site.site_header,
            "site_title": self.admin_site.site_title,
        }
        
        return TemplateResponse(request, "admin/automation/test_court_result.html", context)