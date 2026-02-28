"""案件材料整理 Admin"""

import logging
from typing import Any

from django.contrib import admin
from django.template.response import TemplateResponse

from apps.evidence_sorting.models import EvidenceSorting

logger = logging.getLogger("apps.evidence_sorting")


@admin.register(EvidenceSorting)
class EvidenceSortingAdmin(admin.ModelAdmin):
    """案件材料整理工具 Admin，使用虚拟模型作为入口"""

    def changelist_view(
        self, request: Any, extra_context: dict[str, Any] | None = None
    ) -> TemplateResponse:
        context: dict[str, Any] = {
            "title": "案件材料整理",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "site_header": self.admin_site.site_header,
            "site_title": self.admin_site.site_title,
        }
        return TemplateResponse(
            request,
            "admin/evidence_sorting/evidence_sorting.html",
            context,
        )

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def get_model_perms(self, request: Any) -> dict[str, bool]:
        return {"view": True}
