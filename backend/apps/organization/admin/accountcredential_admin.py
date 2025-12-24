"""
AccountCredential Admin - 账号凭证管理
遵循 Admin 层规范：UI配置、显示格式化，业务逻辑委托给 Service
"""
from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.utils import timezone
from django.contrib import messages

from ..models import AccountCredential


def _get_admin_service():
    """工厂函数 - 创建 AccountCredentialAdminService 实例"""
    from ..services import AccountCredentialAdminService
    return AccountCredentialAdminService()


@admin.register(AccountCredential)
class AccountCredentialAdmin(admin.ModelAdmin):
    """账号凭证管理 - 支持自动Token获取功能"""
    
    list_display = [
        "id", 
        "lawyer", 
        "site_name", 
        "account", 
        "login_statistics_display",
        "success_rate_display",
        "last_login_display",
        "is_preferred",
        "auto_login_button",
        "created_at"
    ]
    
    search_fields = ("site_name", "url", "account", "lawyer__username", "lawyer__real_name")
    
    list_filter = [
        "site_name",
        "is_preferred", 
        "lawyer",
        "last_login_success_at",
        "created_at"
    ]
    
    autocomplete_fields = ("lawyer",)

    readonly_fields = [
        "id",
        "login_statistics_display",
        "success_rate_display", 
        "last_login_display",
        "created_at",
        "updated_at"
    ]
    
    fieldsets = (
        ('基本信息', {
            'fields': ('id', 'lawyer', 'site_name', 'url', 'account', 'password')
        }),
        ('登录统计', {
            'fields': (
                'login_statistics_display',
                'success_rate_display',
                'last_login_display',
                'is_preferred'
            )
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    ordering = ['-last_login_success_at', '-login_success_count', 'login_failure_count']
    
    date_hierarchy = 'last_login_success_at'
    
    list_per_page = 50
    
    actions = ['mark_as_preferred', 'unmark_as_preferred']

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'password' in form.base_fields:
            form.base_fields['password'].widget = forms.PasswordInput(render_value=True)
        return form
    
    def login_statistics_display(self, obj):
        """显示登录统计信息"""
        return format_html(
            '<span style="color: #28a745; font-weight: bold;">{}</span> / '
            '<span style="color: #dc3545;">{}</span>',
            obj.login_success_count,
            obj.login_failure_count
        )
    login_statistics_display.short_description = "成功/失败次数"
    
    def success_rate_display(self, obj):
        """显示登录成功率"""
        rate = obj.success_rate * 100
        
        if rate >= 80:
            color = "#28a745"
        elif rate >= 50:
            color = "#ffc107"
        else:
            color = "#dc3545"
        
        rate_str = f"{rate:.1f}%"
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            rate_str
        )
    success_rate_display.short_description = "成功率"

    def last_login_display(self, obj):
        """显示最后登录时间"""
        if not obj.last_login_success_at:
            return format_html('<span style="color: #999;">从未成功</span>')
        
        now = timezone.now()
        delta = now - obj.last_login_success_at
        
        if delta.days > 30:
            color = "#dc3545"
            time_str = f"{delta.days}天前"
        elif delta.days > 7:
            color = "#ffc107"
            time_str = f"{delta.days}天前"
        elif delta.days > 0:
            color = "#007bff"
            time_str = f"{delta.days}天前"
        else:
            hours = delta.seconds // 3600
            if hours > 0:
                color = "#28a745"
                time_str = f"{hours}小时前"
            else:
                minutes = delta.seconds // 60
                color = "#28a745"
                time_str = f"{minutes}分钟前"
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            time_str
        )
    last_login_display.short_description = "最后成功登录"
    
    def auto_login_button(self, obj):
        """操作按钮 - 查看历史"""
        if obj.site_name == "court_zxfw":
            return format_html(
                '<a class="button" href="/admin/automation/tokenacquisitionhistory/?credential_id={}" '
                'style="background-color: #28a745; color: white; padding: 5px 8px; '
                'border-radius: 4px; text-decoration: none; display: inline-block; font-size: 12px;">'
                '📊 查看历史</a>',
                obj.id
            )
        else:
            return format_html('<span style="color: #999;">不支持</span>')
    auto_login_button.short_description = "操作"

    @admin.action(description="标记为优先账号")
    def mark_as_preferred(self, request, queryset):
        """标记为优先账号"""
        count = queryset.update(is_preferred=True)
        self.message_user(request, f"已将 {count} 个账号标记为优先使用")
    
    @admin.action(description="取消优先标记")
    def unmark_as_preferred(self, request, queryset):
        """取消优先标记"""
        count = queryset.update(is_preferred=False)
        self.message_user(request, f"已取消 {count} 个账号的优先标记")
    
    def get_queryset(self, request):
        """优化查询性能"""
        qs = super().get_queryset(request)
        return qs.select_related('lawyer')
    

