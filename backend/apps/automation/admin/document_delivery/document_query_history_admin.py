"""
文书查询历史 Django Admin 界面

提供查询历史记录管理、搜索、过滤等功能。
"""
import logging
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone

from apps.automation.models import DocumentQueryHistory

logger = logging.getLogger("apps.automation")


@admin.register(DocumentQueryHistory)
class DocumentQueryHistoryAdmin(admin.ModelAdmin):
    """文书查询历史管理"""
    
    # 列表显示字段
    list_display = [
        'id',
        'credential_display',
        'case_number',
        'send_time_display',
        'court_sms_display',
        'queried_at_display',
    ]
    
    # 列表筛选器
    list_filter = [
        'send_time',
        'queried_at',
        ('credential', admin.RelatedFieldListFilter),
        ('court_sms', admin.RelatedFieldListFilter),
    ]
    
    # 搜索字段
    search_fields = [
        'case_number',
        'credential__account',
        'credential__site_name',
    ]
    
    # 排序
    ordering = ['-queried_at']
    
    # 分页
    list_per_page = 50
    
    # 只读字段（查询历史应该是只读的）
    readonly_fields = [
        'id',
        'credential',
        'case_number',
        'send_time',
        'court_sms',
        'queried_at',
        'court_sms_link',
        'time_since_query',
    ]
    
    # 字段分组
    fieldsets = (
        ('查询信息', {
            'fields': (
                'id',
                'credential',
                'case_number',
                'send_time',
            )
        }),
        ('关联信息', {
            'fields': (
                'court_sms',
                'court_sms_link',
            )
        }),
        ('时间信息', {
            'fields': (
                'queried_at',
                'time_since_query',
            )
        }),
    )
    
    # 日期层次结构
    date_hierarchy = 'queried_at'
    
    def credential_display(self, obj):
        """账号凭证显示"""
        if obj.credential:
            url = reverse('admin:organization_accountcredential_change', args=[obj.credential.id])
            return format_html(
                '<a href="{}" target="_blank">{}</a><br>'
                '<small style="color: #666;">{}</small>',
                url,
                obj.credential.account,
                obj.credential.site_name
            )
        return '-'
    credential_display.short_description = '账号凭证'
    
    def send_time_display(self, obj):
        """文书发送时间显示"""
        now = timezone.now()
        time_diff = now - obj.send_time
        
        if time_diff.days > 0:
            time_str = f"{time_diff.days} 天前"
            color = "#666"
        elif time_diff.seconds > 3600:
            hours = time_diff.seconds // 3600
            time_str = f"{hours} 小时前"
            color = "#666"
        elif time_diff.seconds > 60:
            minutes = time_diff.seconds // 60
            time_str = f"{minutes} 分钟前"
            color = "blue"
        else:
            time_str = "刚刚"
            color = "green"
        
        return format_html(
            '<span style="color: {};">{}</span><br>'
            '<small style="color: #666;">{}</small>',
            color,
            time_str,
            obj.send_time.strftime('%Y-%m-%d %H:%M')
        )
    send_time_display.short_description = '文书发送时间'
    
    def court_sms_display(self, obj):
        """关联短信显示"""
        if obj.court_sms:
            url = reverse('admin:automation_courtsms_change', args=[obj.court_sms.id])
            
            # 根据短信状态显示不同颜色
            status_colors = {
                'pending': 'orange',
                'parsing': 'blue',
                'downloading': 'blue',
                'download_failed': 'red',
                'matching': 'blue',
                'pending_manual': 'orange',
                'renaming': 'blue',
                'notifying': 'blue',
                'completed': 'green',
                'failed': 'red',
            }
            color = status_colors.get(obj.court_sms.status, 'gray')
            
            return format_html(
                '<a href="{}" target="_blank">短信 #{}</a><br>'
                '<small style="color: {};">{}</small>',
                url,
                obj.court_sms.id,
                color,
                obj.court_sms.get_status_display()
            )
        return format_html('<span style="color: gray;">无关联短信</span>')
    court_sms_display.short_description = '关联短信'
    
    def queried_at_display(self, obj):
        """查询时间显示"""
        now = timezone.now()
        time_diff = now - obj.queried_at
        
        if time_diff.days > 0:
            time_str = f"{time_diff.days} 天前"
            color = "#666"
        elif time_diff.seconds > 3600:
            hours = time_diff.seconds // 3600
            time_str = f"{hours} 小时前"
            color = "#666"
        elif time_diff.seconds > 60:
            minutes = time_diff.seconds // 60
            time_str = f"{minutes} 分钟前"
            color = "blue"
        else:
            time_str = "刚刚"
            color = "green"
        
        return format_html(
            '<span style="color: {};">{}</span><br>'
            '<small style="color: #666;">{}</small>',
            color,
            time_str,
            obj.queried_at.strftime('%Y-%m-%d %H:%M')
        )
    queried_at_display.short_description = '查询时间'
    
    def court_sms_link(self, obj):
        """关联短信链接"""
        if obj.court_sms:
            url = reverse('admin:automation_courtsms_change', args=[obj.court_sms.id])
            return format_html(
                '<a href="{}" target="_blank">查看短信 #{} - {}</a>',
                url,
                obj.court_sms.id,
                obj.court_sms.get_status_display()
            )
        return '-'
    court_sms_link.short_description = '关联短信链接'
    
    def time_since_query(self, obj):
        """查询后经过的时间"""
        now = timezone.now()
        time_diff = now - obj.queried_at
        
        total_seconds = int(time_diff.total_seconds())
        days = time_diff.days
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        if days > 0:
            return f"{days} 天 {hours % 24} 小时前"
        elif hours > 0:
            return f"{hours} 小时 {minutes} 分钟前"
        elif minutes > 0:
            return f"{minutes} 分钟前"
        else:
            return "刚刚"
    time_since_query.short_description = '查询后经过时间'
    
    def has_add_permission(self, request):
        """禁用添加功能（查询历史应该由系统自动创建）"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """禁用修改功能（查询历史应该是只读的）"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """允许删除功能（用于清理旧记录）"""
        return True
    
    def get_actions(self, request):
        """自定义批量操作"""
        actions = super().get_actions(request)
        
        # 添加批量删除旧记录的操作
        actions['delete_old_records'] = (
            self.delete_old_records,
            'delete_old_records',
            '删除30天前的记录'
        )
        
        return actions
    
    def delete_old_records(self, request, queryset):
        """批量删除30天前的记录"""
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=30)
        old_records = queryset.filter(queried_at__lt=cutoff_date)
        count = old_records.count()
        
        old_records.delete()
        
        self.message_user(
            request,
            f"成功删除 {count} 条30天前的查询记录"
        )
        logger.info(f"管理员批量删除旧查询记录: Count={count}, User={request.user}")
    delete_old_records.short_description = "删除30天前的记录"
    
    def get_queryset(self, request):
        """优化查询性能"""
        return super().get_queryset(request).select_related(
            'credential',
            'court_sms'
        )
    
    def get_search_results(self, request, queryset, search_term):
        """自定义搜索，支持案号模糊匹配"""
        queryset, may_have_duplicates = super().get_search_results(
            request, queryset, search_term
        )
        
        # 如果搜索词看起来像案号（包含年份和法院标识），进行特殊处理
        if search_term and ('(' in search_term or '）' in search_term or '年' in search_term):
            # 案号的模糊搜索
            queryset |= self.model.objects.filter(
                case_number__icontains=search_term.replace('(', '').replace(')', '').replace('（', '').replace('）', '')
            )
            may_have_duplicates = True
        
        return queryset, may_have_duplicates