"""
外部模板 Admin 配置

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 8.4, 9.5, 9.6, 13.4
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django import forms
from django.contrib import admin
from django.core.validators import FileExtensionValidator
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.documents.models import ExternalTemplate, ExternalTemplateFieldMapping

logger: logging.Logger = logging.getLogger(__name__)

_SOURCE_NAME_WIDGET = forms.TextInput(
    attrs={
        "class": "vTextField js-court-autocomplete",
        "placeholder": "请输入法院或机构名称...",
        "autocomplete": "off",
    }
)


class ExternalTemplateAddForm(forms.ModelForm[ExternalTemplate]):  # pragma: no cover
    """新增外部模板表单"""

    docx_file = forms.FileField(
        label="模板文件 (.docx)",
        validators=[FileExtensionValidator(["docx"])],
        help_text="仅支持 .docx 格式，最大 20MB",
    )

    class Meta:  # pragma: no cover
        model = ExternalTemplate
        fields = ("name", "source_name")
        widgets: ClassVar[dict[str, Any]] = {
            "source_name": _SOURCE_NAME_WIDGET,
        }


class ExternalTemplateChangeForm(forms.ModelForm[ExternalTemplate]):  # pragma: no cover
    """编辑外部模板表单"""

    class Meta:  # pragma: no cover
        model = ExternalTemplate
        fields = ("name", "source_name", "is_active")
        widgets: ClassVar[dict[str, Any]] = {
            "source_name": _SOURCE_NAME_WIDGET,
        }


def _get_analysis_service() -> Any:
    """工厂函数获取分析服务"""
    from apps.documents.services.infrastructure.wiring import get_analysis_service

    return get_analysis_service()


def _get_filling_service() -> Any:
    """工厂函数获取填充服务"""
    from apps.documents.services.infrastructure.wiring import get_filling_service

    return get_filling_service()


class ExternalTemplateFieldMappingInline(admin.TabularInline):  # pragma: no cover
    """字段映射 Inline（只读展示，由 LLM 分析自动生成）"""

    model = ExternalTemplateFieldMapping
    extra: int = 0
    fields: tuple[str, ...] = (  # type: ignore[misc]
        "sort_order",
        "position_description",
        "semantic_label",
        "fill_type",
    )
    readonly_fields: tuple[str, ...] = (  # type: ignore[misc]
        "position_description",
        "semantic_label",
        "fill_type",
    )


@admin.register(ExternalTemplate)
class ExternalTemplateAdmin(admin.ModelAdmin):  # pragma: no cover
    """
    外部模板管理

    列表页展示模板信息, 详情页包含字段映射 Inline 和操作按钮.
    通过工厂函数获取 Service, 不直接实例化.
    """

    change_form_template: str = "admin/documents/external_template/change_form.html"  # type: ignore[misc]

    list_display: ClassVar[list[str]] = [  # type: ignore[misc,assignment]
        "name",
        "source_name",
        "status",
        "version",
        "is_active",
        "updated_at",
    ]
    list_filter: ClassVar[list[str]] = [  # type: ignore[assignment]
        "status",
        "is_active",
    ]
    search_fields: ClassVar[list[str]] = [
        "name",
        "source_name",
    ]
    inlines: ClassVar[list[type[admin.TabularInline]]] = [  # type: ignore[assignment]
        ExternalTemplateFieldMappingInline,
    ]

    # 新增时显示的字段（含文件上传）
    add_fields: ClassVar[tuple[str, ...]] = (
        "name",
        "source_name",
        "docx_file",
    )

    # 编辑时显示的字段
    change_fields: ClassVar[tuple[str, ...]] = (
        "name",
        "source_name",
        "status",
        "version",
        "is_active",
    )

    # 编辑时只读字段
    change_readonly_fields: ClassVar[tuple[str, ...]] = (
        "original_filename",
        "file_size_display",
        "uploaded_by_display",
        # "law_firm_display",  # 移除所属律所字段
        "version",
        "status",
        "created_at",
        "updated_at",
    )

    def get_form(  # pragma: no cover
        self,
        request: HttpRequest,
        obj: ExternalTemplate | None = None,
        change: bool = False,
        **kwargs: Any,
    ) -> type[forms.ModelForm[ExternalTemplate]]:
        if obj is None:
            kwargs["form"] = ExternalTemplateAddForm
        else:
            kwargs["form"] = ExternalTemplateChangeForm
        return super().get_form(request, obj, change, **kwargs)

    def get_fields(  # pragma: no cover
        self,
        request: HttpRequest,
        obj: ExternalTemplate | None = None,
    ) -> tuple[str, ...]:
        if obj is None:
            return self.add_fields
        return self.change_fields + self.change_readonly_fields

    def get_readonly_fields(  # pragma: no cover
        self,
        request: HttpRequest,
        obj: ExternalTemplate | None = None,
    ) -> tuple[str, ...]:
        if obj is None:
            return ()
        return self.change_readonly_fields

    @admin.display(description="原始文件名")
    def original_filename(self, obj: ExternalTemplate) -> str:  # pragma: no cover
        return obj.original_filename

    @admin.display(description="文件大小")
    def file_size_display(self, obj: ExternalTemplate) -> str:  # pragma: no cover
        size = obj.file_size
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / 1024 / 1024:.1f} MB"

    @admin.display(description="上传者")
    def uploaded_by_display(self, obj: ExternalTemplate) -> str:  # pragma: no cover
        if obj.uploaded_by:
            return str(obj.uploaded_by.real_name or obj.uploaded_by.username)
        return "-"

    @admin.display(description="所属律所")
    def law_firm_display(self, obj: ExternalTemplate) -> str:  # pragma: no cover
        return str(obj.law_firm.name) if obj.law_firm_id else "-"

    def save_model(  # pragma: no cover
        self,
        request: HttpRequest,
        obj: ExternalTemplate,
        form: Any,
        change: bool,
    ) -> None:
        """新增时通过 AnalysisService.upload_template 处理文件上传"""
        if not change:
            docx_file = form.cleaned_data.get("docx_file")
            if docx_file:
                service = _get_analysis_service()
                template = service.upload_template(
                    file=docx_file,
                    name=form.cleaned_data["name"],
                    source_name=form.cleaned_data.get("source_name", ""),
                    uploaded_by=request.user,
                )
                # 用 service 创建的对象替换 obj，避免重复 save
                obj.pk = template.pk
                obj.__dict__.update(template.__dict__)
                logger.info("模板上传成功: id=%d, name=%s", template.pk, template.name)
                return
        super().save_model(request, obj, form, change)

    def get_urls(self) -> list[Any]:  # pragma: no cover
        """注册自定义 URL: 分析、填充操作页面"""
        from django.urls import path

        urls = super().get_urls()
        custom_urls: list[Any] = [
            path(
                "analyze/<int:template_id>/",
                self.admin_site.admin_view(self.analyze_view),
                name="documents_externaltemplate_analyze",
            ),
            path(
                "fill-action/<int:template_id>/",
                self.admin_site.admin_view(self.fill_action_view),
                name="documents_externaltemplate_fill_action",
            ),
            path(
                "mapping-editor/<int:template_id>/",
                self.admin_site.admin_view(self.mapping_editor_view),
                name="documents_externaltemplate_mapping_editor",
            ),
        ]
        return custom_urls + urls

    def analyze_view(self, request: HttpRequest, template_id: int) -> HttpResponse:  # pragma: no cover
        """触发 LLM 分析并重定向回详情页"""
        from apps.documents.models.external_template import ExternalTemplateFieldMapping

        service = _get_analysis_service()
        try:
            has_mappings = ExternalTemplateFieldMapping.objects.filter(template_id=template_id).exists()
            if has_mappings:
                service.retry_analysis(template_id)
            else:
                service.analyze_template(template_id)
            self.message_user(request, "模板分析已完成")
        except Exception:
            logger.exception("模板分析失败: template_id=%s", template_id)
            self.message_user(
                request,
                "模板分析失败，请查看日志",
                level="error",
            )
        change_url = reverse(
            "admin:documents_externaltemplate_change",
            args=[template_id],
        )
        return HttpResponseRedirect(change_url)

    def fill_action_view(self, request: HttpRequest, template_id: int) -> HttpResponse:  # pragma: no cover
        """填充操作页面"""
        template_obj = self.get_object(request, str(template_id))
        if template_obj is None:
            from django.http import Http404

            raise Http404("模板不存在")

        service = _get_filling_service()
        custom_fields: list[dict[str, Any]] = service.get_custom_fields(template_id)

        import json as _json

        context: dict[str, Any] = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "template_obj": template_obj,
            "custom_fields_json": _json.dumps(custom_fields, ensure_ascii=False),
            "title": "填充操作 - %(name)s" % {"name": template_obj.name},
        }
        return TemplateResponse(
            request,
            "admin/documents/external_template/fill_action.html",
            context,
        )

    def mapping_editor_view(self, request: HttpRequest, template_id: int) -> HttpResponse:  # pragma: no cover
        """映射可视化编辑页面"""
        template_obj = self.get_object(request, str(template_id))
        if template_obj is None:
            from django.http import Http404

            raise Http404("模板不存在")

        context: dict[str, Any] = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "template_obj": template_obj,
            "title": "映射编辑 - %(name)s" % {"name": template_obj.name},
        }
        return TemplateResponse(
            request,
            "admin/documents/external_template/mapping_editor.html",
            context,
        )
