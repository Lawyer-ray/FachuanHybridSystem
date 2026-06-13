"""doc_convert Admin - 要素式转换工作台。"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.template.response import TemplateResponse

from apps.doc_convert.models import DocConvertTool


def _has_doc_convert_plugin() -> bool:
    """检测要素式转换插件是否可用。"""
    try:
        from plugins import has_doc_convert_plugin

        return has_doc_convert_plugin()
    except ImportError:
        return False


@admin.register(DocConvertTool)
class DocConvertToolAdmin(admin.ModelAdmin):  # pragma: no cover
    """要素式转换工作台 Admin。"""

    def changelist_view(  # pragma: no cover
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> TemplateResponse:
        context = {
            **self.admin_site.each_context(request),
            "title": "要素式转换",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
        }
        return TemplateResponse(request, "admin/doc_convert/workbench.html", context)

    def has_add_permission(self, request: HttpRequest) -> bool:  # pragma: no cover
        return False

    def has_change_permission(self, request: HttpRequest, obj: DocConvertTool | None = None) -> bool:  # pragma: no cover
        return False

    def has_delete_permission(self, request: HttpRequest, obj: DocConvertTool | None = None) -> bool:  # pragma: no cover
        return False

    def has_view_permission(self, request: HttpRequest, obj: DocConvertTool | None = None) -> bool:
        """插件未安装时禁用视图权限，Django 自动重定向到 app index。"""
        return _has_doc_convert_plugin()

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:  # pragma: no cover
        return {"view": True}
