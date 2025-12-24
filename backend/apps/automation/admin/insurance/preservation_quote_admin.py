"""
财产保全询价 Admin
提供询价任务的创建、查看、执行功能
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q
from decimal import Decimal
import asyncio
from ...models import PreservationQuote, InsuranceQuote, QuoteStatus


def _get_preservation_quote_admin_service():
    """工厂函数：创建财产保全询价管理服务"""
    from ...services.admin import PreservationQuoteAdminService
    return PreservationQuoteAdminService()


class InsuranceQuoteInline(admin.TabularInline):
    """保险公司报价内联显示"""
    model = InsuranceQuote
    extra = 0
    can_delete = False
    
    fields = [
        'company_name',
        'prices_display',
        'rates_display',
        'max_apply_amount_display',
        'status_display',
        'error_message_display',
    ]
    
    readonly_fields = [
        'company_name',
        'prices_display',
        'rates_display',
        'max_apply_amount_display',
        'status_display',
        'error_message_display',
    ]
    
    def prices_display(self, obj):
        """显示三个价格"""
        if obj.status != "success":
            return format_html('<span style="color: #999;">-</span>')
        
        parts = []
        if obj.min_premium:
            parts.append(f'最低收费: <span style="color: #28a745; font-weight: bold;">¥{obj.min_premium:,.2f}</span>')
        if obj.min_amount:
            parts.append(f'最低报价: <span style="color: #17a2b8; font-weight: bold;">¥{obj.min_amount:,.2f}</span>')
        if obj.max_amount:
            parts.append(f'最高收费: <span style="color: #dc3545; font-weight: bold;">¥{obj.max_amount:,.2f}</span>')
        
        if parts:
            return format_html('<br>'.join(parts))
        return format_html('<span style="color: #999;">-</span>')
    prices_display.short_description = "收费标准"
    
    def rates_display(self, obj):
        """显示两个费率"""
        if obj.status != "success":
            return format_html('<span style="color: #999;">-</span>')
        
        parts = []
        if obj.min_rate:
            parts.append(f'最低: <span style="color: #28a745; font-weight: bold;">{obj.min_rate}</span>')
        if obj.max_rate:
            parts.append(f'最高: <span style="color: #dc3545; font-weight: bold;">{obj.max_rate}</span>')
        
        if parts:
            return format_html('<br>'.join(parts))
        return format_html('<span style="color: #999;">-</span>')
    rates_display.short_description = "费率"
    
    def max_apply_amount_display(self, obj):
        """显示最高保全金额"""
        if obj.status != "success" or not obj.max_apply_amount:
            return format_html('<span style="color: #999;">-</span>')
        
        # 转换为易读格式
        amount = float(obj.max_apply_amount)
        if amount >= 100000000:  # 1亿以上
            display = f'{amount / 100000000:.2f}亿'
        elif amount >= 10000:  # 1万以上
            display = f'{amount / 10000:.2f}万'
        else:
            display = f'{amount:,.2f}'
        
        return format_html(
            '<span style="color: #007bff; font-weight: bold;">¥{}</span>',
            display
        )
    max_apply_amount_display.short_description = "最高保全金额"
    
    def status_display(self, obj):
        """带颜色的状态显示"""
        if obj.status == "success":
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">✅ 成功</span>'
            )
        else:
            return format_html(
                '<span style="color: #dc3545; font-weight: bold;">❌ 失败</span>'
            )
    status_display.short_description = "状态"
    
    def error_message_display(self, obj):
        """格式化显示错误信息（请求和响应）"""
        if not obj.error_message:
            return format_html('<span style="color: #999;">-</span>')
        
        try:
            import json
            # 尝试解析为 JSON
            error_info = json.loads(obj.error_message)
            formatted = json.dumps(error_info, ensure_ascii=False, indent=2)
            
            # 使用可折叠的 details 标签
            return format_html(
                '<details style="cursor: pointer;">'
                '<summary style="color: #007bff; font-weight: bold;">📋 查看详情</summary>'
                '<pre style="max-height: 400px; overflow: auto; background: #f5f5f5; padding: 10px; border-radius: 4px; font-size: 12px;">{}</pre>'
                '</details>',
                formatted
            )
        except:
            # 如果不是 JSON，直接显示
            return format_html(
                '<pre style="max-height: 200px; overflow: auto; background: #f5f5f5; padding: 10px; border-radius: 4px; font-size: 12px;">{}</pre>',
                obj.error_message[:500]
            )
    error_message_display.short_description = "请求/响应详情"
    
    def has_add_permission(self, request, obj=None):
        """禁用添加功能"""
        return False


@admin.register(PreservationQuote)
class PreservationQuoteAdmin(admin.ModelAdmin):
    """
    财产保全询价管理 Admin
    
    功能：
    - 创建询价任务
    - 查看任务列表（状态、时间、统计）
    - 查看任务详情（展示所有报价）
    - 执行任务的 Admin Action
    - 重试失败任务
    """
    
    list_display = [
        'id',
        'preserve_amount_display',
        'status_display',
        'statistics_display',
        'success_rate_display',
        'duration_display',
        'created_at',
        'run_button',
    ]
    
    list_filter = [
        'status',
        'created_at',
        'finished_at',
    ]
    
    search_fields = [
        'id',
        'corp_id',
        'category_id',
    ]
    
    readonly_fields = [
        'id',
        'status',
        'total_companies',
        'success_count',
        'failed_count',
        'error_message',
        'created_at',
        'started_at',
        'finished_at',
        'duration_display',
        'success_rate_display',
        'quotes_summary',
    ]
    
    fieldsets = (
        ('基本信息', {
            'fields': (
                'id',
                'preserve_amount',
                'corp_id',
                'category_id',
            )
        }),
        ('任务状态', {
            'fields': (
                'status',
                'total_companies',
                'success_count',
                'failed_count',
                'success_rate_display',
                'error_message',
            )
        }),
        ('时间信息', {
            'fields': (
                'created_at',
                'started_at',
                'finished_at',
                'duration_display',
            )
        }),
        ('报价汇总', {
            'fields': ('quotes_summary',),
            'classes': ('wide',),
        }),
    )
    
    inlines = [InsuranceQuoteInline]
    
    ordering = ['-created_at']
    
    date_hierarchy = 'created_at'
    
    list_per_page = 20
    
    actions = ['execute_quotes', 'retry_failed_quotes']
    
    def preserve_amount_display(self, obj):
        """格式化显示保全金额"""
        amount_str = f'{obj.preserve_amount:,.2f}'
        return format_html(
            '<span style="font-weight: bold; font-size: 14px;">¥{}</span>',
            amount_str
        )
    preserve_amount_display.short_description = "保全金额"
    
    def status_display(self, obj):
        """带颜色的状态显示"""
        colors = {
            QuoteStatus.PENDING: "#ffa500",
            QuoteStatus.RUNNING: "#007bff",
            QuoteStatus.SUCCESS: "#28a745",
            QuoteStatus.PARTIAL_SUCCESS: "#ffc107",
            QuoteStatus.FAILED: "#dc3545",
        }
        icons = {
            QuoteStatus.PENDING: "⏳",
            QuoteStatus.RUNNING: "🔄",
            QuoteStatus.SUCCESS: "✅",
            QuoteStatus.PARTIAL_SUCCESS: "⚠️",
            QuoteStatus.FAILED: "❌",
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
    
    def statistics_display(self, obj):
        """显示统计信息"""
        if obj.total_companies == 0:
            return format_html('<span style="color: #999;">-</span>')
        
        return format_html(
            '<span style="color: #28a745; font-weight: bold;">{}</span> / '
            '<span style="color: #dc3545;">{}</span> / '
            '<span style="color: #666;">{}</span>',
            obj.success_count,
            obj.failed_count,
            obj.total_companies
        )
    statistics_display.short_description = "成功/失败/总数"
    
    def success_rate_display(self, obj):
        """显示成功率"""
        if obj.total_companies == 0:
            return format_html('<span style="color: #999;">-</span>')
        
        rate = obj.get_success_rate()
        rate_str = f'{rate:.1f}%'
        
        # 根据成功率显示不同颜色
        if rate >= 80:
            color = "#28a745"
        elif rate >= 50:
            color = "#ffc107"
        else:
            color = "#dc3545"
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            rate_str
        )
    success_rate_display.short_description = "成功率"
    
    def duration_display(self, obj):
        """显示执行时长"""
        if obj.started_at and obj.finished_at:
            delta = obj.finished_at - obj.started_at
            seconds = delta.total_seconds()
            
            if seconds < 60:
                time_str = f'{seconds:.1f}秒'
                return format_html(
                    '<span style="color: #28a745;">{}</span>',
                    time_str
                )
            else:
                minutes = seconds / 60
                time_str = f'{minutes:.1f}分钟'
                return format_html(
                    '<span style="color: #007bff;">{}</span>',
                    time_str
                )
        elif obj.started_at:
            # 正在执行中
            delta = timezone.now() - obj.started_at
            seconds = delta.total_seconds()
            time_str = f'执行中 ({seconds:.0f}秒)'
            return format_html(
                '<span style="color: #ffa500;">{}</span>',
                time_str
            )
        
        return format_html('<span style="color: #999;">-</span>')
    duration_display.short_description = "执行时长"
    
    def run_button(self, obj):
        """立即运行按钮"""
        if obj.status in [QuoteStatus.PENDING, QuoteStatus.FAILED]:
            return format_html(
                '<a class="button" href="/admin/automation/preservationquote/{}/run/" '
                'style="background-color: #28a745; color: white; padding: 5px 10px; '
                'border-radius: 4px; text-decoration: none; display: inline-block;">'
                '▶️ 立即运行</a>',
                obj.id
            )
        elif obj.status == QuoteStatus.RUNNING:
            return format_html(
                '<span style="color: #007bff; font-weight: bold;">🔄 运行中...</span>'
            )
        else:
            return format_html(
                '<span style="color: #999;">已完成</span>'
            )
    run_button.short_description = "操作"
    
    def quotes_summary(self, obj):
        """报价汇总表格"""
        if obj.total_companies == 0:
            return format_html('<p style="color: #999;">暂无报价数据</p>')
        
        # 获取所有报价，按最低报价（min_amount）排序
        quotes = obj.quotes.all().order_by('min_amount')
        
        if not quotes:
            return format_html('<p style="color: #999;">暂无报价数据</p>')
        
        # 构建 HTML 表格
        html_parts = [
            '<table style="width: 100%; border-collapse: collapse; margin-top: 10px;">',
            '<thead>',
            '<tr style="background-color: #f5f5f5;">',
            '<th style="padding: 8px; text-align: left; border: 1px solid #ddd;">排名</th>',
            '<th style="padding: 8px; text-align: left; border: 1px solid #ddd;">保险公司</th>',
            '<th style="padding: 8px; text-align: right; border: 1px solid #ddd;">报价金额</th>',
            '<th style="padding: 8px; text-align: center; border: 1px solid #ddd;">状态</th>',
            '</tr>',
            '</thead>',
            '<tbody>',
        ]
        
        rank = 1
        for quote in quotes:
            # 状态显示
            if quote.status == "success":
                status_html = '<span style="color: #28a745;">✅ 成功</span>'
            else:
                status_html = '<span style="color: #dc3545;">❌ 失败</span>'
            
            # 报价显示（使用 min_amount 最低报价）
            if quote.min_amount:
                # 最低价高亮显示
                if rank == 1:
                    premium_html = f'<span style="color: #28a745; font-weight: bold; font-size: 16px;">¥{quote.min_amount:,.2f}</span> 🏆'
                else:
                    premium_html = f'<span style="font-weight: bold;">¥{quote.min_amount:,.2f}</span>'
                
                rank_display = f'<span style="font-weight: bold;">#{rank}</span>'
                rank += 1
            else:
                premium_html = '<span style="color: #999;">-</span>'
                rank_display = '<span style="color: #999;">-</span>'
            
            html_parts.append(
                f'<tr>'
                f'<td style="padding: 8px; border: 1px solid #ddd;">{rank_display}</td>'
                f'<td style="padding: 8px; border: 1px solid #ddd;">{quote.company_name}</td>'
                f'<td style="padding: 8px; text-align: right; border: 1px solid #ddd;">{premium_html}</td>'
                f'<td style="padding: 8px; text-align: center; border: 1px solid #ddd;">{status_html}</td>'
                f'</tr>'
            )
        
        html_parts.append('</tbody></table>')
        
        # 添加统计信息（使用 min_amount 最低报价）
        successful_quotes = [q for q in quotes if q.min_amount is not None]
        if successful_quotes:
            min_premium = min(q.min_amount for q in successful_quotes)
            max_premium = max(q.min_amount for q in successful_quotes)
            avg_premium = sum(q.min_amount for q in successful_quotes) / len(successful_quotes)
            
            html_parts.append(
                '<div style="margin-top: 15px; padding: 10px; background-color: #f8f9fa; border-radius: 4px;">'
                '<strong>统计信息：</strong><br>'
                f'最低报价: <span style="color: #28a745; font-weight: bold;">¥{min_premium:,.2f}</span><br>'
                f'最高报价: <span style="color: #dc3545; font-weight: bold;">¥{max_premium:,.2f}</span><br>'
                f'平均报价: <span style="color: #007bff; font-weight: bold;">¥{avg_premium:,.2f}</span>'
                '</div>'
            )
        
        return format_html(''.join(html_parts))
    quotes_summary.short_description = "报价汇总"
    
    @admin.action(description="执行选中的询价任务")
    def execute_quotes(self, request, queryset):
        """批量执行询价任务"""
        try:
            service = _get_preservation_quote_admin_service()
            quote_ids = list(queryset.values_list('id', flat=True))
            result = asyncio.run(service.execute_quotes(quote_ids))
            self._display_execution_results(request, result)
        except Exception as e:
            self.message_user(request, f"❌ 批量执行失败: {str(e)}", level=messages.ERROR)
    
    def _display_execution_results(self, request, result):
        """显示执行结果"""
        if result['success_count'] > 0:
            self.message_user(request, f"✅ 成功执行 {result['success_count']} 个询价任务")
        
        if result['error_count'] > 0:
            self.message_user(request, f"❌ {result['error_count']} 个任务执行失败", level=messages.WARNING)
            for error in result['errors'][:5]:
                self.message_user(request, f"任务 #{error['quote_id']}: {error['error']}", level=messages.ERROR)
    
    @admin.action(description="重试失败的询价任务")
    def retry_failed_quotes(self, request, queryset):
        """重试失败的询价任务"""
        try:
            service = _get_preservation_quote_admin_service()
            quote_ids = list(queryset.values_list('id', flat=True))
            result = service.retry_failed_quotes(quote_ids)
            
            self.message_user(
                request,
                result['message']
            )
        except Exception as e:
            self.message_user(
                request,
                f"❌ 重试失败: {str(e)}",
                level=messages.ERROR
            )
    
    def has_delete_permission(self, request, obj=None):
        """允许删除"""
        return True
    
    def get_queryset(self, request):
        """优化查询性能"""
        qs = super().get_queryset(request)
        # 预加载关联的报价记录
        return qs.prefetch_related('quotes')
    
    def get_urls(self):
        """添加自定义URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:quote_id>/run/',
                self.admin_site.admin_view(self.run_quote_view),
                name='automation_preservationquote_run',
            ),
        ]
        return custom_urls + urls
    
    def run_quote_view(self, request, quote_id):
        """立即运行询价任务"""
        try:
            service = _get_preservation_quote_admin_service()
            result = service.run_single_quote(quote_id)
            self.message_user(request, result['message'])
        except Exception as e:
            self.message_user(request, f"提交任务失败: {str(e)}", level=messages.ERROR)
        
        return redirect('admin:automation_preservationquote_changelist')