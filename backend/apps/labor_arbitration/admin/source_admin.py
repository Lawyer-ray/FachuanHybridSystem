"""仲裁文书来源 Admin：列表/详情 + 增量更新按钮。"""

from __future__ import annotations

import json
from typing import Any

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString

from apps.labor_arbitration.models import ArbitrationDocumentSource


@admin.register(ArbitrationDocumentSource)
class ArbitrationDocumentSourceAdmin(admin.ModelAdmin):
    """来源管理：可触发增量爬取。"""

    list_display = (
        "id",
        "name",
        "district",
        "list_url",
        "enabled",
        "document_count",
        "last_crawl_status",
        "last_crawl_at",
    )
    list_filter = ("district", "enabled", "last_crawl_status")
    search_fields = ("name", "list_url")
    readonly_fields = (
        "document_count",
        "last_crawl_at",
        "last_crawl_status",
        "last_crawl_summary_display",
        "update_button",
    )
    fieldsets = (
        ("基本信息", {"fields": ("name", "district", "list_url", "enabled")}),
        (
            "爬取配置",
            {
                "fields": (
                    "parse_backend",
                    "max_pages",
                    "detail_image_container_selector",
                    "detail_image_selector",
                )
            },
        ),
        ("更新操作", {"fields": ("update_button",)}),
        ("上次爬取", {"fields": ("last_crawl_status", "last_crawl_at", "last_crawl_summary_display")}),
    )

    @admin.display(description="文书数")
    def document_count(self, obj: ArbitrationDocumentSource) -> int:
        return obj.documents.count()

    @admin.display(description="上次爬取摘要")
    def last_crawl_summary_display(self, obj: ArbitrationDocumentSource) -> SafeString:
        if not obj.last_crawl_summary:
            return format_html("<span>{}</span>", "-")
        pretty = json.dumps(obj.last_crawl_summary, indent=2, ensure_ascii=False)
        return format_html("<pre style='max-height:300px;overflow:auto;'>{}</pre>", pretty)

    @admin.display(description="增量更新")
    def update_button(self, obj: ArbitrationDocumentSource) -> SafeString:
        if obj.pk is None:
            return format_html("<span>{}</span>", "-")
        url = reverse("admin:labor_arbitration_arbitrationdocumentsource_update", args=[obj.pk])
        return format_html('<a class="button" href="{}">增量更新（爬取新文书）</a>', url)

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom = [
            path(
                "<pk>/update/",
                self.admin_site.admin_view(self.update_view),
                name="labor_arbitration_arbitrationdocumentsource_update",
            ),
        ]
        return custom + urls

    def update_view(self, request: HttpRequest, pk: str) -> HttpResponseRedirect:
        source = ArbitrationDocumentSource.objects.get(pk=pk)
        task_id = source.trigger_update()
        self.message_user(request, f"已提交增量更新任务（任务ID: {task_id}），可在后台队列查看进度。")
        return HttpResponseRedirect(reverse("admin:labor_arbitration_arbitrationdocumentsource_change", args=[pk]))

    @admin.action(description="增量更新选中的来源")
    def trigger_update_action(self, request: HttpRequest, queryset: Any) -> None:
        count = 0
        for src in queryset:
            src.trigger_update()
            count += 1
        self.message_user(request, f"已提交 {count} 个来源的增量更新任务")

    actions = ["trigger_update_action"]
