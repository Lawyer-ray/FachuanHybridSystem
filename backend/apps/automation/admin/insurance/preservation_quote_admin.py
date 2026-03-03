"""
财产保全询价 Admin
提供询价任务的创建、查看、执行功能
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, ClassVar

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.automation.models import InsuranceQuote, PreservationQuote, QuoteStatus


def _get_preservation_quote_admin_service() -> Any:
    """工厂函数：创建财产保全询价管理服务"""
    from apps.automation.services.admin import PreservationQuoteAdminService

    return PreservationQuoteAdminService()


class InsuranceQuoteInline(admin.TabularInline[InsuranceQuote, InsuranceQuote]):
    """保险公司报价内联显示"""

    model = InsuranceQuote
    extra = 0
    can_delete = False

    fields: ClassVar[list[str]] = [
        "company_name",
        "prices_display",
        "rates_display",
        "max_apply_amount_display",
        "status_display",
        "error_message_display",
    ]

    readonly_fields: ClassVar[list[str]] = [
        "company_name",
        "prices_display",
        "rates_display",
        "max_apply_amount_display",
        "status_display",
        "error_message_display",
    ]

    @admin.display(description=_("收费标准"))
    def prices_display(self, obj: InsuranceQuote) -> SafeString:
        """显示三个价格"""
        if obj.status != "success":
            return format_html('<span style="color: #999;">{}</span>', "-")

        parts = []
        if obj.min_premium:
            parts.append(
                format_html(
                    '最低收费: <span style="color: #28a745; font-weight: bold;">¥{}</span>',
                    f"{obj.min_premium:,.2f}",
                )
            )
        if obj.min_amount:
            parts.append(
                format_html(
                    '最低报价: <span style="color: #17a2b8; font-weight: bold;">¥{}</span>',
                    f"{obj.min_amount:,.2f}",
                )
            )
        if obj.max_amount:
            parts.append(
                format_html(
                    '最高收费: <span style="color: #dc3545; font-weight: bold;">¥{}</span>',
                    f"{obj.max_amount:,.2f}",
                )
            )

        if parts:
            return format_html_join("<br>", "{}", ((p,) for p in parts))
        return format_html('<span style="color: #999;">{}</span>', "-")

    @admin.display(description=_("费率"))
    def rates_display(self, obj: InsuranceQuote) -> SafeString:
        """显示两个费率"""
        if obj.status != "success":
            return format_html('<span style="color: #999;">{}</span>', "-")

        parts = []
        if obj.min_rate:
            parts.append(format_html('最低: <span style="color: #28a745; font-weight: bold;">{}</span>', obj.min_rate))
        if obj.max_rate:
            parts.append(format_html('最高: <span style="color: #dc3545; font-weight: bold;">{}</span>', obj.max_rate))

        if parts:
            return format_html_join("<br>", "{}", ((p,) for p in parts))
        return format_html('<span style="color: #999;">{}</span>', "-")

    @admin.display(description=_("最高保全金额"))
    def max_apply_amount_display(self, obj: InsuranceQuote) -> SafeString:
        """显示最高保全金额"""
        if obj.status != "success" or not obj.max_apply_amount:
            return format_html('<span style="color: #999;">{}</span>', "-")

        amount = float(obj.max_apply_amount)
        if amount >= 100000000:
            display = f"{amount / 100000000:.2f}亿"
        elif amount >= 10000:
            display = f"{amount / 10000:.2f}万"
        else:
            display = f"{amount:,.2f}"

        return format_html('<span style="color: #007bff; font-weight: bold;">¥{}</span>', display)

    @admin.display(description=_("状态"))
    def status_display(self, obj: InsuranceQuote) -> SafeString:
        """带颜色的状态显示"""
        if obj.status == "success":
            return format_html('<span style="color: #28a745; font-weight: bold;">{}</span>', "✅ 成功")
        else:
            return format_html('<span style="color: #dc3545; font-weight: bold;">{}</span>', "❌ 失败")

    @admin.display(description=_("请求/响应详情"))
    def error_message_display(self, obj: InsuranceQuote) -> SafeString:
        """格式化显示错误信息"""
        if not obj.error_message:
            return format_html('<span style="color: #999;">{}</span>', "-")

        try:
            import json

            error_info = json.loads(obj.error_message)
            formatted = json.dumps(error_info, ensure_ascii=False, indent=2)

            return format_html(
                '<details style="cursor: pointer;">'
                '<summary style="color: #007bff; font-weight: bold;">📋 查看详情</summary>'
                '<pre style="max-height: 400px; overflow: auto; background: #f5f5f5;'
                ' padding: 10px; border-radius: 4px; font-size: 12px;">{}</pre>'
                "</details>",
                formatted,
            )
        except Exception:
            return format_html(
                '<pre style="max-height: 200px; overflow: auto; background: #f5f5f5;'
                ' padding: 10px; border-radius: 4px; font-size: 12px;">{}</pre>',
                obj.error_message[:500],
            )

    def has_add_permission(self, request: HttpRequest, obj: InsuranceQuote | None = None) -> bool:
        """禁用添加功能"""
        return False


@admin.register(PreservationQuote)
class PreservationQuoteAdmin(admin.ModelAdmin[PreservationQuote]):
    """财产保全询价管理 Admin"""

    list_display: ClassVar[list[str]] = [
        "id",
        "preserve_amount_display",
        "status_display",
        "statistics_display",
        "success_rate_display",
        "duration_display",
        "created_at",
        "run_button",
    ]

    list_filter: ClassVar[list[str]] = [
        "status",
        "created_at",
        "finished_at",
    ]

    search_fields: ClassVar[list[str]] = [
        "id",
        "corp_id",
        "category_id",
    ]

    readonly_fields: ClassVar[list[str]] = [
        "id",
        "status",
        "total_companies",
        "success_count",
        "failed_count",
        "error_message",
        "created_at",
        "started_at",
        "finished_at",
        "duration_display",
        "success_rate_display",
        "quotes_summary",
    ]

    fieldsets: ClassVar[tuple[Any, ...]] = (
        (
            _("基本信息"),
            {
                "fields": (
                    "id",
                    "preserve_amount",
                    "corp_id",
                    "category_id",
                )
            },
        ),
        (
            _("任务状态"),
            {
                "fields": (
                    "status",
                    "total_companies",
                    "success_count",
                    "failed_count",
                    "success_rate_display",
                    "error_message",
                )
            },
        ),
        (
            _("时间信息"),
            {
                "fields": (
                    "created_at",
                    "started_at",
                    "finished_at",
                    "duration_display",
                )
            },
        ),
        (
            _("报价汇总"),
            {
                "fields": ("quotes_summary",),
                "classes": ("wide",),
            },
        ),
    )

    inlines: ClassVar[list[Any]] = [InsuranceQuoteInline]
    ordering: ClassVar[list[str]] = ["-created_at"]
    date_hierarchy = "created_at"

    list_per_page = 20

    actions: ClassVar[list[str]] = ["execute_quotes", "retry_failed_quotes"]

    @admin.display(description=_("保全金额"))
    def preserve_amount_display(self, obj: PreservationQuote) -> SafeString:
        """格式化显示保全金额"""
        amount_str = f"{obj.preserve_amount:,.2f}"
        return format_html('<span style="font-weight: bold; font-size: 14px;">¥{}</span>', amount_str)

    @admin.display(description=_("状态"))
    def status_display(self, obj: PreservationQuote) -> SafeString:
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
            '<span style="color: {}; font-weight: bold;">{} {}</span>', color, icon, obj.get_status_display()
        )

    @admin.display(description=_("成功/失败/总数"))
    def statistics_display(self, obj: PreservationQuote) -> SafeString:
        """显示统计信息"""
        if obj.total_companies == 0:
            return format_html('<span style="color: #999;">{}</span>', "-")

        return format_html(
            '<span style="color: #28a745; font-weight: bold;">{}</span> / '
            '<span style="color: #dc3545;">{}</span> / '
            '<span style="color: #666;">{}</span>',
            obj.success_count,
            obj.failed_count,
            obj.total_companies,
        )

    @admin.display(description=_("成功率"))
    def success_rate_display(self, obj: PreservationQuote) -> SafeString:
        """显示成功率"""
        if obj.total_companies == 0:
            return format_html('<span style="color: #999;">{}</span>', "-")

        rate = obj.get_success_rate()
        rate_str = f"{rate:.1f}%"

        if rate >= 80:
            color = "#28a745"
        elif rate >= 50:
            color = "#ffc107"
        else:
            color = "#dc3545"

        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, rate_str)

    @admin.display(description=_("执行时长"))
    def duration_display(self, obj: PreservationQuote) -> SafeString:
        """显示执行时长"""
        if obj.started_at and obj.finished_at:
            delta = obj.finished_at - obj.started_at
            seconds = delta.total_seconds()

            if seconds < 60:
                time_str = f"{seconds:.1f}秒"
                return format_html('<span style="color: #28a745;">{}</span>', time_str)
            else:
                minutes = seconds / 60
                time_str = f"{minutes:.1f}分钟"
                return format_html('<span style="color: #007bff;">{}</span>', time_str)
        elif obj.started_at:
            delta = timezone.now() - obj.started_at
            seconds = delta.total_seconds()
            time_str = f"执行中 ({seconds:.0f}秒)"
            return format_html('<span style="color: #ffa500;">{}</span>', time_str)

        return format_html('<span style="color: #999;">{}</span>', "-")

    @admin.display(description=_("操作"))
    def run_button(self, obj: PreservationQuote) -> SafeString:
        """立即运行按钮"""
        if obj.status in [QuoteStatus.PENDING, QuoteStatus.FAILED]:
            return format_html(
                '<a class="button" href="/admin/automation/preservationquote/{}/run/" '
                'style="background-color: #28a745; color: white; padding: 5px 10px; '
                'border-radius: 4px; text-decoration: none; display: inline-block;">'
                "▶️ 立即运行</a>",
                obj.id,
            )
        elif obj.status == QuoteStatus.RUNNING:
            return format_html('<span style="color: #007bff; font-weight: bold;">{}</span>', "🔄 运行中...")
        else:
            return format_html('<span style="color: #999;">{}</span>', "已完成")

    @admin.display(description=_("报价汇总"))
    def quotes_summary(self, obj: PreservationQuote) -> SafeString:
        """报价汇总表格"""
        if obj.total_companies == 0:
            return format_html('<p style="color: #999;">{}</p>', _("暂无报价数据"))

        quotes = obj.quotes.all().order_by("min_amount")

        if not quotes:
            return format_html('<p style="color: #999;">{}</p>', _("暂无报价数据"))

        table_header = format_html(
            '<table style="width: 100%; border-collapse: collapse; margin-top: 10px;">'
            "<thead>"
            '<tr style="background-color: #f5f5f5;">'
            '<th style="padding: 8px; text-align: left; border: 1px solid #ddd;">{}</th>'
            '<th style="padding: 8px; text-align: left; border: 1px solid #ddd;">{}</th>'
            '<th style="padding: 8px; text-align: right; border: 1px solid #ddd;">{}</th>'
            '<th style="padding: 8px; text-align: center; border: 1px solid #ddd;">{}</th>'
            "</tr>"
            "</thead>"
            "<tbody>",
            _("排名"),
            _("保险公司"),
            _("报价金额"),
            _("状态"),
        )

        row_parts: list[SafeString] = []
        rank = 1
        for quote in quotes:
            row_parts.append(self._render_quote_row(quote, rank))
            if (quote.premium is not None) or (quote.min_amount is not None):
                rank += 1

        rows_html = format_html_join("", "{}", ((r,) for r in row_parts))
        table_close = format_html("{}", "</tbody></table>")

        def _get_amount(q: Any) -> Any:
            return q.premium if q.premium is not None else q.min_amount

        successful_quotes = [q for q in quotes if _get_amount(q) is not None]
        if successful_quotes:
            min_premium: Decimal = min(_get_amount(q) for q in successful_quotes)
            max_premium: Decimal = max(_get_amount(q) for q in successful_quotes)
            avg_premium: float = float(sum(_get_amount(q) for q in successful_quotes)) / len(successful_quotes)

            stats_html = format_html(
                '<div style="margin-top: 15px; padding: 10px; background-color: #f8f9fa; border-radius: 4px;">'
                "<strong>{}：</strong><br>"
                '{}: <span style="color: #28a745; font-weight: bold;">¥{}</span><br>'
                '{}: <span style="color: #dc3545; font-weight: bold;">¥{}</span><br>'
                '{}: <span style="color: #007bff; font-weight: bold;">¥{}</span>'
                "</div>",
                _("统计信息"),
                _("最低报价"),
                f"{min_premium:,.2f}",
                _("最高报价"),
                f"{max_premium:,.2f}",
                _("平均报价"),
                f"{avg_premium:,.2f}",
            )
            return format_html("{}{}{}{}", table_header, rows_html, table_close, stats_html)

        return format_html("{}{}{}", table_header, rows_html, table_close)

    def _render_quote_row(self, quote: Any, rank: int) -> SafeString:
        """渲染单行报价。"""
        if quote.status == "success":
            status_cell = format_html('<span style="color: #28a745;">✅ {}</span>', _("成功"))
        else:
            status_cell = format_html('<span style="color: #dc3545;">❌ {}</span>', _("失败"))

        amount_val = quote.premium if quote.premium is not None else quote.min_amount
        if amount_val is not None:
            amount_str = f"{amount_val:,.2f}"
            if rank == 1:
                premium_cell = format_html(
                    '<span style="color: #28a745; font-weight: bold; font-size: 16px;">¥{}</span> 🏆', amount_str
                )
            else:
                premium_cell = format_html('<span style="font-weight: bold;">¥{}</span>', amount_str)
            rank_cell = format_html('<span style="font-weight: bold;">#{}</span>', rank)
        else:
            premium_cell = format_html('<span style="color: #999;">{}</span>', "-")
            rank_cell = format_html('<span style="color: #999;">{}</span>', "-")

        return format_html(
            "<tr>"
            '<td style="padding: 8px; border: 1px solid #ddd;">{}</td>'
            '<td style="padding: 8px; border: 1px solid #ddd;">{}</td>'
            '<td style="padding: 8px; text-align: right; border: 1px solid #ddd;">{}</td>'
            '<td style="padding: 8px; text-align: center; border: 1px solid #ddd;">{}</td>'
            "</tr>",
            rank_cell,
            quote.company_name,
            premium_cell,
            status_cell,
        )

    @admin.action(description="执行选中的询价任务")
    def execute_quotes(self, request: HttpRequest, queryset: QuerySet[PreservationQuote]) -> None:
        """批量执行询价任务"""
        try:
            service = _get_preservation_quote_admin_service()
            quote_ids = list(queryset.values_list("id", flat=True))
            result = asyncio.run(service.execute_quotes(quote_ids))
            self._display_execution_results(request, result)
        except Exception as e:
            self.message_user(request, f"❌ 批量执行失败: {e!s}", level=messages.ERROR)

    def _display_execution_results(self, request: HttpRequest, result: dict[str, Any]) -> None:
        """显示执行结果"""
        if result["success_count"] > 0:
            self.message_user(request, f"✅ 成功执行 {result['success_count']} 个询价任务")

        if result["error_count"] > 0:
            self.message_user(request, f"❌ {result['error_count']} 个任务执行失败", level=messages.WARNING)
            for error in result["errors"][:5]:
                self.message_user(request, f"任务 #{error['quote_id']}: {error['error']}", level=messages.ERROR)

    @admin.action(description="重试失败的询价任务")
    def retry_failed_quotes(self, request: HttpRequest, queryset: QuerySet[PreservationQuote]) -> None:
        """重试失败的询价任务"""
        try:
            service = _get_preservation_quote_admin_service()
            quote_ids = list(queryset.values_list("id", flat=True))
            result = service.retry_failed_quotes(quote_ids)

            self.message_user(request, result["message"])
        except Exception as e:
            self.message_user(request, f"❌ 重试失败: {e!s}", level=messages.ERROR)

    def has_delete_permission(self, request: HttpRequest, obj: PreservationQuote | None = None) -> bool:
        """允许删除"""
        return True

    def get_queryset(self, request: HttpRequest) -> QuerySet[PreservationQuote]:
        """优化查询性能"""
        qs = super().get_queryset(request)
        return qs.prefetch_related("quotes")

    def get_urls(self) -> list[Any]:
        """添加自定义URL"""
        urls = super().get_urls()
        custom_urls: list[Any] = [
            path(
                "<int:quote_id>/run/",
                self.admin_site.admin_view(self.run_quote_view),
                name="automation_preservationquote_run",
            ),
        ]
        return custom_urls + urls

    def run_quote_view(self, request: HttpRequest, quote_id: int) -> HttpResponse:
        """立即运行询价任务"""
        try:
            service = _get_preservation_quote_admin_service()
            result = service.run_single_quote(quote_id)
            self.message_user(request, result["message"])
        except Exception as e:
            self.message_user(request, f"提交任务失败: {e!s}", level=messages.ERROR)

        return redirect("admin:automation_preservationquote_changelist")  # type: ignore[return-value]
