from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.oa_filing.models import FilingSession


class FilingSessionAdmin(admin.ModelAdmin[FilingSession]):
    list_display = [
        "id",
        "contract",
        "case",
        "oa_config",
        "user",
        "status",
        "created_at",
    ]
    list_filter = ["status", "oa_config"]
    search_fields = ["contract__name", "case__case_name"]
    readonly_fields = [
        "contract",
        "case",
        "oa_config",
        "credential",
        "user",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    ]
    fieldsets = [
        (
            _("会话信息"),
            {"fields": ("contract", "case", "oa_config", "credential", "user", "status")},
        ),
        (
            _("错误信息"),
            {"fields": ("error_message",), "classes": ("collapse",)},
        ),
        (
            _("时间信息"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    ]
