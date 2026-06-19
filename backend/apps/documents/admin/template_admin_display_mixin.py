"""文书模板 Admin 显示方法和 Action Mixin。"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib import admin
from django.utils.html import format_html

from apps.documents.models import (
    DocumentCaseStage,
    DocumentTemplate,
)

logger = logging.getLogger(__name__)


def _get_template_service() -> Any:
    """工厂函数获取模板服务"""
    from apps.documents.services.template.template_service import DocumentTemplateService

    return DocumentTemplateService()


def _get_admin_service() -> Any:
    """工厂函数获取Admin服务"""
    from apps.documents.services.template.document_template.admin_service import DocumentTemplateAdminService

    return DocumentTemplateAdminService()


class TemplateAdminDisplayMixin:
    """文书模板 Admin 显示方法和批量操作 Mixin。"""

    # ── Display methods ─────────────────────────────────────────────

    @admin.display(description="模板类型")
    def template_type_display(self, obj: DocumentTemplate) -> str:  # pragma: no cover
        """显示模板类型"""
        return obj.template_type_display

    @admin.display(description="合同类型")
    def contract_types_display(self, obj: DocumentTemplate) -> str:  # pragma: no cover
        """显示合同类型"""
        return obj.contract_types_display

    @admin.display(description="案件类型")
    def case_types_display(self, obj: DocumentTemplate) -> str:  # pragma: no cover
        """显示案件类型"""
        return obj.case_types_display

    @admin.display(description="案件阶段")
    def case_stage_display(self, obj: DocumentTemplate) -> str:  # pragma: no cover
        """显示案件阶段"""
        stages = obj.case_stages or []
        if not stages:
            return "-"
        stage_label = dict(DocumentCaseStage.choices).get(stages[0], stages[0])
        return str(stage_label)

    @admin.display(description="当前文件")
    def current_file_display(self, obj: DocumentTemplate) -> Any:  # pragma: no cover
        """显示当前文件(只读,不可点击)"""
        if not obj.pk:
            return "新建模板,请上传文件"
        if obj.file:
            absolute_path = obj.file.path if hasattr(obj.file, "path") else str(obj.file)
            return format_html('<span style="color: #2e7d32;" title="{}">📄 {}</span>', absolute_path, obj.file.name)
        elif obj.file_path:
            return format_html(
                '<span style="color: #1565c0;" title="{}">📁 {}</span>', obj.absolute_file_path, obj.file_path
            )
        return format_html('<span style="color: #c62828;">{}</span>', "⚠️ 未设置文件")

    @admin.display(description="替换词预览")
    def placeholder_preview(self, obj: DocumentTemplate) -> Any:  # pragma: no cover
        """渲染替换词预览容器（由前端 JS 动态填充）"""
        from django.utils.safestring import mark_safe

        return mark_safe(
            '<div id="placeholder-preview">'
            '<div class="preview-empty">选择或上传文件后，自动检测模板中的替换词</div>'
            "</div>"
            '<p class="placeholder-preview-hint">点击替换词可复制到剪贴板。仅在保存模板后，替换词状态才会被持久记录。</p>'
        )

    @admin.display(description="文件位置")
    def file_location_display(self, obj: DocumentTemplate) -> Any:  # pragma: no cover
        """显示文件位置,可点击下载"""
        from django.urls import reverse

        if obj.file:
            download_url = reverse("admin:documents_documenttemplate_download", args=[obj.pk])
            absolute_path = obj.file.path if hasattr(obj.file, "path") else str(obj.file)
            return format_html(
                '<a href="{}" title="点击下载 | 绝对路径: {}" target="_blank">📄 {}</a>',
                download_url,
                absolute_path,
                obj.file.name,
            )
        elif obj.file_path:
            download_url = reverse("admin:documents_documenttemplate_download", args=[obj.pk])
            return format_html(
                '<a href="{}" title="点击下载 | 绝对路径: {}" target="_blank">📁 {}</a>',
                download_url,
                obj.absolute_file_path,
                obj.file_path,
            )
        return format_html('<span style="color: #999;">{}</span>', "未设置")

    @admin.display(description="占位符")
    def placeholder_count_display(self, obj: DocumentTemplate) -> Any:  # pragma: no cover
        """显示占位符数量"""
        try:
            service = _get_template_service()
            placeholders = service.extract_placeholders(obj)
            undefined = service.get_undefined_placeholders(obj)

            all_placeholders_text = ", ".join(placeholders) if placeholders else "无占位符"

            if undefined:
                undefined_names = ", ".join(undefined[:3])
                if len(undefined) > 3:
                    undefined_names += f" 等{len(undefined)}个"

                return format_html(
                    '<span style="color: #e65100;" title="所有占位符: {} | 未定义占位符: {}">'
                    "{} ({}个未定义: {})</span>",
                    all_placeholders_text,
                    ", ".join(undefined),
                    len(placeholders),
                    len(undefined),
                    undefined_names,
                )
            else:
                return format_html('<span title="所有占位符: {}">{}</span>', all_placeholders_text, len(placeholders))
        except Exception as e:
            logger.error("提取占位符失败 - 模板ID: %s, 错误: %s", obj.id, e, exc_info=True)
            return format_html('<span style="color: #c62828;" title="{}">错误</span>', str(e))

    @admin.display(description="占位符列表")
    def placeholders_display(self, obj: DocumentTemplate) -> Any:  # pragma: no cover
        """显示占位符列表"""
        if not obj.pk:
            return "保存后可查看占位符"

        try:
            service = _get_template_service()
            placeholders = service.extract_placeholders(obj)
            undefined = set(service.get_undefined_placeholders(obj))

            admin_service = _get_admin_service()
            return admin_service.render_placeholders_table(placeholders, undefined)
        except Exception as e:
            logger.exception("操作失败")
            return format_html('<span style="color: #c62828;">提取失败: {}</span>', str(e))

    @admin.display(description="未定义占位符")
    def undefined_placeholders_display(self, obj: DocumentTemplate) -> Any:  # pragma: no cover
        """显示未定义的占位符(高亮警告)"""
        if not obj.pk:
            return "保存后可查看"

        try:
            service = _get_template_service()
            undefined = service.get_undefined_placeholders(obj)

            admin_service = _get_admin_service()
            return admin_service.render_undefined_placeholders_warning(undefined)
        except Exception as e:
            logger.exception("操作失败")
            return format_html('<span style="color: #c62828;">检查失败: {}</span>', str(e))

    # ── Admin actions ───────────────────────────────────────────────

    def activate_templates(self, request: Any, queryset: Any) -> None:  # pragma: no cover
        """批量启用模板"""
        service = _get_admin_service()
        updated: int = service.batch_activate(queryset)
        self.message_user(request, "已启用 %(count)d 个模板" % {"count": updated})  # type: ignore[attr-defined]

    def deactivate_templates(self, request: Any, queryset: Any) -> None:  # pragma: no cover
        """批量禁用模板"""
        service = _get_admin_service()
        updated: int = service.batch_deactivate(queryset)
        self.message_user(request, "已禁用 %(count)d 个模板" % {"count": updated})  # type: ignore[attr-defined]

    @admin.action(description="刷新占位符信息")
    def refresh_placeholders(self, request: Any, queryset: Any) -> None:  # pragma: no cover
        """刷新占位符信息(触发重新解析)"""
        count = queryset.count()
        self.message_user(request, "已刷新 %(count)d 个模板的占位符信息" % {"count": count})  # type: ignore[attr-defined]

    @admin.action(description="复制选中的模板")
    def duplicate_templates(self, request: Any, queryset: Any) -> None:  # pragma: no cover
        """批量复制文书模板"""
        admin_service = _get_admin_service()
        count = admin_service.batch_duplicate_templates(queryset)
        self.message_user(request, "已复制 %(count)d 个模板" % {"count": count})  # type: ignore[attr-defined]
