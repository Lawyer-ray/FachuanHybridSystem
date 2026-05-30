"""智能填充 Admin 页面"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from django import forms
from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.documents.models.smart_fill import SmartFillProxy

logger = logging.getLogger(__name__)

# 临时文件存储目录
SMART_FILL_TEMP_DIR = Path(settings.MEDIA_ROOT) / "temp" / "smart_fill"

# 最大文件大小 20MB
MAX_FILE_SIZE = 20 * 1024 * 1024


class SmartFillForm(forms.Form):
    """智能填充表单"""

    template_file = forms.FileField(
        label=_("模板文件 (.docx)"),
        help_text=_("仅支持 .docx 格式，最大 20MB"),
    )
    user_input = forms.CharField(
        label=_("自然语言描述"),
        widget=forms.Textarea(attrs={"rows": 4, "class": "vLargeTextField"}),
        help_text=_("描述你想要生成的文书内容，如：委托人是张三，案件编号是(2026)京01民初123号"),
    )


def _get_smart_fill_service() -> Any:
    """工厂函数获取智能填充服务"""
    from apps.documents.services.infrastructure.wiring import get_smart_fill_service

    return get_smart_fill_service()


@admin.register(SmartFillProxy)
class SmartFillAdmin(admin.ModelAdmin):
    """智能填充 Admin 页面（不绑定 Model）"""

    change_list_template = "admin/documents/smart_fill/change_list.html"

    def get_queryset(self, request: HttpRequest) -> Any:
        """返回空 QuerySet，此页面不展示模型数据"""
        from django.db.models import QuerySet

        return SmartFillProxy.objects.none()

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def get_urls(self) -> list[Any]:
        """注册自定义 URL"""
        from django.urls import path

        custom_urls: list[Any] = [
            path(
                "",
                self.admin_site.admin_view(self.changelist_view),
                name="documents_smartfill_changelist",
            ),
            path(
                "preview/",
                self.admin_site.admin_view(self.preview_view),
                name="documents_smartfill_preview",
            ),
            path(
                "download/<str:task_id>/",
                self.admin_site.admin_view(self.download_view),
                name="documents_smartfill_download",
            ),
        ]
        return custom_urls

    def changelist_view(self, request: HttpRequest) -> HttpResponse:
        """主页面：显示表单"""
        form = SmartFillForm()
        context: dict[str, Any] = {
            **self.admin_site.each_context(request),
            "form": form,
            "show_result": False,
            "title": _("智能模板填充"),
            "opts": self.model._meta if self.model else None,
        }
        return TemplateResponse(request, self.change_list_template, context)

    def preview_view(self, request: HttpRequest) -> HttpResponse:
        """预览映射：调用 LLM 生成占位符映射"""
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:documents_smartfill_changelist"))

        form = SmartFillForm(request.POST, request.FILES)
        if not form.is_valid():
            context: dict[str, Any] = {
                **self.admin_site.each_context(request),
                "form": form,
                "show_result": False,
                "title": _("智能模板填充"),
                "opts": self.model._meta if self.model else None,
            }
            return TemplateResponse(request, self.change_list_template, context)

        template_file = request.FILES["template_file"]
        user_input = form.cleaned_data["user_input"]

        # 校验文件大小
        if template_file.size and template_file.size > MAX_FILE_SIZE:
            form.add_error("template_file", gettext("文件大小超出限制（最大 20MB）"))
            context = {
                **self.admin_site.each_context(request),
                "form": form,
                "show_result": False,
                "title": _("智能模板填充"),
                "opts": self.model._meta if self.model else None,
            }
            return TemplateResponse(request, self.change_list_template, context)

        # 生成唯一任务 ID
        task_id = str(uuid.uuid4())
        task_dir = SMART_FILL_TEMP_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        # 保存模板文件
        template_path = task_dir / "template.docx"
        try:
            with template_path.open("wb") as f:
                for chunk in template_file.chunks():
                    f.write(chunk)
        except Exception:
            logger.exception("保存模板文件失败")
            shutil.rmtree(task_dir, ignore_errors=True)
            form.add_error(None, gettext("保存模板文件失败"))
            context = {
                **self.admin_site.each_context(request),
                "form": form,
                "show_result": False,
                "title": _("智能模板填充"),
                "opts": self.model._meta if self.model else None,
            }
            return TemplateResponse(request, self.change_list_template, context)

        try:
            # 调用 SmartFillService.preview()
            service = _get_smart_fill_service()
            result = service.preview(str(template_path), user_input)

            if result.error:
                shutil.rmtree(task_dir, ignore_errors=True)
                form.add_error(None, result.error)
                context = {
                    **self.admin_site.each_context(request),
                    "form": form,
                    "show_result": False,
                    "title": _("智能模板填充"),
                    "opts": self.model._meta if self.model else None,
                }
                return TemplateResponse(request, self.change_list_template, context)

            # 存储映射结果到文件
            mapping_path = task_dir / "mapping.json"
            mapping_data = {
                "placeholders": [{"key": p.key, "value": p.value, "source": p.source} for p in result.placeholders],
                "user_input": user_input,
            }
            mapping_path.write_text(json.dumps(mapping_data, ensure_ascii=False), encoding="utf-8")

            context = {
                **self.admin_site.each_context(request),
                "form": form,
                "show_result": True,
                "placeholders": result.placeholders,
                "task_id": task_id,
                "title": _("智能模板填充"),
                "opts": self.model._meta if self.model else None,
            }
            return TemplateResponse(request, self.change_list_template, context)

        except Exception as e:
            logger.exception("智能填充预览失败")
            shutil.rmtree(task_dir, ignore_errors=True)
            form.add_error(None, gettext("预览失败: %(error)s") % {"error": str(e)})
            context = {
                **self.admin_site.each_context(request),
                "form": form,
                "show_result": False,
                "title": _("智能模板填充"),
                "opts": self.model._meta if self.model else None,
            }
            return TemplateResponse(request, self.change_list_template, context)

    def download_view(self, request: HttpRequest, task_id: str) -> HttpResponse:
        """生成文件下载"""
        task_dir = SMART_FILL_TEMP_DIR / task_id
        template_path = task_dir / "template.docx"
        mapping_path = task_dir / "mapping.json"

        if not template_path.exists() or not mapping_path.exists():
            return HttpResponse(
                gettext("任务不存在或已过期，请重新预览"),
                status=404,
            )

        # 读取映射结果
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        placeholders_data = mapping["placeholders"]

        # 转换为 PlaceholderResult 对象
        from apps.documents.services.smart_fill.service import PlaceholderResult

        placeholders = [
            PlaceholderResult(key=p["key"], value=p["value"], source=p["source"]) for p in placeholders_data
        ]

        try:
            # 调用 SmartFillService.render()（不再调用 LLM）
            service = _get_smart_fill_service()
            rendered_bytes = service.render(str(template_path), placeholders)
        except Exception as e:
            logger.exception("智能填充渲染失败")
            return HttpResponse(
                gettext("渲染失败: %(error)s") % {"error": str(e)},
                status=500,
            )
        finally:
            # 清理临时文件
            shutil.rmtree(task_dir, ignore_errors=True)

        # 返回文件响应
        response = HttpResponse(
            rendered_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = 'attachment; filename="smart_fill_output.docx"'
        return response
