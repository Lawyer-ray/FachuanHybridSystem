"""
Token 管理 Admin
提供 Token 的查看、搜索、过滤功能
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from ...models import CourtToken


@admin.register(CourtToken)
class CourtTokenAdmin(admin.ModelAdmin):
    """
    Token 管理 Admin
    
    功能：
    - 查看所有 Token
    - 按网站、账号搜索
    - 按过期状态过滤
    - 显示 Token 状态（有效/过期）
    """
    
    list_display = [
        'id',
        'site_name',
        'account',
        'token_preview',
        'token_type',
        'status_display',
        'expires_at',
        'created_at',
        'updated_at',
    ]
    
    list_filter = [
        'site_name',
        'token_type',
        'created_at',
        'expires_at',
    ]
    
    search_fields = [
        'site_name',
        'account',
        'token',
    ]
    
    readonly_fields = [
        'id',
        'token_full',
        'status_display',
        'remaining_time',
        'created_at',
        'updated_at',
    ]
    
    fieldsets = (
        ('基本信息', {
            'fields': ('id', 'site_name', 'account', 'token_type')
        }),
        ('Token 信息', {
            'fields': ('token_full', 'status_display', 'remaining_time')
        }),
        ('时间信息', {
            'fields': ('expires_at', 'created_at', 'updated_at')
        }),
    )
    
    ordering = ['-created_at']
    
    date_hierarchy = 'created_at'
    
    # 每页显示数量
    list_per_page = 50
    
    def token_preview(self, obj):
        """Token 预览（只显示前20个字符）"""
        if len(obj.token) > 20:
            return f"{obj.token[:20]}..."
        return obj.token
    token_preview.short_description = "Token 预览"
    
    def token_full(self, obj):
        """完整的 Token（在详情页显示）"""
        return format_html(
            '<textarea readonly style="width: 100%; height: 100px; '
            'font-family: monospace; font-size: 12px; padding: 10px; '
            'border: 1px solid #ddd; border-radius: 4px;">{}</textarea>',
            obj.token
        )
    token_full.short_description = "完整 Token"
    
    def status_display(self, obj):
        """显示 Token 状态（有效/过期）"""
        if obj.is_expired():
            return format_html(
                '<span style="color: red; font-weight: bold;">❌ 已过期</span>'
            )
        else:
            return format_html(
                '<span style="color: green; font-weight: bold;">✅ 有效</span>'
            )
    status_display.short_description = "状态"
    
    def remaining_time(self, obj):
        """剩余有效时间"""
        if obj.is_expired():
            return format_html(
                '<span style="color: red;">已过期</span>'
            )
        
        now = timezone.now()
        remaining = obj.expires_at - now
        
        # 转换为易读格式
        total_seconds = int(remaining.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            time_str = f"{hours} 小时 {minutes} 分钟"
        elif minutes > 0:
            time_str = f"{minutes} 分钟 {seconds} 秒"
        else:
            time_str = f"{seconds} 秒"
        
        # 根据剩余时间显示不同颜色
        if total_seconds < 300:  # 小于 5 分钟
            color = "red"
        elif total_seconds < 1800:  # 小于 30 分钟
            color = "orange"
        else:
            color = "green"
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            time_str
        )
    remaining_time.short_description = "剩余时间"
    
    def has_add_permission(self, request):
        """禁用添加功能（Token 应该由系统自动创建）"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """禁用修改功能（Token 应该由系统管理）"""
        return False
    
    def get_actions(self, request):
        """自定义批量操作"""
        actions = super().get_actions(request)
        
        # 添加批量删除过期 Token 的操作
        actions['delete_expired_tokens'] = (
            self.delete_expired_tokens,
            'delete_expired_tokens',
            '删除已过期的 Token'
        )
        
        return actions
    
    def delete_expired_tokens(self, request, queryset):
        """批量删除过期的 Token"""
        expired_tokens = [token for token in queryset if token.is_expired()]
        count = len(expired_tokens)
        
        for token in expired_tokens:
            token.delete()
        
        self.message_user(
            request,
            f"成功删除 {count} 个已过期的 Token"
        )
    delete_expired_tokens.short_description = "删除已过期的 Token"