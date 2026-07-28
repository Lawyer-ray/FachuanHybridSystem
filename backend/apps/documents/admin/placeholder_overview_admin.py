"""
替换词总览 Admin 配置

提供只读的替换词总览页面，按分类展示系统支持的所有替换词。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, ClassVar

from django.contrib import admin
from django.http import HttpRequest
from django.template.response import TemplateResponse

from apps.documents.models import PlaceholderOverview

# 分类显示名映射
CATEGORY_LABELS: dict[str, str] = {
    "basic": "基础信息",
    "party": "当事人信息",
    "contract": "合同信息",
    "lawyer": "律师信息",
    "litigation": "诉讼文书",
    "supplementary": "补充协议",
    "supplementary_agreement": "补充协议",
    "authorization_materials": "授权材料",
    "authorization_material": "授权材料",
    "case": "案件信息",
    "evidence": "证据清单",
    "archive": "归档",
    "generated": "代码扫描",
    "general": "通用",
}


def _get_catalog_service() -> Any:
    from apps.documents.services.code_placeholders.catalog_service import CodePlaceholderCatalogService

    return CodePlaceholderCatalogService()


@admin.register(PlaceholderOverview)
class PlaceholderOverviewAdmin(admin.ModelAdmin):  # pragma: no cover
    """
    替换词总览

    只读页面，按分类展示系统支持的所有替换词。
    """

    change_list_template = "admin/documents/placeholderoverview/change_list.html"

    list_display: ClassVar[tuple[str, ...]] = ("key",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def get_queryset(self, request: HttpRequest) -> Any:
        """返回空查询集，实际数据在 changelist_view 中处理"""
        return PlaceholderOverview.objects.none()

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> TemplateResponse:
        """自定义 changelist 视图，展示替换词总览"""
        catalog = _get_catalog_service()
        definitions = catalog.list_definitions()

        # 搜索过滤
        query = request.GET.get("q", "").strip()
        if query:
            q_lower = query.lower()
            definitions = [
                d
                for d in definitions
                if q_lower in d.key.lower()
                or q_lower in (d.display_name or "").lower()
                or q_lower in (d.description or "").lower()
                or q_lower in (d.source or "").lower()
            ]

        # 按分类分组
        grouped: OrderedDict[str, list[Any]] = OrderedDict()
        for d in definitions:
            cat = d.category or "general"
            grouped.setdefault(cat, []).append(d)

        # 排序：按分类显示名排序
        sorted_grouped = OrderedDict(
            sorted(
                grouped.items(),
                key=lambda item: CATEGORY_LABELS.get(item[0], item[0]),
            )
        )

        # 统计
        total_count = len(definitions)
        category_stats = {cat: len(items) for cat, items in sorted_grouped.items()}

        extra_context = extra_context or {}
        extra_context.update(
            {
                "grouped_definitions": sorted_grouped,
                "category_labels": CATEGORY_LABELS,
                "total_count": total_count,
                "category_stats": category_stats,
                "search_query": query,
                "title": "替换词总览",
            }
        )

        return super().changelist_view(request, extra_context=extra_context)
