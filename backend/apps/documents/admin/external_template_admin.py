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
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.documents.models import (
    ExternalTemplate,
    ExternalTemplateFieldMapping,
)

logger: logging.Logger = logging.getLogger(__name__)


class ExternalTemplateAddForm(forms.ModelForm[ExternalTemplate]):
    """新增外部模板表单：包含文件上传字段"""

    docx_file = forms.FileField(
        label=_("模板文件 (.docx)"),
        validators=[FileExtensionValidator(["docx"])],
        help_text=_("仅支持 .docx 格式，最大 20MB"),
    )

    class Meta:
        model = ExternalTemplate
        fields = ("name", "category", "source_type", "court", "organization_name")


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

    # 新增时显示的字段（含文件上传）
    add_fields: ClassVar[tuple[str, ...]] = (
        "name",
        "category",
        "source_type",
        "court",
        "organization_name",
        "docx_file",
    )

    # 编辑时显示的字段
    change_fields: ClassVar[tuple[str, ...]] = (
        "name",
        "category",
        "source_type",
        "court",
        "organization_name",
        "status",
        "version",
        "is_active",
    )

    # 编辑时只读字段
    change_readonly_fields: ClassVar[tuple[str, ...]] = (
        "original_filename",
        "file_size_display",
        "uploaded_by_display",
        "law_firm_display",
        "version",
        "status",
        "created_at",
        "updated_at",
    )

    def get_form(
        self,
        request: HttpRequest,
        obj: ExternalTemplate | None = None,
        change: bool = False,
        **kwargs: Any,
    ) -> type[forms.ModelForm[ExternalTemplate]]:
        if obj is None:
            kwargs["form"] = ExternalTemplateAddForm
        return super().get_form(request, obj, change, **kwargs)  # type: ignore[return-value]

    def get_fields(
        self,
        request: HttpRequest,
        obj: ExternalTemplate | None = None,
    ) -> tuple[str, ...]:
        if obj is None:
            return self.add_fields
        return self.change_fields + self.change_readonly_fields

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: ExternalTemplate | None = None,
    ) -> tuple[str, ...]:
        if obj is None:
            return ()
        return self.change_readonly_fields

    @admin.display(description=_("原始文件名"))
    def original_filename(self, obj: ExternalTemplate) -> str:
        return obj.original_filename

    @admin.display(description=_("文件大小"))
    def file_size_display(self, obj: ExternalTemplate) -> str:
        size = obj.file_size
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / 1024 / 1024:.1f} MB"

    @admin.display(description=_("上传者"))
    def uploaded_by_display(self, obj: ExternalTemplate) -> str:
        if obj.uploaded_by:
            return str(obj.uploaded_by.real_name or obj.uploaded_by.username)
        return "-"

    @admin.display(description=_("所属律所"))
    def law_firm_display(self, obj: ExternalTemplate) -> str:
        return str(obj.law_firm.name) if obj.law_firm_id else "-"

    def save_model(
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
                    category=form.cleaned_data["category"],
                    source_type=form.cleaned_data["source_type"],
                    court_id=form.cleaned_data["court"].pk if form.cleaned_data.get("court") else None,
                    organization_name=form.cleaned_data.get("organization_name", ""),
                    uploaded_by=request.user,
                )
                # 用 service 创建的对象替换 obj，避免重复 save
                obj.pk = template.pk
                obj.__dict__.update(template.__dict__)
                logger.info("模板上传成功: id=%d, name=%s", template.pk, template.name)
                return
        super().save_model(request, obj, form, change)

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
