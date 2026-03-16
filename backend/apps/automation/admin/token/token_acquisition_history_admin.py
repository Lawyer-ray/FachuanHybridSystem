"""
Token获取历史记录 Admin
提供Token获取过程的详细历史记录查看功能
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, ClassVar

from django.contrib import admin, messages
from django.db.models import Avg, QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeData, SafeString
from django.utils.translation import gettext_lazy as _

from apps.automation.models import TokenAcquisitionHistory, TokenAcquisitionStatus

SITE_NAME_LABELS: dict[str, str] = {
    "court_zxfw": "人民法院在线服务网（一张网）",
    "court_baoquan": "人民法院保全系统",
}


def _get_token_history_admin_service() -> Any:
    """工厂函数：创建一张网/保全Token历史管理服务"""
    from apps.automation.services.admin import TokenAcquisitionHistoryAdminService

    return TokenAcquisitionHistoryAdminService()


@admin.register(TokenAcquisitionHistory)
class TokenAcquisitionHistoryAdmin(admin.ModelAdmin[TokenAcquisitionHistory]):
    """
    一张网/保全系统 Token获取历史记录管理 Admin

    功能：
    - 查看所有一张网/保全系统 Token 获取历史记录
    - 按网站、账号、状态搜索和过滤
    - 显示详细的执行统计信息
    - 查看错误详情和性能指标
    """

    list_display: ClassVar[list[str]] = [  # type: ignore[assignment,misc]
        "id",
        "site_name_display",
        "account",
        "status_display",
        "trigger_reason_display",
        "performance_display",
        "attempts_display",
        "duration_display",
        "created_at",
    ]

    list_filter: ClassVar[list[str]] = [  # type: ignore[assignment]
        "status",
        "site_name",
        "trigger_reason",
        "created_at",
        "finished_at",
    ]

    search_fields: ClassVar[list[str]] = [
        "site_name",
        "account",
        "trigger_reason",
        "error_message",
    ]

    readonly_fields: ClassVar[list[str]] = [
        "id",
        "site_name",
        "account",
        "credential_id",
        "status",
        "trigger_reason",
        "attempt_count",
        "total_duration",
        "login_duration",
        "captcha_attempts",
        "network_retries",
        "token_preview",
        "error_message",
        "error_details_display",
        "performance_summary",
        "created_at",
        "started_at",
        "finished_at",
    ]

    fieldsets = (
        (
            _("基本信息"),
            {
                "fields": (
                    "id",
                    "site_name",
                    "account",
                    "credential_id",
                    "trigger_reason",
                )
            },
        ),
        (
            _("执行结果"),
            {
                "fields": (
                    "status",
                    "token_preview",
                    "error_message",
                    "error_details_display",
                )
            },
        ),
        (
            _("性能指标"),
            {
                "fields": (
                    "performance_summary",
                    "attempt_count",
                    "total_duration",
                    "login_duration",
                    "captcha_attempts",
                    "network_retries",
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
                )
            },
        ),
    )

    ordering: ClassVar[list[str]] = ["-created_at"]
    date_hierarchy = "created_at"

    list_per_page = 50

    @admin.display(description=_("站点"))
    def site_name_display(self, obj: TokenAcquisitionHistory) -> str:
        """显示可读站点名称"""
        return SITE_NAME_LABELS.get(obj.site_name, obj.site_name)

    @admin.display(description=_("状态"))
    def status_display(self, obj: TokenAcquisitionHistory) -> SafeString:
        """带颜色的状态显示"""
        colors: dict[str, str] = {
            TokenAcquisitionStatus.SUCCESS: "#28a745",
            TokenAcquisitionStatus.FAILED: "#dc3545",
            TokenAcquisitionStatus.TIMEOUT: "#ffc107",
            TokenAcquisitionStatus.NETWORK_ERROR: "#fd7e14",
            TokenAcquisitionStatus.CAPTCHA_ERROR: "#6f42c1",
            TokenAcquisitionStatus.CREDENTIAL_ERROR: "#e83e8c",
        }
        icons: dict[str, str] = {
            TokenAcquisitionStatus.SUCCESS: "",
            TokenAcquisitionStatus.FAILED: "",
            TokenAcquisitionStatus.TIMEOUT: "",
            TokenAcquisitionStatus.NETWORK_ERROR: "",
            TokenAcquisitionStatus.CAPTCHA_ERROR: "",
            TokenAcquisitionStatus.CREDENTIAL_ERROR: "",
        }

        color = colors.get(obj.status, "#666")
        icon = icons.get(obj.status, "")

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}{}</span>',
            color,
            icon,
            obj.get_status_display(),
        )

    @admin.display(description=_("触发原因"))
    def trigger_reason_display(self, obj: TokenAcquisitionHistory) -> SafeString:
        """格式化触发原因"""
        reason_map: dict[str, str] = {
            "token_expired": "Token已过期",
            "no_token": "无可用Token",
            "manual_trigger": "手动触发",
            "auto_refresh": "自动刷新",
            "system_startup": "系统启动",
        }

        display_text = reason_map.get(obj.trigger_reason, obj.trigger_reason)

        return format_html('<span style="font-weight: bold;">{}</span>', display_text)

    @admin.display(description=_("总耗时"))
    def performance_display(self, obj: TokenAcquisitionHistory) -> SafeString:
        """显示性能指标"""
        if not obj.total_duration:
            return format_html('<span style="color: #999;">{}</span>', "-")
        duration = float(obj.total_duration)
        if duration < 10:
            color = "#28a745"  # 绿色：快速
        elif duration < 30:
            color = "#ffc107"  # 黄色：正常
        else:
            color = "#dc3545"  # 红色：慢速

        duration_text = f"{duration:.1f}s"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, duration_text)

    @admin.display(description=_("尝试统计"))
    def attempts_display(self, obj: TokenAcquisitionHistory) -> SafeString | SafeData:
        """显示尝试次数统计"""
        parts: list[SafeString] = []

        if obj.attempt_count > 1:
            parts.append(
                format_html(
                    '重试: <span style="color: #ffc107; font-weight: bold;">{}</span>',
                    obj.attempt_count,
                )
            )

        if obj.captcha_attempts > 0:
            parts.append(
                format_html(
                    '验证码: <span style="color: #6f42c1; font-weight: bold;">{}</span>',
                    obj.captcha_attempts,
                )
            )

        if obj.network_retries > 0:
            parts.append(
                format_html(
                    '网络: <span style="color: #fd7e14; font-weight: bold;">{}</span>',
                    obj.network_retries,
                )
            )

        if parts:
            return format_html_join(" | ", "{}", ((p,) for p in parts))

        return format_html('<span style="color: #28a745;">{}</span>', _("一次成功"))

    @admin.display(description=_("耗时详情"))
    def duration_display(self, obj: TokenAcquisitionHistory) -> SafeString | SafeData:
        """显示详细耗时信息"""
        if not obj.total_duration:
            return format_html('<span style="color: #999;">{}</span>', "-")

        total_text = f"{obj.total_duration:.1f}s"
        parts: list[SafeString] = [format_html('总计: <span style="font-weight: bold;">{}</span>', total_text)]

        if obj.login_duration:
            login_text = f"{obj.login_duration:.1f}s"
            parts.append(format_html('登录: <span style="color: #007bff;">{}</span>', login_text))

        return format_html_join("<br>", "{}", ((p,) for p in parts))

    @admin.display(description=_("错误详情"))
    def error_details_display(self, obj: TokenAcquisitionHistory) -> SafeString:
        """格式化显示错误详情"""
        if not obj.error_details:
            return format_html('<span style="color: #999;">{}</span>', "-")

        try:
            formatted = json.dumps(obj.error_details, ensure_ascii=False, indent=2)

            return format_html(
                '<details style="cursor: pointer;">'
                '<summary style="color: #007bff; font-weight: bold;">查看详情</summary>'
                '<pre style="max-height: 400px; overflow: auto; background: #f5f5f5; '
                'padding: 10px; border-radius: 4px; font-size: 12px;">{}</pre>'
                "</details>",
                formatted,
            )
        except Exception:
            return format_html(
                '<pre style="max-height: 200px; overflow: auto; background: #f5f5f5; '
                'padding: 10px; border-radius: 4px; font-size: 12px;">{}</pre>',
                str(obj.error_details)[:500],
            )

    @admin.display(description=_("性能汇总"))
    def performance_summary(self, obj: TokenAcquisitionHistory) -> SafeString:
        """性能汇总信息"""
        if not obj.total_duration:
            return format_html('<p style="color: #999;">{}</p>', _("无性能数据"))

        # 构建表格行列表
        rows: list[SafeString] = [
            format_html(
                '<tr><td style="padding: 5px; font-weight: bold;">{}</td><td style="padding: 5px;">{}</td></tr>',
                _("总耗时:"),
                f"{obj.total_duration:.2f} " + str(_("秒")),
            ),
        ]

        if obj.login_duration:
            rows.append(
                format_html(
                    '<tr><td style="padding: 5px; font-weight: bold;">{}</td><td style="padding: 5px;">{}</td></tr>',
                    _("登录耗时:"),
                    f"{obj.login_duration:.2f} " + str(_("秒")),
                )
            )

        rows.extend(
            [
                format_html(
                    '<tr><td style="padding: 5px; font-weight: bold;">{}</td><td style="padding: 5px;">{} {}</td></tr>',
                    _("尝试次数:"),
                    obj.attempt_count,
                    _("次"),
                ),
                format_html(
                    '<tr><td style="padding: 5px; font-weight: bold;">{}</td><td style="padding: 5px;">{} {}</td></tr>',
                    _("验证码尝试:"),
                    obj.captcha_attempts,
                    _("次"),
                ),
                format_html(
                    '<tr><td style="padding: 5px; font-weight: bold;">{}</td><td style="padding: 5px;">{} {}</td></tr>',
                    _("网络重试:"),
                    obj.network_retries,
                    _("次"),
                ),
            ]
        )

        table = format_html(
            '<table style="width: 100%; border-collapse: collapse;">{}</table>',
            format_html_join("", "{}", ((row,) for row in rows)),
        )

        # 性能评级
        duration = float(obj.total_duration)
        if duration < 10:
            rating: SafeString = format_html('<span style="color: #28a745; font-weight: bold;">{}</span>', _("优秀"))
        elif duration < 30:
            rating = format_html('<span style="color: #ffc107; font-weight: bold;">{}</span>', _("良好"))
        else:
            rating = format_html('<span style="color: #dc3545; font-weight: bold;">{}</span>', _("需优化"))

        return format_html(
            '{}<p style="margin-top: 10px;">{}: {}</p>',
            table,
            _("性能评级"),
            rating,
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """禁用添加功能（历史记录由系统自动创建）"""
        return False

    def has_change_permission(self, request: HttpRequest, obj: TokenAcquisitionHistory | None = None) -> bool:
        """禁用修改功能（历史记录不应被修改）"""
        return False

    # 定义批量操作
    actions: ClassVar[list[str]] = ["cleanup_old_records", "export_to_csv", "reanalyze_performance"]  # type: ignore[misc]

    @admin.action(description=_("清理30天前的一张网/保全Token历史记录"))
    def cleanup_old_records(
        self,
        request: HttpRequest,
        queryset: QuerySet[TokenAcquisitionHistory, TokenAcquisitionHistory],
    ) -> None:
        """清理旧的历史记录"""
        try:
            service = _get_token_history_admin_service()
            count = service.cleanup_old_records(days=30)

            if count > 0:
                self.message_user(
                    request,
                    _("成功清理 %(count)d 条30天前的历史记录") % {"count": count},
                )
            else:
                self.message_user(request, _("没有找到需要清理的历史记录"))
        except Exception as e:
            self.message_user(request, _("清理失败: %(error)s") % {"error": str(e)}, level=messages.ERROR)

    @admin.action(description=_("导出为CSV文件"))
    def export_to_csv(
        self,
        request: HttpRequest,
        queryset: QuerySet[TokenAcquisitionHistory, TokenAcquisitionHistory],
    ) -> HttpResponse | None:
        """导出选中记录为CSV"""
        try:
            service = _get_token_history_admin_service()
            response: HttpResponse = service.export_to_csv(queryset)

            self.message_user(
                request,
                _("成功导出 %(count)d 条记录") % {"count": queryset.count()},
            )

            return response
        except Exception as e:
            self.message_user(request, _("导出失败: %(error)s") % {"error": str(e)}, level=messages.ERROR)
            return None

    @admin.action(description=_("重新分析性能数据"))
    def reanalyze_performance(
        self,
        request: HttpRequest,
        queryset: QuerySet[TokenAcquisitionHistory, TokenAcquisitionHistory],
    ) -> None:
        """重新分析性能数据"""
        try:
            service = _get_token_history_admin_service()
            result: dict[str, Any] = service.reanalyze_performance(queryset)
            self._display_analysis_results(request, result)
            self._provide_performance_suggestions(request, result)
        except Exception as e:
            self.message_user(request, f"分析失败: {e!s}", level=messages.ERROR)

    def _display_analysis_results(self, request: HttpRequest, result: dict[str, Any]) -> None:
        """显示分析结果"""
        result_parts = [
            f"分析完成：共 {result['total_count']} 条记录",
            f"成功率：{result['success_rate']:.1f}% ({result['success_count']}/{result['total_count']})",
        ]

        if result["avg_duration"] > 0:
            result_parts.append(f"平均耗时：{result['avg_duration']:.1f}秒")

        if result["error_stats"]:
            error_summary = "、".join([f"{k}({v})" for k, v in result["error_stats"].items()])
            result_parts.append(f"错误分布：{error_summary}")

        self.message_user(request, " | ".join(result_parts))

    def _provide_performance_suggestions(self, request: HttpRequest, result: dict[str, Any]) -> None:
        """提供性能建议"""
        if result["success_rate"] < 80:
            self.message_user(
                request,
                "建议：成功率较低，请检查账号配置和网络环境",
                level=messages.WARNING,
            )

        if result["avg_duration"] > 30:
            self.message_user(
                request,
                "建议：平均耗时较长，请检查网络连接和服务器性能",
                level=messages.WARNING,
            )

    def get_urls(self) -> list[Any]:
        """添加自定义URL"""
        urls = super().get_urls()
        from django.urls import path

        custom_urls = [
            path(
                "dashboard/",
                self.admin_site.admin_view(self.dashboard_view),
                name="automation_tokenacquisitionhistory_dashboard",
            ),
        ]
        return custom_urls + urls

    def dashboard_view(self, request: HttpRequest) -> HttpResponse:
        """一张网/保全Token获取仪表板视图"""
        try:
            service = _get_token_history_admin_service()
            stats: dict[str, Any] = service.get_dashboard_statistics()
            context = self._build_dashboard_context(stats)
            return self._render_dashboard(request, context)
        except Exception as e:
            return self._render_dashboard_error(request, str(e))

    def _build_dashboard_context(self, stats: dict[str, Any]) -> dict[str, Any]:
        """构建仪表板上下文"""
        return {
            "title": "一张网/保全Token获取仪表板",
            "total_records": stats["total_records"],
            "success_records": stats["success_records"],
            "success_rate": stats["success_rate"],
            "time_stats": stats["time_stats"],
            "status_stats": stats["status_stats"],
            "site_stats": stats["site_stats"],
            "performance_stats": stats["performance_stats"],
            "trend_data": json.dumps(stats["trend_data"]),
            "opts": self.model._meta,
        }

    def _render_dashboard(self, request: HttpRequest, context: dict[str, Any]) -> HttpResponse:
        """渲染仪表板"""
        from django.shortcuts import render

        return render(
            request,
            "admin/automation/tokenacquisitionhistory/dashboard.html",
            context,
        )

    def _render_dashboard_error(self, request: HttpRequest, error: str) -> HttpResponse:
        """渲染仪表板错误页面"""
        from django.shortcuts import render

        context: dict[str, Any] = {
            "title": "一张网/保全Token获取仪表板",
            "error": error,
            "opts": self.model._meta,
        }
        return render(
            request,
            "admin/automation/tokenacquisitionhistory/dashboard.html",
            context,
        )

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """添加统计信息到列表页面"""
        extra_context = extra_context or {}

        # 计算统计信息
        total_records = TokenAcquisitionHistory.objects.count()
        success_records = TokenAcquisitionHistory.objects.filter(status=TokenAcquisitionStatus.SUCCESS).count()

        if total_records > 0:
            success_rate = (success_records / total_records) * 100
        else:
            success_rate = 0.0

        # 最近24小时的统计
        last_24h = timezone.now() - timedelta(hours=24)
        recent_records = TokenAcquisitionHistory.objects.filter(created_at__gte=last_24h)
        recent_count = recent_records.count()
        recent_success = recent_records.filter(status=TokenAcquisitionStatus.SUCCESS).count()

        # 平均耗时
        avg_duration: float = (
            TokenAcquisitionHistory.objects.filter(
                status=TokenAcquisitionStatus.SUCCESS, total_duration__isnull=False
            ).aggregate(avg_duration=Avg("total_duration"))["avg_duration"]
            or 0.0
        )

        extra_context["statistics"] = {
            "total_records": total_records,
            "success_records": success_records,
            "success_rate": success_rate,
            "recent_count": recent_count,
            "recent_success": recent_success,
            "avg_duration": avg_duration,
        }

        return super().changelist_view(request, extra_context)
