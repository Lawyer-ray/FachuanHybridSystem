from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib import messages

from ..models import CaseChat
from ..services.case_chat_service import CaseChatService
from ..exceptions import ChatProviderException

try:
    import nested_admin
    BaseTabularInline = nested_admin.NestedTabularInline
except Exception:
    BaseTabularInline = admin.TabularInline


def _get_case_chat_service():
    """工厂函数获取案件群聊服务"""
    return CaseChatService()


@admin.register(CaseChat)
class CaseChatAdmin(admin.ModelAdmin):
    """案件群聊管理"""
    
    list_display = (
        'name', 
        'chat_id_display', 
        'platform_display', 
        'case_link',
        'status_display',
        'created_at'
    )
    
    list_filter = (
        'platform',
        'is_active',
        'created_at'
    )
    
    search_fields = (
        'name',
        'chat_id',
        'case__name'
    )
    
    readonly_fields = (
        'chat_id',
        'created_at',
        'updated_at'
    )
    
    fields = (
        'case',
        'platform',
        'chat_id',
        'name',
        'is_active',
        'created_at',
        'updated_at'
    )
    
    ordering = ('-created_at',)
    
    actions = ['unbind_selected_chats']
    
    change_form_template = 'admin/cases/casechat/change_form.html'
    
    def chat_id_display(self, obj):
        """显示群聊ID（截断显示）"""
        if obj.chat_id:
            if len(obj.chat_id) > 20:
                return f"{obj.chat_id[:20]}..."
            return obj.chat_id
        return "-"
    chat_id_display.short_description = _('群聊ID')
    
    def platform_display(self, obj):
        """显示平台（带图标）"""
        platform_icons = {
            'feishu': '🚀',
            'dingtalk': '📱',
            'wechat_work': '💬',
            'telegram': '✈️',
            'slack': '💼'
        }
        icon = platform_icons.get(obj.platform, '📢')
        return f"{icon} {obj.get_platform_display()}"
    platform_display.short_description = _('平台')
    
    def case_link(self, obj):
        """案件链接"""
        if obj.case:
            url = reverse('admin:cases_case_change', args=[obj.case.pk])
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url,
                obj.case.name
            )
        return "-"
    case_link.short_description = _('关联案件')
    
    def status_display(self, obj):
        """状态显示"""
        if obj.is_active:
            return format_html(
                '<span style="color: green;">●</span> 有效'
            )
        else:
            return format_html(
                '<span style="color: red;">●</span> 已解绑'
            )
    status_display.short_description = _('状态')
    
    def unbind_selected_chats(self, request, queryset):
        """批量解除绑定群聊"""
        service = _get_case_chat_service()
        success_count = 0
        
        for chat in queryset.filter(is_active=True):
            try:
                if service.unbind_chat(chat.id):
                    success_count += 1
            except Exception as e:
                messages.error(
                    request,
                    f"解除绑定群聊 {chat.name} 失败: {str(e)}"
                )
        
        if success_count > 0:
            messages.success(
                request,
                f"成功解除绑定 {success_count} 个群聊"
            )
    
    unbind_selected_chats.short_description = _("解除绑定选中的群聊")
    
    def has_add_permission(self, request):
        """禁止直接添加群聊记录"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """禁止删除群聊记录"""
        return False
    
    def response_change(self, request, obj):
        """处理自定义操作"""
        if "_unbind_chat" in request.POST:
            service = _get_case_chat_service()
            try:
                if service.unbind_chat(obj.id):
                    messages.success(
                        request,
                        f"成功解除绑定群聊: {obj.name}"
                    )
                else:
                    messages.error(
                        request,
                        f"解除绑定群聊失败: {obj.name}"
                    )
            except Exception as e:
                messages.error(
                    request,
                    f"解除绑定群聊时发生错误: {str(e)}"
                )
            
            # 重定向到列表页面
            return HttpResponseRedirect(
                reverse('admin:cases_casechat_changelist')
            )
        
        return super().response_change(request, obj)


class CaseChatInline(BaseTabularInline):
    """案件群聊内联管理"""
    
    model = CaseChat
    extra = 0
    
    fields = (
        'platform_display',
        'name',
        'chat_id_display',
        'status_display',
        'created_at'
    )
    
    readonly_fields = (
        'platform_display',
        'name',
        'chat_id_display',
        'status_display',
        'created_at'
    )
    
    ordering = ('platform', '-created_at')
    
    def platform_display(self, obj):
        """显示平台（带图标）"""
        if not obj.pk:
            return ""
        
        platform_icons = {
            'feishu': '🚀',
            'dingtalk': '📱',
            'wechat_work': '💬',
            'telegram': '✈️',
            'slack': '💼'
        }
        icon = platform_icons.get(obj.platform, '📢')
        return f"{icon} {obj.get_platform_display()}"
    platform_display.short_description = _('平台')
    
    def chat_id_display(self, obj):
        """显示群聊ID（截断显示）"""
        if not obj.pk or not obj.chat_id:
            return ""
        
        if len(obj.chat_id) > 15:
            return f"{obj.chat_id[:15]}..."
        return obj.chat_id
    chat_id_display.short_description = _('群聊ID')
    
    def status_display(self, obj):
        """状态显示"""
        if not obj.pk:
            return ""
        
        if obj.is_active:
            return format_html(
                '<span style="color: green;">●</span> 有效'
            )
        else:
            return format_html(
                '<span style="color: red;">●</span> 已解绑'
            )
    status_display.short_description = _('状态')
    
    def has_add_permission(self, request, obj=None):
        """禁止直接添加群聊记录"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """禁止删除群聊记录"""
        return False