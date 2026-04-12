"""
法院短信 Admin 基础配置

包含列表显示、字段配置、筛选器等基础 Admin 配置.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, cast

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.automation.models import CourtSMS, CourtSMSStatus, CourtSMSType
from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService

logger = logging.getLogger("apps.automation")


def _get_case_service() -> Any:
    """获取案件服务实例(工厂函数)"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_case_service()


class CourtSMSAdminBase(admin.ModelAdmin[CourtSMS]):
    """法院短信管理基础配置"""

    # 列表显示字段
    list_display = [
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
    list_filter = [
        "status",
        "sms_type",
        "received_at",
        ("case", admin.RelatedFieldListFilter),
        ("scraper_task", admin.RelatedFieldListFilter),
    ]

    # 搜索字段
    search_fields = [
        "content",
        "case__name",
    ]

    # 排序
    ordering: ClassVar[tuple[str, ...]] = ()

    # 分页
    list_per_page = 20

    # 只读字段
    readonly_fields: ClassVar[list[str]] = [
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
    fieldsets = (
        (
            _("基本信息"),
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
            _("解析结果"),
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
            _("关联信息"),
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
            _("处理状态"),
            {
                "fields": (
                    "error_message",
                    "retry_count",
                    "retry_button",
                )
            },
        ),
        (
            _("飞书通知"),
            {
                "fields": ("feishu_details",),
                "classes": ("collapse",),
            },
        ),
        (
            _("时间戳"),
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description=_("处理状态"))
    def status_display(self, obj: CourtSMS) -> SafeString:
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

    @admin.display(description=_("短信类型"))
    def sms_type_display(self, obj: CourtSMS) -> str:
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

    @admin.display(description=_("关联案件"))
    def case_display(self, obj: CourtSMS) -> SafeString | str:
        """案件显示"""
        if obj.case:
            url = reverse("admin:cases_case_change", args=[cast(int, obj.case.id)])
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url,
                obj.case.name[:50] + ("..." if len(obj.case.name) > 50 else ""),
            )
        elif obj.status == CourtSMSStatus.PENDING_MANUAL:
            change_url = reverse("admin:automation_courtsms_change", args=[cast(int, obj.id)])
            return format_html(
                '<a href="{}" style="color: orange; font-weight: bold;">🔗 去详情页绑定案件</a>', change_url
            )
        return "-"

    @admin.display(description=_("短信内容"))
    def content_preview(self, obj: CourtSMS) -> str:
        """短信内容预览"""
        preview = obj.content[:100]
        if len(obj.content) > 100:
            preview += "..."
        return str(preview)

    @admin.display(description=_("下载链接"))
    def has_download_links(self, obj: CourtSMS) -> SafeString:
        """是否有下载链接"""
        if obj.download_links:
            return format_html('<span style="color: green;">✓ {} 个链接</span>', len(obj.download_links))
        return format_html('<span style="color: gray;">{}</span>', "✗ 无链接")

    @admin.display(description=_("提取的案号"))
    def case_numbers_display(self, obj: CourtSMS) -> SafeString | str:
        """案号显示"""
        if obj.case_numbers:
            return format_html_join("<br>", "{0}", ((n,) for n in obj.case_numbers))
        return "-"

    @admin.display(description=_("提取的当事人"))
    def party_names_display(self, obj: CourtSMS) -> SafeString | str:
        """当事人显示"""
        if obj.party_names:
            return format_html_join("<br>", "{0}", ((n,) for n in obj.party_names))
        return "-"

    @admin.display(description=_("下载链接"))
    def download_links_display(self, obj: CourtSMS) -> SafeString | str:
        """下载链接显示"""
        if obj.download_links:
            parts = [
                format_html('<p><strong>链接 {}:</strong><br><a href="{}" target="_blank">{}</a></p>', i, link, link)
                for i, link in enumerate(obj.download_links, 1)
            ]
            return format_html_join("", "{}", ((p,) for p in parts))
        return "-"

    @admin.display(description=_("下载任务"))
    def scraper_task_link(self, obj: CourtSMS) -> SafeString | str:
        """爬虫任务链接"""
        if obj.scraper_task:
            url = reverse("admin:automation_scrapertask_change", args=[cast(int, obj.scraper_task.id)])
            return format_html(
                '<a href="{}" target="_blank">任务 #{} - {}</a>',
                url,
                cast(int, obj.scraper_task.id),
                obj.scraper_task.get_status_display(),
            )
        return "-"

    @admin.display(description=_("案件日志"))
    def case_log_link(self, obj: CourtSMS) -> SafeString | str:
        """案件日志链接"""
        if obj.case_log:
            url = reverse("admin:cases_caselog_change", args=[cast(int, obj.case_log.id)])
            return format_html('<a href="{}" target="_blank">日志 #{}</a>', url, cast(int, obj.case_log.id))
        return "-"

    @admin.display(description=_("关联文书"))
    def documents_display(self, obj: CourtSMS) -> SafeString | str:
        """关联文书显示"""
        references = CourtSMSDocumentReferenceService().collect(obj)
        if not references:
            return "-"

        source_labels = {
            "court_document": _("文书记录"),
            "sms_reference": _("短信引用"),
            "task_result": _("任务结果"),
            "case_log_attachment": _("案件日志附件"),
        }

        parts = []
        for index, ref in enumerate(references):
            source_label = source_labels.get(ref.source, ref.source)
            status_display = ref.download_status_display or _("已下载")

            if ref.court_document_id:
                doc_url = reverse("admin:automation_courtdocument_change", args=[ref.court_document_id])
                parts.append(
                    format_html(
                        '<p><a href="{}" target="_blank">{}</a> <span style="color: #666;">[{}/{}]</span></p>',
                        doc_url,
                        ref.display_name,
                        source_label,
                        status_display,
                    )
                )
            else:
                open_url = reverse(
                    "admin:automation_courtsms_open_document",
                    args=[cast(int, obj.id), index],
                )
                parts.append(
                    format_html(
                        '<p><a href="{}" target="_blank">{}</a> <span style="color: #666;">[{}/{}]</span></p>',
                        open_url,
                        ref.display_name,
                        source_label,
                        status_display,
                    )
                )

        return format_html_join("", "{}", ((p,) for p in parts))

    @admin.display(description=_("通知状态"))
    def feishu_status(self, obj: CourtSMS) -> SafeString:
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
        return format_html('<span style="color: gray;">{}</span>', "- 未发送")

    @admin.display(description=_("飞书通知详情"))
    def feishu_details(self, obj: CourtSMS) -> str:
        """飞书详情"""
        if obj.feishu_sent_at:
            return f"发送时间: {obj.feishu_sent_at}"
        elif obj.feishu_error:
            return f"发送失败: {obj.feishu_error}"
        return "未发送"

    @admin.display(description=_("操作"))
    def retry_button(self, obj: CourtSMS) -> SafeString | str:
        """重新处理按钮"""
        if cast(int, obj.id):
            retry_url = reverse("admin:automation_courtsms_retry", args=[cast(int, obj.id)])
            return format_html(
                '<a href="{}" class="button" onclick="return confirm('
                "'确认要重新处理这条短信吗?这将重置状态并重新执行完整流程.');"
                '">'
                "🔄 重新处理</a>",
                retry_url,
            )
        return "-"

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[CourtSMS], search_term: str
    ) -> tuple[QuerySet[CourtSMS], bool]:
        """自定义搜索,支持 JSON 字段搜索"""
        queryset, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        return queryset, may_have_duplicates

    def get_queryset(self, request: HttpRequest) -> QuerySet[CourtSMS]:
        """优化查询性能"""
        return (
            super()
            .get_queryset(request)
            .select_related("case", "scraper_task", "case_log")
            .prefetch_related("scraper_task__documents", "case_log__attachments")
        )

    def get_fields(self, request: HttpRequest, obj: CourtSMS | None = None) -> Any:
        """根据是否为新增页面返回不同的字段"""
        if obj is None:
            return ["content", "received_at"]
        else:
            return [field.name for field in self.model._meta.fields if field.name != "id"]

    def get_readonly_fields(self, request: HttpRequest, obj: CourtSMS | None = None) -> list[str] | tuple[str, ...]:
        """根据是否为新增页面返回不同的只读字段"""
        if obj is None:
            return ["received_at"]
        else:
            return self.readonly_fields

    def get_fieldsets(self, request: HttpRequest, obj: CourtSMS | None = None) -> Any:
        """根据是否为新增页面返回不同的字段分组"""
        if obj is None:
            return [
                (
                    str(_("短信信息")),
                    {
                        "fields": ("content", "received_at"),
                        "description": (
                            "请输入完整的法院短信内容。收到时间将自动设置为当前时间。"
                            "<br><br><b>支持自动下载的平台：</b>"
                            "<br>• 法院执行网（zxfw.court.gov.cn）— 含 qdbh/sdbh/sdsin 参数的链接"
                            "<br>• 广东电子送达（sd.gdems.com）— /v3/dzsd/ 链接"
                            "<br>• 简易送达（jysd.10102368.com）— /sd?key= 链接"
                            "<br>• 湖北电子送达（dzsd.hbfy.gov.cn）— 免账号 /hb/msg= 链接 或 账号入口 /sfsddz"
                            "<br>• 司法送达网（sfpt.cdfy12368.gov.cn）— /sfsdw//r/ 链接 + 验证码"
                        ),
                    },
                ),
            ]
        else:
            return list(self.fieldsets)

    def get_form(self, request: HttpRequest, obj: CourtSMS | None = None, change: bool = False, **kwargs: Any) -> Any:
        """自定义表单"""
        form = super().get_form(request, obj, change=change, **kwargs)

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
