"""公众号发布 Admin 配置"""

from __future__ import annotations

from django.contrib import admin

from apps.wechat_mp.models import PublishTask, WeChatAccount


@admin.register(WeChatAccount)
class WeChatAccountAdmin(admin.ModelAdmin):
    list_display = ["name", "mp_url", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(PublishTask)
class PublishTaskAdmin(admin.ModelAdmin):
    list_display = ["title", "account", "status", "save_as_draft", "created_at", "finished_at"]
    list_select_related = ("account",)
    list_filter = ["status", "save_as_draft", "account"]
    search_fields = ["title"]
    readonly_fields = [
        "queue_task_id",
        "result_data",
        "error_message",
        "created_at",
        "started_at",
        "finished_at",
        "updated_at",
    ]
    fieldsets = [
        (None, {"fields": ["account", "title", "save_as_draft"]}),
        ("内容", {"fields": ["content_md", "content_html", "cover_image"]}),
        ("状态", {"fields": ["status", "queue_task_id", "result_data", "error_message"]}),
        ("时间", {"fields": ["created_at", "started_at", "finished_at", "updated_at"]}),
    ]
