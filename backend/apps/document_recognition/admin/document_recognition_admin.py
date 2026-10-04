"""Django admin for document recognition."""

from __future__ import annotations

from typing import Any, ClassVar, cast

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString

from apps.document_recognition.models import (
    DateCandidateStatus,
    DateConfirmationStatus,
    DocumentRecognitionDateCandidate,
    DocumentRecognitionStatus,
    DocumentRecognitionTask,
    DocumentRecognitionTool,
)


class DateCandidateInline(admin.TabularInline):  # pragma: no cover
    """任务详情页只读展示日期候选（确认状态/提醒回链）。"""

    model = DocumentRecognitionDateCandidate
    extra = 0
    can_delete = False
    fields = (
        "due_at",
        "reminder_type",
        "context_text",
        "source",
        "confidence",
        "status_display_inline",
        "reminder_link",
        "confirmed_by",
        "confirmed_at",
    )
    readonly_fields = (
        "due_at",
        "reminder_type",
        "context_text",
        "source",
        "confidence",
        "status_display_inline",
        "reminder_link",
        "confirmed_by",
        "confirmed_at",
    )

    def status_display_inline(self, obj: DocumentRecognitionDateCandidate) -> str:  # pragma: no cover
        return obj.get_status_display()

    status_display_inline.short_description = "确认状态"  # type: ignore[attr-defined]

    def reminder_link(self, obj: DocumentRecognitionDateCandidate) -> SafeString | str:  # pragma: no cover
        if not obj.reminder_id:
            return "-"
        url = reverse("admin:reminders_reminder_change", args=[obj.reminder_id])
        return format_html('<a href="{}" target="_blank">提醒 #{}</a>', url, obj.reminder_id)

    reminder_link.short_description = "已写入提醒"  # type: ignore[attr-defined]

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # pragma: no cover
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # pragma: no cover
        return False


@admin.register(DocumentRecognitionTool)
class DocumentRecognitionToolAdmin(admin.ModelAdmin):  # pragma: no cover
    """Admin entry page for the recognition workbench."""

    def changelist_view(  # pragma: no cover
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> TemplateResponse:
        context = {
            **self.admin_site.each_context(request),
            "title": "法院文书智能识别",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
        }
        return TemplateResponse(request, "admin/document_recognition/recognition.html", context)

    def has_add_permission(self, request: HttpRequest) -> bool:  # pragma: no cover
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: DocumentRecognitionTool | None = None
    ) -> bool:  # pragma: no cover
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: DocumentRecognitionTool | None = None
    ) -> bool:  # pragma: no cover
        return False

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:  # pragma: no cover
        return {"view": True}


