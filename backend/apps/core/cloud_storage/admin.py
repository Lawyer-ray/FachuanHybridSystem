"""Admin registration for CloudStorageAccount."""

from __future__ import annotations

from django.contrib import admin

from .models import CloudStorageAccount


@admin.register(CloudStorageAccount)
class CloudStorageAccountAdmin(admin.ModelAdmin):
    list_display = ["name", "storage_type", "is_active", "created_at"]
    list_filter = ["storage_type", "is_active"]
    search_fields = ["name"]

    FIELDSETS = [
        ("基本信息", {"fields": ["name", "storage_type", "is_active"]}),
        (
            "坚果云 WebDAV",
            {
                "fields": ["webdav_url", "webdav_username", "webdav_password", "webdav_root_path"],
                "classes": ["collapse", "webdav-section"],
            },
        ),
        (
            "OneDrive",
            {
                "fields": [
                    "onedrive_client_id",
                    "onedrive_tenant_id",
                    "onedrive_root_path",
                    "onedrive_access_token",
                    "onedrive_refresh_token",
                    "onedrive_token_expires_at",
                ],
                "classes": ["collapse", "onedrive-section"],
            },
        ),
        (
            "本地文件系统",
            {
                "fields": ["local_root_path"],
                "classes": ["collapse", "local-section"],
            },
        ),
    ]

    fieldsets = FIELDSETS  # type: ignore[assignment]

    class Media:
        js = ("admin/js/cloud_storage_admin.js",)

    def get_readonly_fields(self, request, obj=None):  # type: ignore[override]
        if obj and obj.storage_type == "onedrive":
            return ["onedrive_token_expires_at"]
        return []
