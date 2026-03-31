"""doc_convert Admin - 传统文书转要素式文书测试界面。"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.template.response import TemplateResponse

from apps.doc_convert.models import DocConvertTool


@admin.register(DocConvertTool)
class DocConvertToolAdmin(admin.ModelAdmin[DocConvertTool]):
    """传统文书转换工作台 Admin。"""

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> TemplateResponse:
        context = {
            **self.admin_site.each_context(request),
            "title": "传统文书转要素式文书",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
        }
        return TemplateResponse(request, "admin/doc_convert/workbench.html", context)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: DocConvertTool | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: DocConvertTool | None = None) -> bool:
        return False

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        return {"view": True}
