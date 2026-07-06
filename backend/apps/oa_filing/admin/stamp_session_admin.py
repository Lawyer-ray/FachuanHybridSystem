from __future__ import annotations

from django.contrib import admin

from apps.oa_filing.models import StampSession


class StampSessionAdmin(admin.ModelAdmin):  # pragma: no cover
    list_display = [
        "id",
        "oa_case_number",
        "contract",
        "user",
        "file_path",
        "status",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["oa_case_number", "contract__name", "file_path"]
    readonly_fields = [
        "contract",
        "credential",
        "user",
        "oa_case_number",
        "file_path",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    ]
    fieldsets = [
        (
            "会话信息",
            {"fields": ("contract", "credential", "user", "oa_case_number", "file_path", "status")},
        ),
        (
            "错误信息",
            {"fields": ("error_message",), "classes": ("collapse",)},
        ),
        (
            "时间信息",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    ]
