"""
外部模板 Admin 配置

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 8.4, 9.5, 9.6, 13.4
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.documents.models import (
    ExternalTemplate,
    ExternalTemplateFieldMapping,
)

logger: logging.Logger = logging.getLogger(__name__)


def _get_analysis_service() -> Any:
    """工厂函数获取分析服务"""
    from apps.documents.services.wiring import get_analysis_service

    return get_analysis_service()


def _get_filling_service() -> Any:
    """工厂函数获取填充服务"""
    from apps.documents.services.wiring import get_filling_service

    return get_filling_service()


class ExternalTemplateFieldMappingInline(admin.TabularInline):  # type: ignore[type-arg]
    """字段映射 Inline"""

    model = ExternalTemplateFieldMapping
    extra: int = 0
    fields: tuple[str, ...] = (
        "sort_order",
        "position_description",
        "semantic_label",
        "placeholder_key",
        "fill_type",
        "is_confirmed",
    )


@admin.register(ExternalTemplate)
class ExternalTemplateAdmin(admin.ModelAdmin[ExternalTemplate]):  # type: ignore[type-arg]
    """
    外部模板管理

    列表页展示模板信息, 详情页包含字段映射 Inline 和操作按钮.
    通过工厂函数获取 Service, 不直接实例化.
    """

    change_form_template: str = "admin/documents/external_template/change_form.html"

    list_display: ClassVar[list[str]] = [
        "name",
        "category",
        "source_display",
        "status",
        "version",
        "is_active",
        "updated_at",
    ]
    list_filter: ClassVar[list[str]] = [
        "status",
        "category",
        "source_type",
        "is_active",
    ]
    search_fields: ClassVar[list[str]] = [
        "name",
        "organization_name",
        "court__name",
    ]
    inlines: ClassVar[list[type[admin.TabularInline]]] = [  # type: ignore[type-arg]
        ExternalTemplateFieldMappingInline,
    ]

    def get_urls(self) -> list[Any]:
        """注册自定义 URL: 分析、确认、填充操作页面"""
        from django.urls import path

        urls = super().get_urls()
        custom_urls: list[Any] = [
            path(
                "analyze/<int:template_id>/",
                self.admin_site.admin_view(self.analyze_view),
                name="documents_externaltemplate_analyze",
            ),
            path(
                "confirm/<int:template_id>/",
                self.admin_site.admin_view(self.confirm_view),
                name="documents_externaltemplate_confirm",
            ),
            path(
                "fill-action/<int:template_id>/",
                self.admin_site.admin_view(self.fill_action_view),
                name="documents_externaltemplate_fill_action",
            ),
        ]
        return custom_urls + urls

    @admin.display(description=_("来源"))
    def source_display(self, obj: ExternalTemplate) -> str:
        """来源显示: 法院名称或机构名称"""
        if obj.source_type == "court" and obj.court:
            return str(obj.court.name)
        if obj.organization_name:
            return obj.organization_name
        return "-"

    def analyze_view(
        self, request: HttpRequest, template_id: int
    ) -> HttpResponse:
        """触发 LLM 分析并重定向回详情页"""
        service = _get_analysis_service()
        try:
            service.analyze_template(template_id)
            self.message_user(request, gettext("模板分析已完成"))
        except Exception:
            logger.exception("模板分析失败: template_id=%s", template_id)
            self.message_user(
                request,
                gettext("模板分析失败，请查看日志"),
                level="error",
            )
        change_url = reverse(
            "admin:documents_externaltemplate_change",
            args=[template_id],
        )
        return HttpResponseRedirect(change_url)

    def confirm_view(
        self, request: HttpRequest, template_id: int
    ) -> HttpResponse:
        """确认映射并重定向回详情页"""
        service = _get_analysis_service()
        try:
            service.confirm_mappings(template_id)
            self.message_user(request, gettext("映射已确认"))
        except Exception:
            logger.exception("映射确认失败: template_id=%s", template_id)
            self.message_user(
                request,
                gettext("映射确认失败，请查看日志"),
                level="error",
            )
        change_url = reverse(
            "admin:documents_externaltemplate_change",
            args=[template_id],
        )
        return HttpResponseRedirect(change_url)

    def fill_action_view(
        self, request: HttpRequest, template_id: int
    ) -> HttpResponse:
        """填充操作页面"""
        template_obj = self.get_object(request, str(template_id))
        if template_obj is None:
            from django.http import Http404

            raise Http404(gettext("模板不存在"))

        service = _get_filling_service()
        custom_fields: list[dict[str, Any]] = service.get_custom_fields(
            template_id
        )

        context: dict[str, Any] = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "template_obj": template_obj,
            "custom_fields": custom_fields,
            "title": gettext("填充操作 - %(name)s") % {"name": template_obj.name},
        }
        return TemplateResponse(
            request,
            "admin/documents/external_template/fill_action.html",
            context,
        )
