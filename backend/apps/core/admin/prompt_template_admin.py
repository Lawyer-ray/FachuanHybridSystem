"""
Prompt 模板 Admin

提供 Django Admin 界面来管理 Prompt 模板,支持模板编辑、变量管理和预览功能.
"""

import json
import logging
from typing import Any, ClassVar

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html

from apps.core.models import PromptTemplate

logger = logging.getLogger("apps.core.admin.prompt_template")


def _get_prompt_service() -> None:
    """工厂函数:获取 PromptTemplateService 实例"""
    from apps.core.services import PromptTemplateService

    return PromptTemplateService()


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    """Prompt 模板 Admin"""

    list_display: ClassVar = [
        "title",
        "name",
        "category_display",
        "variables_display",
        "is_active",
        "version",
        "updated_at",
    ]
    list_filter: ClassVar = ["category", "is_active", "created_at"]
    search_fields: ClassVar = ["name", "title", "description"]
    list_editable: ClassVar = ["is_active"]
    ordering: ClassVar = ["category", "name"]

    fieldsets: tuple[Any, ...] = (
        ("基本信息", {"fields": ("name", "title", "category", "description", "version")}),
        ("模板内容", {"fields": ("template", "variables"), "classes": ("wide",)}),
        ("设置", {"fields": ("is_active",), "classes": ("collapse",)}),
        ("时间信息", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    readonly_fields: ClassVar = ["created_at", "updated_at"]

    def category_display(self, obj) -> None:
        """显示分类标签"""
        colors = {
            "litigation": "#e91e63",
            "contract": "#2196f3",
            "document": "#ff9800",
            "analysis": "#9c27b0",
            "general": "#607d8b",
        }
        color = colors.get(obj.category, "#607d8b")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 12px;">{}</span>',
            color,
            obj.category.title(),
        )

    category_display.short_description = "分类"
    category_display.admin_order_field = "category"

    def variables_display(self, obj) -> None:
        """显示变量列表"""
        if not obj.variables:
            return format_html('<span style="color: #999;">{}</span>', "无变量")

        variables_html = []
        for var in obj.variables[:3]:  # 只显示前3个变量
            variables_html.append(
                format_html(
                    '<code style="background: #f5f5f5; padding: 1px 4px; border-radius: 2px;">{{{}}}</code>',
                    var,
                )
            )

        if len(obj.variables) > 3:
            variables_html.append(f"... (+{len(obj.variables) - 3})")

        return format_html(" ".join(["{}"] * len(variables_html)), *variables_html)

    variables_display.short_description = "变量"

    def get_urls(self) -> None:
        """添加自定义 URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:object_id>/preview/",
                self.admin_site.admin_view(self.preview_template_view),
                name="core_prompttemplate_preview",
            ),
            path(
                "<int:object_id>/test/",
                self.admin_site.admin_view(self.test_template_view),
                name="core_prompttemplate_test",
            ),
            path(
                "sync-from-code/",
                self.admin_site.admin_view(self.sync_from_code_view),
                name="core_prompttemplate_sync",
            ),
        ]
        return custom_urls + urls

    def preview_template_view(self, request, object_id) -> None:
        """预览模板"""
        try:
            template = PromptTemplate.objects.get(id=object_id)

            if request.method == "POST":
                # 获取变量值
                variables = {}
                for var in template.variables:
                    variables[var] = request.POST.get(var, f"[{var}]")

                # 渲染模板
                prompt_service = _get_prompt_service()
                rendered = prompt_service.render_template(template.name, **variables)

                return JsonResponse({"success": True, "rendered": rendered})

            # GET 请求显示预览页面
            context = {
                "template": template,
                "title": f"预览模板: {template.title}",
                "opts": self.model._meta,
            }
            return render(request, "admin/core/prompttemplate/preview.html", context)

        except PromptTemplate.DoesNotExist:
            messages.error(request, "模板不存在")
            return self.changelist_view(request)
        except Exception as e:
            logger.exception(
                "预览模板失败",
                extra={"prompt_template_id": object_id, "error": str(e)},
            )
            return JsonResponse({"success": False, "error": str(e)})

    def test_template_view(self, request, object_id) -> None:
        """测试模板(调用 LLM)"""
        try:
            template = PromptTemplate.objects.get(id=object_id)

            if request.method == "POST":
                # 获取变量值
                variables = {}
                for var in template.variables:
                    variables[var] = request.POST.get(var, "")

                # 调用 LLM 服务测试
                from apps.core.interfaces import ServiceLocator

                llm_service = ServiceLocator.get_llm_service()

                # 渲染并调用
                prompt_service = _get_prompt_service()
                rendered = prompt_service.render_template(template.name, **variables)

                response = llm_service.complete(rendered, temperature=0.3)

                return JsonResponse(
                    {
                        "success": True,
                        "rendered": rendered,
                        "response": response.content,
                        "tokens": response.total_tokens,
                        "duration": response.duration_ms,
                    }
                )

            # GET 请求显示测试页面
            context = {
                "template": template,
                "title": f"测试模板: {template.title}",
                "opts": self.model._meta,
            }
            return render(request, "admin/core/prompttemplate/test.html", context)

        except PromptTemplate.DoesNotExist:
            messages.error(request, "模板不存在")
            return self.changelist_view(request)
        except Exception as e:
            logger.exception(
                "测试模板失败",
                extra={"prompt_template_id": object_id, "error": str(e)},
            )
            return JsonResponse({"success": False, "error": str(e)})

    def sync_from_code_view(self, request) -> None:
        """从代码同步模板"""
        try:
            prompt_service = _get_prompt_service()
            synced_count = prompt_service.sync_templates_from_code()

            messages.success(request, f"成功同步 {synced_count} 个模板")
        except Exception as e:
            logger.exception("从代码同步模板失败", extra={"error": str(e)})
            messages.error(request, f"同步失败: {e!s}")

        return self.changelist_view(request)

    def save_model(self, request, obj, form, change) -> None:
        """保存模型时验证模板"""
        try:
            # 使用 Service 层验证模板
            prompt_service = _get_prompt_service()
            validation = prompt_service.validate_template_syntax(obj.template, obj.variables)

            if not validation["valid"]:
                error_msg = "; ".join(validation["errors"])
                messages.error(request, f"模板验证失败: {error_msg}")
                raise ValidationError(error_msg)

            super().save_model(request, obj, form, change)

            # 同步到 PromptManager
            prompt_service.sync_template_to_manager(obj)

            messages.success(request, "模板保存成功并已同步到系统")
        except ValidationError:
            raise
        except Exception as e:
            messages.error(request, f"保存失败: {e!s}")
            raise ValidationError(str(e)) from e

    class Media:
        css: ClassVar = {"all": ("admin/css/prompt_template.css",)}
        js: tuple[Any, ...] = ("admin/js/prompt_template.js",)
