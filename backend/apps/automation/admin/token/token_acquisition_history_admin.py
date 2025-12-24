"""
Token获取历史记录 Admin
提供Token获取过程的详细历史记录查看功能
"""
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Q, Count, Avg
from ...models import TokenAcquisitionHistory, TokenAcquisitionStatus


def _get_token_history_admin_service():
    """工厂函数：创建Token历史管理服务"""
    from ...services.admin import TokenAcquisitionHistoryAdminService
    return TokenAcquisitionHistoryAdminService()


@admin.register(TokenAcquisitionHistory)
class TokenAcquisitionHistoryAdmin(admin.ModelAdmin):
    """
    Token获取历史记录管理 Admin
    
    功能：
    - 查看所有Token获取历史记录
    - 按网站、账号、状态搜索和过滤
    - 显示详细的执行统计信息
    - 查看错误详情和性能指标
    """
    
    list_display = [
        'id',
        'site_name',
        'account',
        'status_display',
        'trigger_reason_display',
        'performance_display',
        'attempts_display',
        'duration_display',
        'created_at',
    ]
    
    list_filter = [
        'status',
        'site_name',
        'trigger_reason',
        'created_at',
        'finished_at',
    ]
    
    search_fields = [
        'site_name',
        'account',
        'trigger_reason',
        'error_message',
    ]
    
    readonly_fields = [
        'id',
        'site_name',
        'account',
        'credential_id',
        'status',
        'trigger_reason',
        'attempt_count',
        'total_duration',
        'login_duration',
        'captcha_attempts',
        'network_retries',
        'token_preview',
        'error_message',
        'error_details_display',
        'performance_summary',
        'created_at',
        'started_at',
        'finished_at',
    ]
    
    fieldsets = (
        ('基本信息', {
            'fields': (
                'id',
                'site_name',
                'account',
                'credential_id',
                'trigger_reason',
            )
        }),
        ('执行结果', {
            'fields': (
                'status',
                'token_preview',
                'error_message',
                'error_details_display',
            )
        }),
        ('性能指标', {
            'fields': (
                'performance_summary',
                'attempt_count',
                'total_duration',
                'login_duration',
                'captcha_attempts',
                'network_retries',
            )
        }),
        ('时间信息', {
            'fields': (
                'created_at',
                'started_at',
                'finished_at',
            )
        }),
    )
    
    ordering = ['-created_at']
    
    date_hierarchy = 'created_at'
    
    list_per_page = 50
    
    def status_display(self, obj):
        """带颜色的状态显示"""
        colors = {
            TokenAcquisitionStatus.SUCCESS: "#28a745",
            TokenAcquisitionStatus.FAILED: "#dc3545",
            TokenAcquisitionStatus.TIMEOUT: "#ffc107",
            TokenAcquisitionStatus.NETWORK_ERROR: "#fd7e14",
            TokenAcquisitionStatus.CAPTCHA_ERROR: "#6f42c1",
            TokenAcquisitionStatus.CREDENTIAL_ERROR: "#e83e8c",
        }
        icons = {
            TokenAcquisitionStatus.SUCCESS: "✅",
            TokenAcquisitionStatus.FAILED: "❌",
            TokenAcquisitionStatus.TIMEOUT: "⏰",
            TokenAcquisitionStatus.NETWORK_ERROR: "🌐",
            TokenAcquisitionStatus.CAPTCHA_ERROR: "🔤",
            TokenAcquisitionStatus.CREDENTIAL_ERROR: "🔑",
        }
        
        color = colors.get(obj.status, "#666")
        icon = icons.get(obj.status, "")
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color,
            icon,
            obj.get_status_display()
        )
    status_display.short_description = "状态"
    
    def trigger_reason_display(self, obj):
        """格式化触发原因"""
        reason_map = {
            'token_expired': '🕐 Token过期',
            'no_token': '🚫 无Token',
            'manual_trigger': '👤 手动触发',
            'auto_refresh': '🔄 自动刷新',
            'system_startup': '🚀 系统启动',
        }
        
        display_text = reason_map.get(obj.trigger_reason, obj.trigger_reason)
        
        return format_html(
            '<span style="font-weight: bold;">{}</span>',
            display_text
        )
    trigger_reason_display.short_description = "触发原因"
    
    def performance_display(self, obj):
        """显示性能指标"""
        if not obj.total_duration:
            return format_html('<span style="color: #999;">-</span>')
        
        # 根据耗时显示不同颜色
        duration = float(obj.total_duration)
        if duration < 10:
            color = "#28a745"  # 绿色：快速
        elif duration < 30:
            color = "#ffc107"  # 黄色：正常
        else:
            color = "#dc3545"  # 红色：慢速
        
        duration_text = "{:.1f}s".format(duration)
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            duration_text
        )
    performance_display.short_description = "总耗时"
    
    def attempts_display(self, obj):
        """显示尝试次数统计"""
        parts = []
        
        if obj.attempt_count > 1:
            parts.append('重试: <span style="color: #ffc107; font-weight: bold;">{}</span>'.format(obj.attempt_count))
        
        if obj.captcha_attempts > 0:
            parts.append('验证码: <span style="color: #6f42c1; font-weight: bold;">{}</span>'.format(obj.captcha_attempts))
        
        if obj.network_retries > 0:
            parts.append('网络: <span style="color: #fd7e14; font-weight: bold;">{}</span>'.format(obj.network_retries))
        
        if parts:
            return format_html(' | '.join(parts))
        
        return format_html('<span style="color: #28a745;">一次成功</span>')
    attempts_display.short_description = "尝试统计"
    
    def duration_display(self, obj):
        """显示详细耗时信息"""
        if not obj.total_duration:
            return format_html('<span style="color: #999;">-</span>')
        
        total_text = "{:.1f}s".format(obj.total_duration)
        parts = ['总计: <span style="font-weight: bold;">{}</span>'.format(total_text)]
        
        if obj.login_duration:
            login_text = "{:.1f}s".format(obj.login_duration)
            parts.append('登录: <span style="color: #007bff;">{}</span>'.format(login_text))
        
        return format_html('<br>'.join(parts))
    duration_display.short_description = "耗时详情"
    
    def error_details_display(self, obj):
        """格式化显示错误详情"""
        if not obj.error_details:
            return format_html('<span style="color: #999;">-</span>')
        
        try:
            import json
            formatted = json.dumps(obj.error_details, ensure_ascii=False, indent=2)
            
            return format_html(
                '<details style="cursor: pointer;">'
                '<summary style="color: #007bff; font-weight: bold;">📋 查看详情</summary>'
                '<pre style="max-height: 400px; overflow: auto; background: #f5f5f5; '
                'padding: 10px; border-radius: 4px; font-size: 12px;">{}</pre>'
                '</details>',
                formatted
            )
        except:
            return format_html(
                '<pre style="max-height: 200px; overflow: auto; background: #f5f5f5; '
                'padding: 10px; border-radius: 4px; font-size: 12px;">{}</pre>',
                str(obj.error_details)[:500]
            )
    error_details_display.short_description = "错误详情"
    
    def performance_summary(self, obj):
        """性能汇总信息"""
        if not obj.total_duration:
            return format_html('<p style="color: #999;">无性能数据</p>')
        
        # 构建性能汇总表格
        total_duration_text = "{:.2f} 秒".format(obj.total_duration)
        html_parts = [
            '<table style="width: 100%; border-collapse: collapse;">',
            '<tr><td style="padding: 5px; font-weight: bold;">总耗时:</td>',
            '<td style="padding: 5px;">{}</td></tr>'.format(total_duration_text),
        ]
        
        if obj.login_duration:
            login_duration_text = "{:.2f} 秒".format(obj.login_duration)
            html_parts.extend([
                '<tr><td style="padding: 5px; font-weight: bold;">登录耗时:</td>',
                '<td style="padding: 5px;">{}</td></tr>'.format(login_duration_text),
            ])
        
        html_parts.extend([
            '<tr><td style="padding: 5px; font-weight: bold;">尝试次数:</td>',
            '<td style="padding: 5px;">{} 次</td></tr>'.format(obj.attempt_count),
            '<tr><td style="padding: 5px; font-weight: bold;">验证码尝试:</td>',
            '<td style="padding: 5px;">{} 次</td></tr>'.format(obj.captcha_attempts),
            '<tr><td style="padding: 5px; font-weight: bold;">网络重试:</td>',
            '<td style="padding: 5px;">{} 次</td></tr>'.format(obj.network_retries),
            '</table>',
        ])
        
        # 添加性能评级
        duration = obj.total_duration
        if duration < 10:
            rating = '<span style="color: #28a745; font-weight: bold;">🚀 优秀</span>'
        elif duration < 30:
            rating = '<span style="color: #ffc107; font-weight: bold;">⚡ 良好</span>'
        else:
            rating = '<span style="color: #dc3545; font-weight: bold;">🐌 需优化</span>'
        
        html_parts.append('<p style="margin-top: 10px;">性能评级: {}</p>'.format(rating))
        
        return format_html(''.join(html_parts))
    performance_summary.short_description = "性能汇总"
    
    def has_add_permission(self, request):
        """禁用添加功能（历史记录由系统自动创建）"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """禁用修改功能（历史记录不应被修改）"""
        return False
    
    # 定义批量操作
    actions = ['cleanup_old_records', 'export_to_csv', 'reanalyze_performance']
    
    def cleanup_old_records(self, request, queryset):
        """清理旧的历史记录"""
        try:
            service = _get_token_history_admin_service()
            count = service.cleanup_old_records(days=30)
            
            if count > 0:
                self.message_user(
                    request,
                    f"✅ 成功清理 {count} 条30天前的历史记录"
                )
            else:
                self.message_user(
                    request,
                    "ℹ️ 没有找到需要清理的历史记录"
                )
        except Exception as e:
            self.message_user(
                request,
                f"❌ 清理失败: {str(e)}",
                level=messages.ERROR
            )
    cleanup_old_records.short_description = "清理30天前的历史记录"
    
    def export_to_csv(self, request, queryset):
        """导出选中记录为CSV"""
        try:
            service = _get_token_history_admin_service()
            response = service.export_to_csv(queryset)
            
            self.message_user(
                request,
                f"✅ 成功导出 {queryset.count()} 条记录"
            )
            
            return response
        except Exception as e:
            self.message_user(
                request,
                f"❌ 导出失败: {str(e)}",
                level=messages.ERROR
            )
    export_to_csv.short_description = "导出为CSV文件"
    
    def reanalyze_performance(self, request, queryset):
        """重新分析性能数据"""
        try:
            service = _get_token_history_admin_service()
            result = service.reanalyze_performance(queryset)
            self._display_analysis_results(request, result)
            self._provide_performance_suggestions(request, result)
        except Exception as e:
            self.message_user(request, f"❌ 分析失败: {str(e)}", level=messages.ERROR)
    
    def _display_analysis_results(self, request, result):
        """显示分析结果"""
        result_parts = [
            f"📊 分析完成：共 {result['total_count']} 条记录",
            f"✅ 成功率：{result['success_rate']:.1f}% ({result['success_count']}/{result['total_count']})",
        ]
        
        if result['avg_duration'] > 0:
            result_parts.append(f"⏱️ 平均耗时：{result['avg_duration']:.1f}秒")
        
        if result['error_stats']:
            error_summary = "、".join([f"{k}({v})" for k, v in result['error_stats'].items()])
            result_parts.append(f"❌ 错误分布：{error_summary}")
        
        self.message_user(request, " | ".join(result_parts))
    
    def _provide_performance_suggestions(self, request, result):
        """提供性能建议"""
        if result['success_rate'] < 80:
            self.message_user(request, "💡 建议：成功率较低，请检查账号配置和网络环境", level=messages.WARNING)
        
        if result['avg_duration'] > 30:
            self.message_user(request, "💡 建议：平均耗时较长，请检查网络连接和服务器性能", level=messages.WARNING)
    reanalyze_performance.short_description = "重新分析性能数据"
    
    def get_urls(self):
        """添加自定义URL"""
        urls = super().get_urls()
        from django.urls import path
        
        custom_urls = [
            path(
                'dashboard/',
                self.admin_site.admin_view(self.dashboard_view),
                name='automation_tokenacquisitionhistory_dashboard',
            ),
        ]
        return custom_urls + urls
    
    def dashboard_view(self, request):
        """Token获取仪表板视图"""
        try:
            service = _get_token_history_admin_service()
            stats = service.get_dashboard_statistics()
            context = self._build_dashboard_context(stats)
            return self._render_dashboard(request, context)
        except Exception as e:
            return self._render_dashboard_error(request, str(e))
    
    def _build_dashboard_context(self, stats):
        """构建仪表板上下文"""
        import json
        return {
            'title': 'Token获取仪表板',
            'total_records': stats['total_records'],
            'success_records': stats['success_records'],
            'success_rate': stats['success_rate'],
            'time_stats': stats['time_stats'],
            'status_stats': stats['status_stats'],
            'site_stats': stats['site_stats'],
            'performance_stats': stats['performance_stats'],
            'trend_data': json.dumps(stats['trend_data']),
            'opts': self.model._meta,
        }
    
    def _render_dashboard(self, request, context):
        """渲染仪表板"""
        from django.shortcuts import render
        return render(request, 'admin/automation/tokenacquisitionhistory/dashboard.html', context)
    
    def _render_dashboard_error(self, request, error):
        """渲染仪表板错误页面"""
        from django.shortcuts import render
        context = {'title': 'Token获取仪表板', 'error': error, 'opts': self.model._meta}
        return render(request, 'admin/automation/tokenacquisitionhistory/dashboard.html', context)
    
    def changelist_view(self, request, extra_context=None):
        """添加统计信息到列表页面"""
        extra_context = extra_context or {}
        
        # 计算统计信息
        total_records = TokenAcquisitionHistory.objects.count()
        success_records = TokenAcquisitionHistory.objects.filter(
            status=TokenAcquisitionStatus.SUCCESS
        ).count()
        
        if total_records > 0:
            success_rate = (success_records / total_records) * 100
        else:
            success_rate = 0
        
        # 最近24小时的统计
        last_24h = timezone.now() - timezone.timedelta(hours=24)
        recent_records = TokenAcquisitionHistory.objects.filter(
            created_at__gte=last_24h
        )
        recent_count = recent_records.count()
        recent_success = recent_records.filter(
            status=TokenAcquisitionStatus.SUCCESS
        ).count()
        
        # 平均耗时
        avg_duration = TokenAcquisitionHistory.objects.filter(
            status=TokenAcquisitionStatus.SUCCESS,
            total_duration__isnull=False
        ).aggregate(avg_duration=Avg('total_duration'))['avg_duration'] or 0
        
        extra_context['statistics'] = {
            'total_records': total_records,
            'success_records': success_records,
            'success_rate': success_rate,
            'recent_count': recent_count,
            'recent_success': recent_success,
            'avg_duration': avg_duration,
        }
        
        return super().changelist_view(request, extra_context)