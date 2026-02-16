"""
法院短信 Admin 基础配置

包含列表显示、字段配置、筛选器等基础 Admin 配置.
"""

import logging
from typing import Any, cast

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.automation.models import CourtSMS, CourtSMSStatus, CourtSMSType

logger = logging.getLogger("apps.automation")


def _get_case_service() -> None:
    """获取案件服务实例(工厂函数)"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_case_service()


class CourtSMSAdminBase(admin.ModelAdmin):
    """法院短信管理基础配置"""

    # 列表显示字段
    list_display: list[Any] = [
        "id",
        "status_display",
        "sms_type_display",
        "case_display",
        "content_preview",
        "received_at",
        "has_download_links",
        "case_numbers_display",
        "party_names_display",
        "feishu_status",
        "retry_count",
    ]

    # 列表筛选器
    list_filter: list[Any] = [
        "status",
        "sms_type",
        "received_at",
        ("case", admin.RelatedFieldListFilter),
        ("scraper_task", admin.RelatedFieldListFilter),
    ]

    # 搜索字段
    search_fields: list[Any] = [
        "content",
        "case__name",
    ]

    # 排序
    ordering: list[Any] = []

    # 分页
    list_per_page: int = 20

    # 只读字段
    readonly_fields: list[Any] = [
        "id",
        "created_at",
        "updated_at",
        "download_links_display",
        "case_numbers_display",
        "party_names_display",
        "scraper_task_link",
        "case_log_link",
        "documents_display",
        "feishu_details",
        "retry_button",
    ]

    # 字段分组
    fieldsets: tuple[Any, ...] = (
        (
            "基本信息",
            {
                "fields": (
                    "id",
                    "content",
                    "received_at",
                    "status",
                    "sms_type",
                )
            },
        ),
        (
            "解析结果",
            {
                "fields": (
                    "download_links_display",
                    "case_numbers_display",
                    "party_names_display",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "关联信息",
            {
                "fields": (
                    "case",
                    "scraper_task_link",
                    "case_log_link",
                    "documents_display",
                )
            },
        ),
        (
            "处理状态",
            {
                "fields": (
                    "error_message",
                    "retry_count",
                    "retry_button",
                )
            },
        ),
        (
            "飞书通知",
            {
                "fields": ("feishu_details",),
                "classes": ("collapse",),
            },
        ),
        (
            "时间戳",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def status_display(self, obj) -> None:
        """状态显示(带颜色)"""
        status_colors = {
            CourtSMSStatus.PENDING: "orange",
            CourtSMSStatus.PARSING: "blue",
            CourtSMSStatus.DOWNLOADING: "blue",
            CourtSMSStatus.DOWNLOAD_FAILED: "red",
            CourtSMSStatus.MATCHING: "blue",
            CourtSMSStatus.PENDING_MANUAL: "orange",
            CourtSMSStatus.RENAMING: "blue",
            CourtSMSStatus.NOTIFYING: "blue",
            CourtSMSStatus.COMPLETED: "green",
            CourtSMSStatus.FAILED: "red",
        }
        color = status_colors.get(obj.status, "gray")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_display.short_description = "处理状态"

    def sms_type_display(self, obj) -> None:
        """短信类型显示"""
        if not obj.sms_type:
            return "-"

        type_icons = {
            CourtSMSType.DOCUMENT_DELIVERY: "📄",
            CourtSMSType.INFO_NOTIFICATION: "📢",
            CourtSMSType.FILING_NOTIFICATION: "📋",
        }
        icon = type_icons.get(obj.sms_type, "❓")
        return f"{icon} {obj.get_sms_type_display()}"

    sms_type_display.short_description = "短信类型"

    def case_display(self, obj) -> None:
        """案件显示"""
        if obj.case:
            url = reverse("admin:cases_case_change", args=[obj.cast(int, case.id)])
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url,
                obj.case.name[:50] + ("..." if len(obj.case.name) > 50 else ""),
            )
        elif obj.status == CourtSMSStatus.PENDING_MANUAL:
            assign_url = reverse("admin:automation_courtsms_assign_case", args=[cast(int, obj.id)])
            return format_html('<a href="{}" style="color: orange; font-weight: bold;">🔗 手动指定案件</a>', assign_url)
        return "-"

    case_display.short_description = "关联案件"

    def content_preview(self, obj) -> None:
        """短信内容预览"""
        preview = obj.content[:100]
        if len(obj.content) > 100:
            preview += "..."
        return preview

    content_preview.short_description = "短信内容"

    def has_download_links(self, obj) -> None:
        """是否有下载链接"""
        if obj.download_links:
            return format_html('<span style="color: green;">✓ {} 个链接</span>', len(obj.download_links))
        return format_html('<span style="color: gray;">✗ 无链接</span>')

    has_download_links.short_description = "下载链接"

    def case_numbers_display(self, obj) -> None:
        """案号显示"""
        if obj.case_numbers:
            return mark_safe("<br>".join(obj.case_numbers))
        return "-"

    case_numbers_display.short_description = "提取的案号"

    def party_names_display(self, obj) -> None:
        """当事人显示"""
        if obj.party_names:
            return mark_safe("<br>".join(obj.party_names))
        return "-"

    party_names_display.short_description = "提取的当事人"

    def download_links_display(self, obj) -> None:
        """下载链接显示"""
        if obj.download_links:
            links_html: list[Any] = []
            for i, link in enumerate(obj.download_links, 1):
                links_html.append(f'<p><strong>链接 {i}:</strong><br><a href="{link}" target="_blank">{link}</a></p>')
            return mark_safe("".join(links_html))
        return "-"

    download_links_display.short_description = "下载链接"

    def scraper_task_link(self, obj) -> None:
        """爬虫任务链接"""
        if obj.scraper_task:
            url = reverse("admin:automation_scrapertask_change", args=[obj.cast(int, scraper_task.id)])
            return format_html(
                '<a href="{}" target="_blank">任务 #{} - {}</a>',
                url,
                obj.cast(int, scraper_task.id),
                obj.scraper_task.get_status_display(),
            )
        return "-"

    scraper_task_link.short_description = "下载任务"

    def case_log_link(self, obj) -> None:
        """案件日志链接"""
        if obj.case_log:
            url = reverse("admin:cases_caselog_change", args=[obj.cast(int, case_log.id)])
            return format_html('<a href="{}" target="_blank">日志 #{}</a>', url, obj.cast(int, case_log.id))
        return "-"

    case_log_link.short_description = "案件日志"

    def documents_display(self, obj) -> None:
        """关联文书显示"""
        if obj.scraper_task and hasattr(obj.scraper_task, "documents"):
            documents = obj.scraper_task.documents.all()
            if documents:
                docs_html: list[Any] = []
                for doc in documents:
                    status_color = {
                        "success": "green",
                        "failed": "red",
                        "pending": "orange",
                        "downloading": "blue",
                    }.get(doc.download_status, "gray")

                    doc_url = reverse("admin:automation_courtdocument_change", args=[cast(int, doc.id)])
                    docs_html.append(
                        f'<p><a href="{doc_url}" target="_blank">{doc.c_wsmc}</a> '
                        f'<span style="color: {status_color};">({doc.get_download_status_display()})</span></p>'
                    )
                return mark_safe("".join(docs_html))
        return "-"

    documents_display.short_description = "关联文书"

    def feishu_status(self, obj) -> None:
        """飞书发送状态"""
        if obj.feishu_sent_at:
            if obj.feishu_error and obj.feishu_error not in ["发送失败", ""]:
                return format_html(
                    '<span style="color: green;">✓ 通知成功</span><br>'
                    "<small>{}</small><br>"
                    '<small style="color: #666;">{}</small>',
                    obj.feishu_sent_at.strftime("%m-%d %H:%M"),
                    obj.feishu_error[:50] + ("..." if len(obj.feishu_error) > 50 else ""),
                )
            else:
                return format_html(
                    '<span style="color: green;">✓ 通知成功</span><br><small>{}</small>',
                    obj.feishu_sent_at.strftime("%m-%d %H:%M"),
                )
        elif obj.feishu_error:
            error_preview = obj.feishu_error[:30] + ("..." if len(obj.feishu_error) > 30 else "")
            return format_html(
                '<span style="color: red;">✗ 通知失败</span><br><small style="color: #d63384;">{}</small>',
                error_preview,
            )
        return format_html('<span style="color: gray;">- 未发送</span>')

    feishu_status.short_description = "通知状态"

    def feishu_details(self, obj) -> None:
        """飞书详情"""
        if obj.feishu_sent_at:
            return f"发送时间: {obj.feishu_sent_at}"
        elif obj.feishu_error:
            return f"发送失败: {obj.feishu_error}"
        return "未发送"

    feishu_details.short_description = "飞书通知详情"

    def retry_button(self, obj) -> None:
        """重新处理按钮"""
        if cast(int, obj.id):
            retry_url = reverse("admin:automation_courtsms_retry", args=[cast(int, obj.id)])
            return format_html(
                '<a href="{}" class="button" onclick="return confirm(\'确认要重新处理这条短信吗?这将重置状态并重新执行完整流程.\');">'
                "🔄 重新处理</a>",
                retry_url,
            )
        return "-"

    retry_button.short_description = "操作"

    def get_search_results(self, request, queryset, search_term) -> None:
        """自定义搜索,支持 JSON 字段搜索"""
        queryset, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        return queryset, may_have_duplicates

    def get_queryset(self, request) -> None:
        """优化查询性能"""
        return super().get_queryset(request).select_related("case", "scraper_task", "case_log")

    def get_fields(self, request, obj=None) -> None:
        """根据是否为新增页面返回不同的字段"""
        if obj is None:
            return ["content", "received_at"]
        else:
            return [field.name for field in self.model._meta.fields if field.name != "id"]

    def get_readonly_fields(self, request, obj=None) -> None:
        """根据是否为新增页面返回不同的只读字段"""
        if obj is None:
            return ["received_at"]
        else:
            return self.readonly_fields

    def get_fieldsets(self, request, obj=None) -> None:
        """根据是否为新增页面返回不同的字段分组"""
        if obj is None:
            return (
                (
                    "短信信息",
                    {
                        "fields": ("content", "received_at"),
                        "description": "请输入完整的法院短信内容.收到时间将自动设置为当前时间.",
                    },
                ),
            )
        else:
            return self.fieldsets

    def get_form(self, request, obj=None, **kwargs) -> None:
        """自定义表单"""
        form = super().get_form(request, obj, **kwargs)

        if obj is None:
            from django.utils import timezone

            received_at_field = form.base_fields.get("received_at")
            if received_at_field:
                received_at_field.initial = timezone.now()
                received_at_field.help_text = "自动设置为当前时间,不可修改"

            content_field = form.base_fields.get("content")
            if content_field:
                content_field.required = True
                content_field.help_text = "请粘贴完整的法院短信内容"
                if hasattr(content_field, "widget") and hasattr(content_field.widget, "attrs"):
                    content_field.widget.attrs.update({"rows": 8, "placeholder": "请粘贴完整的法院短信内容..."})

        return form
