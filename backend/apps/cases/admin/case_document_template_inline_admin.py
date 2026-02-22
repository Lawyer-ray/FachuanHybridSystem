"""
案件文件模板内联管理

在案件编辑页显示文件模板模块,支持自动匹配和手动绑定的模板显示.

Requirements: 1.1, 1.7, 3.1, 3.2, 3.3
"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from apps.cases.admin.base import BaseTabularInline
from apps.cases.models import BindingSource, CaseTemplateBinding

logger = logging.getLogger(__name__)


def _get_case_document_template_admin_service() -> Any:
    """工厂函数获取案件文件模板 Admin 服务"""
    from apps.cases.services.template.wiring import get_case_document_template_admin_service

    return get_case_document_template_admin_service()


class CaseDocumentTemplateInline(BaseTabularInline):
    """
    案件文件模板内联管理

    在案件编辑页的案件群聊模块下方显示"文件模板"模块.
    显示自动匹配和手动绑定的文件模板,支持生成文档和移除操作.

    Requirements: 1.1, 1.7, 3.1, 3.2, 3.3
    """

    model = CaseTemplateBinding
    extra: int = 0
    template: str = "admin/cases/case/case_document_template_inline.html"
    verbose_name = _("文件模板")
    verbose_name_plural = _("文件模板")

    fields = ("template_display", "binding_source_display", "actions_display")
    readonly_fields = ("template_display", "binding_source_display", "actions_display")

    ordering: tuple[Any, ...] = ("binding_source", "-created_at")  # type: ignore[misc]

    def template_display(self, obj: CaseTemplateBinding) -> str:
        """
        显示模板名称和描述

        Requirements: 1.7
        """
        if not obj or not obj.pk:
            return ""

        template = obj.template
        if not template:
            return format_html('<span style="color: #999;">{}</span>', "模板已删除")

        name = getattr(template, "name", None) or "未命名模板"
        description = getattr(template, "description", None) or ""

        if description:
            truncated_desc = description[:100] + "..." if len(description) > 100 else description
            return format_html(
                '<div class="template-info">'
                '<strong class="template-name">{}</strong>'
                '<div class="template-description" style="color: #666; font-size: 12px; margin-top: 4px;">{}</div>'
                "</div>",
                name,
                truncated_desc,
            )

        return format_html(
            '<div class="template-info"><strong class="template-name">{}</strong></div>',
            name,
        )

    template_display.short_description = _("模板")  # type: ignore[attr-defined]

    def binding_source_display(self, obj: CaseTemplateBinding) -> str:
        """
        显示绑定来源标签

        Requirements: 3.1, 3.2, 3.3
        """
        if not obj or not obj.pk:
            return ""

        binding_source = obj.binding_source

        if binding_source == BindingSource.AUTO_RECOMMENDED:
            return format_html(
                '<span class="binding-source-tag auto-recommended" '
                'style="display: inline-block; padding: 2px 8px; border-radius: 4px; '
                "background-color: #e6f7ff; color: #1890ff; font-size: 12px; "
                'border: 1px solid #91d5ff;">{}</span>',
                "自动推荐",
            )
        elif binding_source == BindingSource.MANUAL_BOUND:
            return format_html(
                '<span class="binding-source-tag manual-bound" '
                'style="display: inline-block; padding: 2px 8px; border-radius: 4px; '
                "background-color: #f6ffed; color: #52c41a; font-size: 12px; "
                'border: 1px solid #b7eb8f;">{}</span>',
                "手动添加",
            )
        else:
            return format_html(
                '<span class="binding-source-tag unknown" '
                'style="display: inline-block; padding: 2px 8px; border-radius: 4px; '
                "background-color: #f5f5f5; color: #999; font-size: 12px; "
                'border: 1px solid #d9d9d9;">{}</span>',
                "未知",
            )

    binding_source_display.short_description = _("来源")  # type: ignore[attr-defined]

    def actions_display(self, obj: CaseTemplateBinding) -> str:
        """
        显示操作按钮(生成文档、移除)

        Requirements: 3.4
        """
        if not obj or not obj.pk:
            return ""

        template = obj.template
        if not template:
            return ""

        buttons = []

        generate_btn = format_html(
            '<button type="button" class="btn-generate-document" '
            'data-template-id="{}" '
            'data-binding-id="{}" '
            'style="padding: 4px 12px; margin-right: 8px; cursor: pointer; '
            "background-color: #1890ff; color: white; border: none; border-radius: 4px; "
            'font-size: 12px;">{}</button>',
            getattr(template, "id", 0),
            obj.id,
            "生成文档",
        )
        buttons.append(generate_btn)

        if obj.binding_source == BindingSource.MANUAL_BOUND:
            remove_btn = format_html(
                '<button type="button" class="btn-remove-binding" '
                'data-binding-id="{}" '
                'style="padding: 4px 12px; cursor: pointer; '
                "background-color: #ff4d4f; color: white; border: none; border-radius: 4px; "
                'font-size: 12px;">{}</button>',
                obj.id,
                "移除",
            )
            buttons.append(remove_btn)

        return format_html_join("", "{}", [(b,) for b in buttons])

    actions_display.short_description = _("操作")  # type: ignore[attr-defined]

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
