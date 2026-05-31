"""公众号发布 Admin 配置"""

from __future__ import annotations

import logging

from django.contrib import admin

from apps.wechat_mp.models import PublishTask, PublishTaskStatus, WeChatAccount

logger = logging.getLogger(__name__)

@admin.register(WeChatAccount)
class WeChatAccountAdmin(admin.ModelAdmin):
    list_display = ["name", "mp_url", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    exclude = ["created_by"]
    readonly_fields = ["created_at", "updated_at"]

    def save_model(self, request, obj, form, change):  # type: ignore[no-untyped-def]
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(PublishTask)
class PublishTaskAdmin(admin.ModelAdmin):
    list_display = ["title", "account", "status", "format_method", "save_as_draft", "created_at", "finished_at"]
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
        (None, {"fields": ["account", "title", "save_as_draft", "format_method"]}),
        ("内容", {"fields": ["content_md", "content_html", "cover_image"]}),
        ("状态", {"fields": ["status", "queue_task_id", "result_data", "error_message"]}),
        ("时间", {"fields": ["created_at", "started_at", "finished_at", "updated_at"]}),
    ]

    def save_model(self, request, obj, form, change):  # type: ignore[no-untyped-def]
        super().save_model(request, obj, form, change)

        # 新建任务且状态为 PENDING 时，自动调度异步执行
        if not change and obj.status == PublishTaskStatus.PENDING:
            from apps.core.tasking import submit_task

            queue_task_id = submit_task("apps.wechat_mp.tasks.execute_publish_task", obj.id)
            obj.queue_task_id = str(queue_task_id)
            obj.save(update_fields=["queue_task_id"])
            logger.info("Admin 创建发布任务并调度: task_id=%d, queue_id=%s", obj.id, queue_task_id)
