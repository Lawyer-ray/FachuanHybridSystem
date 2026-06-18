"""DocSpaceDocument admin。"""

from __future__ import annotations

from django.contrib import admin

from apps.docspace.models import DocSpaceDocument


@admin.register(DocSpaceDocument)
class DocSpaceDocumentAdmin(admin.ModelAdmin[DocSpaceDocument]):
    list_display = ("title", "lawyer", "file_ext", "content_length", "docspace_file_id", "updated_at")
    list_filter = ("file_ext",)
    search_fields = ("title", "lawyer__real_name", "lawyer__username")
    readonly_fields = ("docspace_file_id", "docspace_folder_id", "created_at", "updated_at")
