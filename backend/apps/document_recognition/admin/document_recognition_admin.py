"""Django admin for document recognition."""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.document_recognition.models import DocumentRecognitionStatus, DocumentRecognitionTask, DocumentRecognitionTool


@admin.register(DocumentRecognitionTool)
class DocumentRecognitionToolAdmin(admin.ModelAdmin[DocumentRecognitionTool]):
    """Admin entry page for the recognition workbench."""

    def changelist_view(  # type: ignore[override]
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

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: DocumentRecognitionTool | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: DocumentRecognitionTool | None = None) -> bool:
        return False

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        return {"view": True}


@admin.register(DocumentRecognitionTask)
class DocumentRecognitionTaskAdmin(admin.ModelAdmin[DocumentRecognitionTask]):
    """Document recognition task list and detail admin."""

    list_display: ClassVar[list[str]] = [
        "id",
        "status_display",
        "original_filename",
        "document_type_display",
        "case_number",
        "case_display",
        "binding_status_display",
        "notification_status_display",
        "notification_sent_at",
        "created_at",
    ]
    list_filter: ClassVar[list[str]] = [
        "status",
        "document_type",
        "binding_success",
        "notification_sent",
        "created_at",
    ]
    search_fields: ClassVar[list[str]] = ["original_filename", "case_number", "case__name"]
    ordering: ClassVar[list[str]] = ["-created_at"]
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
        "raw_text_display",
        "renamed_file_path",
        "binding_success",
        "case",
        "case_log",
        "binding_message",
        "binding_error_code",
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
        (_("基本信息"), {"fields": ("id", "original_filename", "file_path", "status")}),
        (_("识别结果"), {"fields": ("document_type", "case_number", "key_time", "confidence", "extraction_method", "renamed_file_path")}),
        (_("原始文本"), {"fields": ("raw_text_display",), "classes": ("collapse",)}),
        (_("绑定结果"), {"fields": ("binding_success", "case", "case_log", "binding_message", "binding_error_code")}),
        (
            _("通知状态"),
            {
                "fields": ("notification_sent", "notification_sent_at", "notification_file_sent", "notification_error"),
                "description": "绑定成功后的飞书群通知状态",
            },
        ),
        (_("错误信息"), {"fields": ("error_message",), "classes": ("collapse",)}),
        (_("时间戳"), {"fields": ("created_at", "started_at", "finished_at"), "classes": ("collapse",)}),
    )

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom_urls = [
            path(
                "recognize/",
                self.admin_site.admin_view(self.recognition_view),
                name="document_recognition_task_recognize",
            ),
        ]
        return custom_urls + urls

    def recognition_view(self, request: HttpRequest) -> HttpResponse:
        context = {
            **self.admin_site.each_context(request),
            "title": "法院文书智能识别",
            "opts": self.model._meta,
            "has_view_permission": True,
        }
        return render(request, "admin/document_recognition/recognition.html", context)

    def status_display(self, obj: DocumentRecognitionTask) -> SafeString:
        status_colors: dict[str, str] = {
            DocumentRecognitionStatus.PENDING: "orange",
            DocumentRecognitionStatus.PROCESSING: "blue",
            DocumentRecognitionStatus.SUCCESS: "green",
            DocumentRecognitionStatus.FAILED: "red",
        }
        color = status_colors.get(obj.status, "gray")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_display.short_description = _("任务状态")  # type: ignore[attr-defined]
    status_display.admin_order_field = "status"  # type: ignore[attr-defined]

    def document_type_display(self, obj: DocumentRecognitionTask) -> str:
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

    document_type_display.short_description = _("文书类型")  # type: ignore[attr-defined]
    document_type_display.admin_order_field = "document_type"  # type: ignore[attr-defined]

    def case_display(self, obj: DocumentRecognitionTask) -> SafeString | str:
        if obj.case:
            url = reverse("admin:cases_case_change", args=[obj.case.id])
            case_name = obj.case.name
            if len(case_name) > 30:
                case_name = case_name[:30] + "..."
            return format_html('<a href="{}" target="_blank">{}</a>', url, case_name)
        return "-"

    case_display.short_description = _("关联案件")  # type: ignore[attr-defined]

    def binding_status_display(self, obj: DocumentRecognitionTask) -> SafeString:
        if obj.binding_success is None:
            return format_html('<span style="color: gray;">{}</span>', "- 未绑定")
        if obj.binding_success:
            return format_html('<span style="color: green;">{}</span>', "✓ 绑定成功")
        error_preview = obj.binding_error_code or "未知错误"
        return format_html(
            '<span style="color: red;">✗ 绑定失败</span><br><small style="color: #d63384;">{}</small>',
            error_preview,
        )

    binding_status_display.short_description = _("绑定状态")  # type: ignore[attr-defined]

    def notification_status_display(self, obj: DocumentRecognitionTask) -> SafeString:
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

    notification_status_display.short_description = _("通知状态")  # type: ignore[attr-defined]

    def raw_text_display(self, obj: DocumentRecognitionTask) -> SafeString | str:
        if obj.raw_text:
            return format_html(
                '<div style="max-height: 300px; overflow-y: auto; '
                "white-space: pre-wrap; font-family: monospace; "
                'background: #f5f5f5; padding: 10px; border-radius: 4px;">{}</div>',
                obj.raw_text,
            )
        return "-"

    raw_text_display.short_description = _("原始文本")  # type: ignore[attr-defined]

    def get_queryset(self, request: HttpRequest) -> QuerySet[DocumentRecognitionTask]:
        return super().get_queryset(request).select_related("case", "case_log")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: DocumentRecognitionTask | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: DocumentRecognitionTask | None = None) -> bool:
        return True
