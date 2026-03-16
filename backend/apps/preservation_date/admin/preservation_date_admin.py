"""Preservation date tool admin."""

from __future__ import annotations

import logging
from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.template.response import TemplateResponse

from apps.preservation_date.models import PreservationDateTool

logger = logging.getLogger("apps.preservation_date")


@admin.register(PreservationDateTool)
class PreservationDateAdmin(admin.ModelAdmin):
    """Admin entry for preservation date recognition test page."""

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> TemplateResponse:
        context = {
            "title": "财产保全日期识别测试",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "site_header": self.admin_site.site_header,
            "site_title": self.admin_site.site_title,
        }
        return TemplateResponse(
            request,
            "admin/preservation_date/preservation_date_test.html",
            context,
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
