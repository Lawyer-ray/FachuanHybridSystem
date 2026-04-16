from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.batch_printing.models import (
    BatchPrintItem,
    BatchPrintJob,
    BatchPrintingTool,
    PrintKeywordRule,
    PrintPresetSnapshot,
)
from apps.batch_printing.services.wiring import get_rule_service


class PrintKeywordRuleAdminForm(forms.ModelForm):
    class Meta:
        model = PrintKeywordRule
        fields = ["keyword", "priority", "enabled", "preset_snapshot", "notes"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        preset_field = self.fields.get("preset_snapshot")
        if preset_field is not None:
            preset_field.queryset = PrintPresetSnapshot.objects.order_by("printer_name", "preset_name")
            preset_field.help_text = "只需选择打印预置，实际打印机会自动取该预置所属打印机，无需单独选择。"


@admin.register(BatchPrintingTool)
class BatchPrintingToolAdmin(admin.ModelAdmin[BatchPrintingTool]):
    def changelist_view(  # type: ignore[override]
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> TemplateResponse:
        context = {
            **self.admin_site.each_context(request),
            "title": "批量打印",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
        }
        return TemplateResponse(request, "admin/batch_printing/workbench.html", context)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: BatchPrintingTool | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: BatchPrintingTool | None = None) -> bool:
        return False

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        return {"view": True}


@admin.register(PrintPresetSnapshot)
class PrintPresetSnapshotAdmin(admin.ModelAdmin[PrintPresetSnapshot]):
    list_display = ["printer_name", "preset_name", "last_synced_at", "updated_at"]
    list_filter = ["printer_name", "last_synced_at"]
    search_fields = ["printer_name", "preset_name"]
    ordering = ["printer_name", "preset_name"]
    readonly_fields = [
        "printer_name",
        "printer_display_name",
        "preset_name",
        "preset_source",
        "raw_settings_payload",
        "executable_options_payload",
        "supported_option_names",
        "last_synced_at",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False


@admin.register(PrintKeywordRule)
class PrintKeywordRuleAdmin(admin.ModelAdmin[PrintKeywordRule]):
    form = PrintKeywordRuleAdminForm
    list_display = ["keyword", "priority", "enabled", "printer_name", "preset_snapshot", "updated_at"]
    list_filter = ["enabled", "printer_name"]
    search_fields = ["keyword", "printer_name", "notes"]
    ordering = ["priority", "id"]
    fields = ["keyword", "priority", "enabled", "preset_snapshot", "resolved_printer_name", "notes"]
    readonly_fields = ["resolved_printer_name"]

    def resolved_printer_name(self, obj: PrintKeywordRule | None) -> str:
        if obj is None or not obj.preset_snapshot_id:
            return "保存后会自动同步为所选预置所属打印机"
        return obj.preset_snapshot.printer_name

    resolved_printer_name.short_description = _("实际打印机")  # type: ignore[attr-defined]

    def save_model(self, request: HttpRequest, obj: PrintKeywordRule, form: forms.ModelForm, change: bool) -> None:
        if obj.preset_snapshot_id:
            get_rule_service().sync_printer_name_from_preset(rule=obj)
        super().save_model(request, obj, form, change)


class BatchPrintItemInline(admin.TabularInline[BatchPrintItem]):
    model = BatchPrintItem
    extra = 0
    can_delete = False
    readonly_fields = [
        "order",
        "source_original_name",
        "file_type",
        "status",
        "matched_keyword",
        "target_printer_name",
        "target_preset_name",
        "cups_job_id",
        "error_message",
        "started_at",
        "finished_at",
    ]


@admin.register(BatchPrintJob)
class BatchPrintJobAdmin(admin.ModelAdmin[BatchPrintJob]):
    list_display = [
        "id",
        "status_display",
        "total_count",
        "processed_count",
        "success_count",
        "failed_count",
        "progress",
        "created_by",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["id", "task_id", "error_message"]
    ordering = ["-created_at"]
    inlines = [BatchPrintItemInline]
    readonly_fields = [
        "id",
        "status",
        "total_count",
        "processed_count",
        "success_count",
        "failed_count",
        "progress",
        "task_id",
        "cancel_requested",
        "created_by",
        "capability_payload",
        "summary_payload",
        "error_message",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def status_display(self, obj: BatchPrintJob) -> SafeString:
        color_map = {
            "pending": "#8d6e63",
            "processing": "#1565c0",
            "completed": "#2e7d32",
            "partial_failed": "#ef6c00",
            "failed": "#c62828",
            "cancelled": "#546e7a",
        }
        color = color_map.get(obj.status, "#546e7a")
        return format_html('<span style="color:{};font-weight:700;">{}</span>', color, obj.get_status_display())

    status_display.short_description = _("状态")  # type: ignore[attr-defined]
