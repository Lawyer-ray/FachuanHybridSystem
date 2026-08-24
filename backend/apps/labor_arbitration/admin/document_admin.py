"""仲裁文书 Admin：列表/详情 + 图片预览 + 调用文档解析按钮。"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString

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
        "image_count",
        "crawl_status",
        "parse_status",
        "parsed_at",
    )
    list_filter = ("source", "crawl_status", "parse_status", "publish_date")
    search_fields = ("title", "case_number", "detail_url")
    readonly_fields = (
        "source",
        "title",
        "case_number",
        "detail_url",
        "publish_date",
        "crawl_status",
        "error_message",
        "image_count",
        "images_preview",
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
        from django.conf import settings

        rows = [
            (settings.MEDIA_URL + img.image.name, img.page_index + 1, img.source_url)
            for img in obj.images.order_by("page_index")
        ]
        if not rows:
            return format_html("<span>{}</span>", "暂无图片")
        # 用 format_html_join 拼接：str(SafeString) 会退化为普通 str 而被转义，不可手工 join
        return format_html_join(
            "",
            '<div style="margin-bottom:10px;">'
            '<img src="{}" style="max-width:760px; border:1px solid #ccc;" />'
            '<div style="font-size:11px;color:#888;">第 {} 页 · {}</div></div>',
            rows,
        )

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

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom = [
            path(
                "<pk>/parse/",
                self.admin_site.admin_view(self.parse_view),
                name="labor_arbitration_arbitrationdocument_parse",
            ),
        ]
        return custom + urls

    def parse_view(self, request: HttpRequest, pk: str) -> HttpResponseRedirect:
        doc = ArbitrationDocument.objects.get(pk=pk)
        task_id = doc.trigger_parse()
        self.message_user(request, f"已提交文档解析任务（任务ID: {task_id}）。")
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

    actions = ["trigger_parse_action"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
