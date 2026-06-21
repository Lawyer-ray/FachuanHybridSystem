"""Redis 任务队列管理 Admin。

当 Django Q 使用 Redis broker 时，在 Admin 中提供队列查看/删除/清空功能。
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db import models
from django.http import HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils.translation import gettext_lazy as _

from apps.core.tasking.redis_queue import (
    delete_task_by_index,
    delete_tasks_by_ids,
    get_queue_length,
    is_redis_broker,
    list_tasks,
    purge_queue,
)


class RedisQueueTool(models.Model):
    """虚拟模型：Redis 任务队列管理工具入口（不建数据库表）。"""

    class Meta:
        app_label = "core"
        managed = False
        verbose_name = "Redis 任务队列"
        verbose_name_plural = "Redis 任务队列"


@admin.register(RedisQueueTool)
class RedisQueueAdmin(admin.ModelAdmin):  # pragma: no cover
    """Redis 任务队列管理页面。"""

    # ---- 权限控制 ----

    def has_module_permission(self, request: HttpRequest) -> bool:
        if not is_redis_broker():
            return False
        return bool(request.user and request.user.is_active and request.user.is_superuser)

    def has_view_permission(self, request: HttpRequest, obj: Any | None = None) -> bool:
        if not is_redis_broker():
            return False
        return bool(request.user and request.user.is_active and request.user.is_superuser)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any | None = None) -> bool:
        return False

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        if not self.has_view_permission(request):
            return {}
        return {"view": True, "add": False, "change": False, "delete": False}

    # ---- 主视图 ----

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> TemplateResponse:
        if not is_redis_broker():
            messages.warning(request, _("当前未使用 Redis 作为任务队列，此功能不可用。"))
            return HttpResponseRedirect("/admin/")

        if request.method == "POST":
            return self._handle_post(request)

        return self._render_list(request)

    # ---- POST 处理 ----

    def _handle_post(self, request: HttpRequest) -> HttpResponseRedirect:
        action = request.POST.get("action")

        if action == "purge":
            count = purge_queue()
            messages.success(request, _(f"已清空队列，共删除 {count} 个任务。"))

        elif action == "delete_selected":
            raw_ids = request.POST.getlist("task_ids")
            if raw_ids:
                count = delete_tasks_by_ids(set(raw_ids))
                messages.success(request, _(f"已删除 {count} 个任务。"))

        elif action == "delete_one":
            try:
                index = int(request.POST.get("index", "-1"))
                if delete_task_by_index(index):
                    messages.success(request, _("已删除该任务。"))
                else:
                    messages.warning(request, _("任务未找到，可能已被处理。"))
            except (ValueError, TypeError):
                messages.error(request, _("无效的任务索引。"))

        return HttpResponseRedirect(request.path)

    # ---- GET 渲染 ----

    def _render_list(self, request: HttpRequest) -> TemplateResponse:
        queue_length = get_queue_length()
        tasks = list_tasks(limit=500)

        context = {
            **self.admin_site.each_context(request),
            "title": "Redis 任务队列",
            "tasks": tasks,
            "queue_length": queue_length,
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
            "has_view_permission": True,
        }
        return TemplateResponse(request, "admin/core/redisqueuetool/change_list.html", context)
