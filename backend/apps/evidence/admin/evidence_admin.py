"""Django admin configuration."""

import logging
from collections import defaultdict
from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from apps.evidence.models import EvidenceList

from .evidence import EvidenceItemInline, EvidenceListForm
from .evidence.mixins import EvidenceListAdminActionsMixin, EvidenceListAdminSaveMixin, EvidenceListAdminViewsMixin
from .hearing_mode import HearingModeAdminMixin

logger = logging.getLogger(__name__)


@admin.register(EvidenceList)
class EvidenceListAdmin(
    HearingModeAdminMixin,
    EvidenceListAdminViewsMixin,
    EvidenceListAdminActionsMixin,
    EvidenceListAdminSaveMixin,
    admin.ModelAdmin,
):
    form = EvidenceListForm

    list_display: tuple[Any, ...] = (
        "title",
        "case_display",
        "list_type",
        "item_count_display",
        "order_range_display",
        "total_pages_display",
        "page_range_display",
        "export_version",
        "has_merged_pdf_display",
        "actions_display",
        "hearing_mode_link",
        "updated_at",
    )

    list_filter: tuple[Any, ...] = ("case", "list_type")
    search_fields: tuple[Any, ...] = ("title", "case__name")
    ordering: ClassVar = ["case", "order"]
    autocomplete_fields: tuple[Any, ...] = ("export_template",)

    readonly_fields: tuple[Any, ...] = (
        "list_type",
        "order",
        "page_range_display",
        "order_range_display",
        "total_pages",
        "merged_pdf",
        "created_by",
        "created_at",
        "updated_at",
    )

    fieldsets: tuple[Any, ...] = (
        (None, {"fields": ("case",)}),
        (
            "自动计算信息",
            {
                "fields": ("list_type", "order_range_display", "total_pages", "page_range_display"),
                "description": "以下信息由系统自动计算,无需手动填写.",
            },
        ),
        (
            "合并PDF",
            {
                "fields": ("merged_pdf",),
                "description": "点击列表页的「合并」按钮将证据文件合并为PDF.",
            },
        ),
        (
            "导出设置",
            {
                "fields": ("export_version", "export_template"),
                "description": "导出版本号用于文件名控制,请手动修改.选择导出模板后,导出清单时将使用该模板格式.",
                "classes": ("evidence-export-section",),
            },
        ),
        (
            "系统信息",
            {
                "fields": ("created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    inlines: ClassVar = [EvidenceItemInline]
    actions: ClassVar = ["merge_pdfs", "export_list_word", "export_list_zip"]
    list_select_related: tuple[Any, ...] = ("case", "created_by")

    def get_queryset(self, request: Any) -> QuerySet:
        return super().get_queryset(request).annotate(item_count=Count("items"))  # type: ignore[no-any-return]

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> Any:
        """覆写 changelist：批量预计算 start_order/start_page，消除链式遍历 N+1。

        对当前页涉及的每个 Case，一次性获取其所有 EvidenceList（含 item_count），
        按 order 排序后累加计算 start_order 和 start_page，写入实例 __dict__ 缓存。
        """
        response = super().changelist_view(request, extra_context)

        cl = getattr(self, "changelist_instance", None)
        if cl is None or not hasattr(cl, "result_list") or not cl.result_list:
            return response

        # 按 case_id 分组
        case_groups: dict[int, list[EvidenceList]] = defaultdict(list)
        for obj in cl.result_list:
            case_groups[obj.case_id].append(obj)

        for case_id, page_objs in case_groups.items():
            # 获取该 Case 的所有 EvidenceList（含 item_count 注解），按 order 排序
            all_lists = (
                EvidenceList.objects.filter(case_id=case_id)
                .annotate(_batch_item_count=Count("items"))
                .order_by("order", "pk")
                .only("pk", "order", "total_pages")
            )

            # 累加计算 start_order 和 start_page
            running_order = 1
            running_page = 1
            computed: dict[int, tuple[int, int]] = {}  # pk -> (start_order, start_page)
            for el in all_lists:
                computed[el.pk] = (running_order, running_page)
                item_cnt = getattr(el, "_batch_item_count", 0) or 0
                running_order += item_cnt
                running_page += el.total_pages or 0

            # 写入页面实例的 __dict__（@property 优先检查 __dict__）
            for obj in page_objs:
                start_o, start_p = computed.get(obj.pk, (1, 1))
                obj.__dict__["_cached_start_order"] = start_o
                obj.__dict__["_cached_start_page"] = start_p

        return response

    @admin.display(description="开庭")
    def hearing_mode_link(self, obj: EvidenceList) -> str:
        url = reverse("admin:evidence_hearing_mode", args=[obj.case_id])
        return format_html('<a class="button" href="{}" target="_blank">⚖️</a>', url)

    class Media:
        css: ClassVar = {"all": ("evidence/css/evidence_admin.css",)}
        js: tuple[Any, ...] = (
            "evidence/js/evidence_sortable.js",
            "evidence/js/evidence_merge.js",
            "evidence/js/evidence_list_type.js",
        )
