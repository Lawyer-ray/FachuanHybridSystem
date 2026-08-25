"""仲裁文书 Admin：列表/详情 + 图片预览 + 调用文档解析按钮。"""

from __future__ import annotations

from html import escape as html_escape
from typing import Any

from django.contrib import admin
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db import models as db_models
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe

from apps.labor_arbitration.models import ArbitrationDocument


@admin.register(ArbitrationDocument)
class ArbitrationDocumentAdmin(admin.ModelAdmin):
    """文书管理：展示图片与解析结果，可触发文档解析。"""

    list_display = (
        "id",
        "title",
        "case_number",
        "source",
        "publish_date",
        "publish_datetime",
        "created_at",
        "image_count",
        "crawl_status",
        "parse_status",
        "parsed_at",
    )
    list_filter = ("source", "crawl_status", "parse_status", "publish_date", "publish_datetime")
    search_fields = ("title", "case_number", "detail_url", "parsed_text")
    readonly_fields = (
        "source",
        "title",
        "case_number",
        "detail_url",
        "publish_date",
        "publish_datetime",
        "created_at",
        "crawl_status",
        "error_message",
        "image_count",
        "images_preview",
        "retry_button",
        "parse_status",
        "parsed_at",
        "parsed_text_display",
        "parse_error",
        "parse_button",
    )
    fieldsets = (
        (
            "基本信息",
            {
                "fields": (
                    "source",
                    "title",
                    "case_number",
                    "detail_url",
                    "publish_date",
                    "publish_datetime",
                    "created_at",
                    "crawl_status",
                    "image_count",
                )
            },
        ),
        ("图片（扫描件）", {"fields": ("images_preview",)}),
        (
            "文档解析",
            {
                "fields": (
                    "parse_button",
                    "parse_status",
                    "parsed_at",
                    "parse_error",
                    "parsed_text_display",
                )
            },
        ),
    )

    @admin.display(description="图片数")
    def image_count(self, obj: ArbitrationDocument) -> int:
        return obj.images.count()

    @admin.display(description="图片预览")
    def images_preview(self, obj: ArbitrationDocument) -> SafeString:
        images = list(obj.images.order_by("page_index"))
        if not images:
            return format_html("<span>{}</span>", "暂无图片")

        preview_id = f"img-preview-{obj.pk}"
        hidden_items = "".join(
            f'<div style="display:none;" data-src="{html_escape(img.source_url)}" data-page="{img.page_index + 1}"></div>'
            for img in images
        )

        html = (
            f'<div id="{preview_id}">'
            f"{hidden_items}"
            '<button type="button" class="button" onclick="'
            "var el=this.parentNode;"
            "el.querySelectorAll('[data-src]').forEach(function(item){"
            "item.style.display='';"
            "var i=document.createElement('img');i.src=item.dataset.src;"
            "i.style.maxWidth='760px';i.style.border='1px solid #ccc';"
            "var c=document.createElement('div');c.style.fontSize='11px';"
            "c.style.color='#888';c.textContent='第 '+item.dataset.page+' 页 · '+item.dataset.src;"
            "item.appendChild(i);item.appendChild(c);"
            "});"
            "this.style.display='none';"
            f'">显示图片（共 {len(images)} 页）</button>'
            "</div>"
        )
        return mark_safe(html)

    @admin.display(description="解析文本")
    def parsed_text_display(self, obj: ArbitrationDocument) -> SafeString:
        if not obj.parsed_text:
            return format_html("<span>{}</span>", "-")
        return format_html(
            "<pre style='max-height:420px;overflow:auto;white-space:pre-wrap;'>{}</pre>",
            obj.parsed_text[:20000],
        )

    @admin.display(description="文档解析")
    def parse_button(self, obj: ArbitrationDocument) -> SafeString:
        if obj.pk is None:
            return format_html("<span>{}</span>", "-")
        if obj.images.count() == 0:
            return format_html('<span style="color:#c0392b;">{}</span>', "无图片可解析")
        url = reverse("admin:labor_arbitration_arbitrationdocument_parse", args=[obj.pk])
        return format_html('<a class="button" href="{}">调用文档解析</a>', url)

    @admin.display(description="重试抓取")
    def retry_button(self, obj: ArbitrationDocument) -> SafeString:
        if obj.pk is None:
            return format_html("<span>{}</span>", "-")
        url = reverse("admin:labor_arbitration_arbitrationdocument_retry", args=[obj.pk])
        label = "重试抓取图片" if obj.images.count() == 0 else "重新抓取"
        return format_html('<a class="button" href="{}">{}</a>', url, label)

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom = [
            path(
                "<pk>/parse/",
                self.admin_site.admin_view(self.parse_view),
                name="labor_arbitration_arbitrationdocument_parse",
            ),
            path(
                "<pk>/retry/",
                self.admin_site.admin_view(self.retry_view),
                name="labor_arbitration_arbitrationdocument_retry",
            ),
        ]
        return custom + urls

    def parse_view(self, request: HttpRequest, pk: str) -> HttpResponseRedirect:
        doc = ArbitrationDocument.objects.get(pk=pk)
        task_id = doc.trigger_parse()
        self.message_user(request, f"已提交文档解析任务（任务ID: {task_id}）。")
        return HttpResponseRedirect(reverse("admin:labor_arbitration_arbitrationdocument_change", args=[pk]))

    def retry_view(self, request: HttpRequest, pk: str) -> HttpResponseRedirect:
        doc = ArbitrationDocument.objects.get(pk=pk)
        task_id = doc.trigger_recrawl()
        self.message_user(request, f"已提交重试抓取任务（任务ID: {task_id}），完成后刷新查看图片。")
        return HttpResponseRedirect(reverse("admin:labor_arbitration_arbitrationdocument_change", args=[pk]))

    @admin.action(description="调用文档解析（选中文书）")
    def trigger_parse_action(self, request: HttpRequest, queryset: Any) -> None:
        count = 0
        for doc in queryset:
            if doc.images.count() == 0:
                continue
            doc.trigger_parse()
            count += 1
        self.message_user(request, f"已提交 {count} 个文书的解析任务")

    @admin.action(description="重试抓取图片（选中文书）")
    def retry_action(self, request: HttpRequest, queryset: Any) -> None:
        count = 0
        for doc in queryset:
            doc.trigger_recrawl()
            count += 1
        self.message_user(request, f"已提交 {count} 个文书的重试抓取任务")

    actions = ["trigger_parse_action", "retry_action"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def get_search_results(self, request: HttpRequest, queryset: Any, search_term: str) -> tuple[Any, bool]:
        """覆盖 Admin 默认搜索：优先 PostgreSQL 全文搜索，无结果时回退至传统 ILIKE。"""
        if not search_term:
            return super().get_search_results(request, queryset, search_term)

        query = SearchQuery(search_term, config="simple", search_type="plain")

        # 1. 先尝试全文搜索（按相关性排名）
        ft_qs = (
            queryset.filter(search_vector=query)
            .annotate(rank=SearchRank(db_models.F("search_vector"), query))
            .order_by("-rank")
        )

        if ft_qs.exists():
            return ft_qs, False

        # 2. 无 FTS 命中，回退到 search_fields 的 ILIKE 行为
        return super().get_search_results(request, queryset, search_term)