@admin.register(DocumentRecognitionTask)
class DocumentRecognitionTaskAdmin(admin.ModelAdmin):  # pragma: no cover
    """Document recognition task list and detail admin."""

    list_display = [
        "id",
        "status_display",
        "original_filename",
        "document_type_display",
        "case_number",
        "case_display",
        "binding_status_display",
        "date_confirmation_display",
        "continue_processing",
        "notification_status_display",
        "created_at",
    ]
    list_filter = [
        "status",
        "document_type",
        "binding_success",
        "date_confirmation_status",
        "notification_sent",
        "created_at",
    ]
    inlines = [DateCandidateInline]
    search_fields: ClassVar[list[str]] = ["original_filename", "case_number", "case__name"]
    ordering = ["-created_at"]
    list_per_page = 20
    readonly_fields: ClassVar[list[str]] = [
        "id",
        "file_path",
        "original_filename",
        "status",
        "document_type",
        "case_number",
        "key_time",
        "confidence",
        "extraction_method",
        "llm_model",
        "llm_backend",
        "llm_latency_ms",
        "degraded",
        "party_names",
        "contacts_display",
        "date_confirmation_status",
        "raw_text_display",
        "renamed_file_path",
        "binding_success",
        "case",
        "case_log",
        "binding_message",
        "binding_error_code",
        "source_court_sms",
        "error_message",
        "notification_sent",
        "notification_sent_at",
        "notification_error",
        "notification_file_sent",
        "created_at",
        "started_at",
        "finished_at",
    ]
    fieldsets = (
        ("基本信息", {"fields": ("id", "original_filename", "file_path", "status")}),
        (
            "识别结果",
            {
                "fields": (
                    "document_type",
                    "case_number",
                    "key_time",
                    "confidence",
                    "extraction_method",
                    "llm_model",
                    "llm_backend",
                    "llm_latency_ms",
                    "degraded",
                    "party_names",
                    "contacts_display",
                    "renamed_file_path",
                )
            },
        ),
        ("日期确认", {"fields": ("date_confirmation_status",)}),
        ("原始文本", {"fields": ("raw_text_display",), "classes": ("collapse",)}),
        (
            "绑定结果",
            {
                "fields": (
                    "binding_success",
                    "case",
                    "case_log",
                    "source_court_sms",
                    "binding_message",
                    "binding_error_code",
                )
            },
        ),
        (
            "通知状态",
            {
                "fields": ("notification_sent", "notification_sent_at", "notification_file_sent", "notification_error"),
            },
        ),
        ("错误信息", {"fields": ("error_message",), "classes": ("collapse",)}),
        ("时间戳", {"fields": ("created_at", "started_at", "finished_at"), "classes": ("collapse",)}),
    )

    def get_urls(self) -> list[Any]:  # pragma: no cover
        urls = super().get_urls()
        custom_urls = [
            path(
                "recognize/",
                self.admin_site.admin_view(self.recognition_view),
                name="document_recognition_task_recognize",
            ),
        ]
        return custom_urls + urls

    def recognition_view(self, request: HttpRequest) -> HttpResponse:  # pragma: no cover
        context = {
            **self.admin_site.each_context(request),
            "title": "法院文书智能识别",
            "opts": self.model._meta,
            "has_view_permission": True,
        }
        return render(request, "admin/document_recognition/recognition.html", context)

    def status_display(self, obj: DocumentRecognitionTask) -> SafeString:  # pragma: no cover
        status_colors: dict[str, str] = {
            DocumentRecognitionStatus.PENDING: "orange",
            DocumentRecognitionStatus.PROCESSING: "blue",
            DocumentRecognitionStatus.SUCCESS: "green",
            DocumentRecognitionStatus.FAILED: "red",
        }
        color = status_colors.get(obj.status, "gray")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_display.short_description = "任务状态"  # type: ignore[attr-defined]
    status_display.admin_order_field = "status"  # type: ignore[attr-defined]

    def document_type_display(self, obj: DocumentRecognitionTask) -> str:  # pragma: no cover
        if not obj.document_type:
            return "-"

        type_icons: dict[str, str] = {
            "summons": "📋",
            "execution": "⚖️",
            "execution_ruling": "⚖️",
            "other": "📄",
        }
        icon = type_icons.get(obj.document_type, "📄")
        return f"{icon} {obj.document_type}"

    document_type_display.short_description = "文书类型"  # type: ignore[attr-defined]
    document_type_display.admin_order_field = "document_type"  # type: ignore[attr-defined]

    def case_display(self, obj: DocumentRecognitionTask) -> SafeString | str:  # pragma: no cover
        if obj.case:
            url = reverse("admin:cases_case_change", args=[obj.case.id])
            case_name = obj.case.name
            if len(case_name) > 30:
                case_name = case_name[:30] + "..."
            return format_html('<a href="{}" target="_blank">{}</a>', url, case_name)
        return "-"

    case_display.short_description = "关联案件"  # type: ignore[attr-defined]

    def binding_status_display(self, obj: DocumentRecognitionTask) -> SafeString:  # pragma: no cover
        if obj.binding_success is None:
            return format_html('<span style="color: gray;">{}</span>', "- 未绑定")
        if obj.binding_success:
            return format_html('<span style="color: green;">{}</span>', "✓ 绑定成功")
        error_preview = obj.binding_error_code or "未知错误"
        return format_html(
            '<span style="color: red;">✗ 绑定失败</span><br><small style="color: #d63384;">{}</small>',
            error_preview,
        )

    binding_status_display.short_description = "绑定状态"  # type: ignore[attr-defined]

    def date_confirmation_display(self, obj: DocumentRecognitionTask) -> SafeString | str:  # pragma: no cover
        total = getattr(obj, "total_candidates", None)
        if total is None:
            total = obj.date_candidates.count()
        confirmed = getattr(obj, "confirmed_candidates", None)
        if confirmed is None:
            confirmed = obj.date_candidates.filter(status=DateCandidateStatus.CONFIRMED).count()
        if total == 0:
            return "-"
        label = f"{confirmed}/{total} 已确认"
        if obj.date_confirmation_status == DateConfirmationStatus.COMPLETE:
            return format_html('<span style="color: green;">✓ {}</span>', label)
        return format_html('<span style="color: orange;">{}</span>', label)

    date_confirmation_display.short_description = "日期确认"  # type: ignore[attr-defined]

    def continue_processing(self, obj: DocumentRecognitionTask) -> SafeString | str:  # pragma: no cover
        if obj.status != DocumentRecognitionStatus.SUCCESS:
            return "-"
        url = reverse("admin:document_recognition_documentrecognitiontool_changelist") + f"?task={obj.id}"
        return format_html('<a href="{}" class="button">继续处理</a>', url)

    continue_processing.short_description = "操作"  # type: ignore[attr-defined]

    def notification_status_display(self, obj: DocumentRecognitionTask) -> SafeString:  # pragma: no cover
        if not obj.binding_success:
            return format_html('<span style="color: gray;">{}</span>', "- 无需通知")

        if obj.notification_sent:
            file_status = "✓ 文件已发送" if obj.notification_file_sent else "✗ 文件未发送"
            return format_html(
                '<span style="color: green;">✓ 通知成功</span><br><small style="color: #666;">{}</small>',
                file_status,
            )

        if obj.notification_error:
            error_preview = obj.notification_error[:30] + ("..." if len(obj.notification_error) > 30 else "")
            return format_html(
                '<span style="color: red;">✗ 通知失败</span><br><small style="color: #d63384;">{}</small>',
                error_preview,
            )

        return format_html('<span style="color: orange;">{}</span>', "⏳ 待发送")

    notification_status_display.short_description = "通知状态"  # type: ignore[attr-defined]

    def raw_text_display(self, obj: DocumentRecognitionTask) -> SafeString | str:  # pragma: no cover
        if obj.raw_text:
            return format_html(
                '<div style="max-height: 300px; overflow-y: auto; '
                "white-space: pre-wrap; font-family: monospace; "
                'background: #f5f5f5; padding: 10px; border-radius: 4px;">{}</div>',
                obj.raw_text,
            )
        return "-"

    raw_text_display.short_description = "原始文本"  # type: ignore[attr-defined]

    def contacts_display(self, obj: DocumentRecognitionTask) -> str:  # pragma: no cover
        from apps.document_recognition.services.contact_extraction_service import extract_address, extract_contacts

        parts: list[str] = []
        for row in extract_contacts(obj.raw_text):
            name, phone = str(row["name"]), row["phone"]
            if name and phone:
                parts.append(f"{name}（{phone}）")
            elif name or phone:
                parts.append(name or str(phone))
        address = extract_address(obj.raw_text)
        if address:
            parts.append(f"地址：{address}")
        return "；".join(parts) if parts else "-"

    contacts_display.short_description = "联系人/地址"  # type: ignore[attr-defined]

    def get_queryset(self, request: HttpRequest) -> QuerySet[DocumentRecognitionTask]:  # pragma: no cover
        from django.db.models import Count, Q

        qs = (
            super()
            .get_queryset(request)
            .select_related("case", "case_log")
            .annotate(
                total_candidates=Count("date_candidates"),
                confirmed_candidates=Count(
                    "date_candidates", filter=Q(date_candidates__status=DateCandidateStatus.CONFIRMED)
                ),
            )
        )
        return cast(QuerySet[DocumentRecognitionTask], qs)

    def has_add_permission(self, request: HttpRequest) -> bool:  # pragma: no cover
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: DocumentRecognitionTask | None = None
    ) -> bool:  # pragma: no cover
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: DocumentRecognitionTask | None = None
    ) -> bool:  # pragma: no cover
        return True
