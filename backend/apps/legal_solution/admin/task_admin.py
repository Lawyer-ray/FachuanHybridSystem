from __future__ import annotations

import logging
from typing import Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html

from apps.core.llm.config import LLMConfig
from apps.core.llm.model_list_service import ModelListService
from apps.legal_solution.models import SectionStatus, SolutionSection, SolutionTask, SolutionTaskStatus
from apps.legal_solution.services import HtmlRenderer, PdfExporter, SolutionTaskService

logger = logging.getLogger(__name__)

WEIKE_FILTER = (
    Q(site_name__icontains="wkxx")
    | Q(site_name__iexact="wk")
    | Q(site_name__icontains="weike")
    | Q(url__icontains="wkinfo.com.cn")
)


class SolutionSectionInline(admin.TabularInline):
    model = SolutionSection
    extra = 0
    can_delete = False
    fields = ("section_type", "title", "status", "version", "adjust_button")
    readonly_fields = ("section_type", "title", "status", "version", "adjust_button")
    ordering = ("order",)

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    @admin.display(description="操作")
    def adjust_button(self, obj: SolutionSection) -> str:
        if obj.status == SectionStatus.GENERATING:
            return format_html('<span style="color:#94a3b8;">生成中...</span>')
        if obj.status not in (SectionStatus.COMPLETED, SectionStatus.FAILED):
            return "—"
        url = reverse("admin:legal_solution_solutiontask_adjust_section", args=[obj.task_id, obj.id])
        return format_html(
            '<a class="button" href="{}" style="font-size:12px;padding:3px 10px;">✏️ 调整</a>',
            url,
        )


@admin.register(SolutionTask)
class SolutionTaskAdmin(admin.ModelAdmin[SolutionTask]):
    list_display = ["id", "case_summary_short", "status", "progress", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["id", "case_summary", "keyword"]
    ordering = ["-created_at"]
    inlines = [SolutionSectionInline]

    add_fields: ClassVar = ["case_summary", "credential", "llm_model"]
    readonly_fields: ClassVar = [
        "id", "keyword", "research_task", "status", "progress", "message", "error",
        "llm_model", "q_task_id", "started_at", "finished_at", "created_at", "updated_at",
        "preview_html_field", "download_pdf_button",
    ]

    def get_fields(self, request: HttpRequest, obj: SolutionTask | None = None) -> list[str]:
        if obj is None:
            return list(self.add_fields)
        return [
            "id", "case_summary", "keyword", "credential", "research_task",
            "status", "progress", "message", "error", "llm_model",
            "preview_html_field", "download_pdf_button",
            "q_task_id", "started_at", "finished_at", "created_at", "updated_at",
        ]

    def get_readonly_fields(self, request: HttpRequest, obj: SolutionTask | None = None) -> list[str]:
        if obj is None:
            return []
        return list(self.readonly_fields) + ["case_summary", "credential"]

    def get_form(self, request: HttpRequest, obj: SolutionTask | None = None, **kwargs: Any) -> type[forms.ModelForm]:
        form = super().get_form(request, obj, **kwargs)
        if obj is not None:
            return form

        # 配置 credential 字段
        cred_field = form.base_fields.get("credential")
        if cred_field is not None:
            from apps.legal_solution.models.task import SolutionTask as _T
            cred_model = _T._meta.get_field("credential").remote_field.model
            qs = cred_model.objects.filter(WEIKE_FILTER)
            if not request.user.is_superuser:
                qs = qs.filter(lawyer__law_firm_id=getattr(request.user, "law_firm_id", None))
            cred_field.queryset = qs
            if qs.count() == 1:
                cred_field.initial = qs.first().id
                cred_field.widget = forms.HiddenInput()

        # 配置 llm_model 字段
        model_field = form.base_fields.get("llm_model")
        if model_field is not None:
            choices = self._build_model_choices()
            model_field.widget = forms.Select(choices=choices)
            model_field.initial = choices[0][0] if choices else LLMConfig.get_default_model()
            model_field.required = False

        return form

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        opts = self.model._meta
        custom = [
            path(
                "<int:task_id>/preview/",
                self.admin_site.admin_view(self.preview_view),
                name=f"{opts.app_label}_{opts.model_name}_preview",
            ),
            path(
                "<int:task_id>/pdf/",
                self.admin_site.admin_view(self.pdf_view),
                name=f"{opts.app_label}_{opts.model_name}_pdf",
            ),
            path(
                "<int:task_id>/sections/<int:section_id>/adjust/",
                self.admin_site.admin_view(self.adjust_section_view),
                name=f"{opts.app_label}_{opts.model_name}_adjust_section",
            ),
        ]
        return custom + urls

    def preview_view(self, request: HttpRequest, task_id: int) -> HttpResponse:
        task = SolutionTask.objects.get(id=task_id)
        if not task.html_content:
            return HttpResponse("<p style='padding:20px;color:#94a3b8;'>方案尚未生成完成。</p>")
        return HttpResponse(task.html_content)

    def pdf_view(self, request: HttpRequest, task_id: int) -> HttpResponse:
        task = SolutionTask.objects.get(id=task_id)
        if not task.html_content:
            messages.error(request, "方案尚未生成，无法导出 PDF")
            return HttpResponseRedirect(reverse("admin:legal_solution_solutiontask_change", args=[task_id]))

        # 使用缓存
        if task.pdf_file:
            try:
                with task.pdf_file.open("rb") as f:
                    pdf_bytes = f.read()
                response = HttpResponse(pdf_bytes, content_type="application/pdf")
                response["Content-Disposition"] = f'inline; filename="法律服务方案-{task.id}.pdf"'
                return response
            except Exception:
                pass

        exporter = PdfExporter()
        pdf_bytes = exporter.export(task.html_content)

        # 缓存 PDF
        from django.core.files.base import ContentFile
        task.pdf_file.save(f"solution_{task.id}.pdf", ContentFile(pdf_bytes), save=True)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="法律服务方案-{task.id}.pdf"'
        return response

    def adjust_section_view(self, request: HttpRequest, task_id: int, section_id: int) -> HttpResponse:
        section = SolutionSection.objects.get(id=section_id, task_id=task_id)
        if request.method == "POST":
            feedback = request.POST.get("feedback", "").strip()
            if not feedback:
                messages.error(request, "请填写调整意见")
            else:
                try:
                    service = SolutionTaskService()
                    service.regenerate_section(section_id=section_id, feedback=feedback)
                    messages.success(request, f"「{section.title}」已重新生成")
                except Exception as exc:
                    messages.error(request, f"重新生成失败：{exc}")
            return HttpResponseRedirect(
                reverse("admin:legal_solution_solutiontask_change", args=[task_id])
            )

        # GET: 显示调整表单
        html = f"""
        <html><head><meta charset="UTF-8">
        <style>body{{font-family:sans-serif;padding:32px;max-width:600px;}}
        textarea{{width:100%;height:120px;padding:10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;}}
        .btn{{background:#4f46e5;color:#fff;border:none;padding:10px 24px;border-radius:8px;cursor:pointer;font-size:14px;}}
        .btn-cancel{{background:#f3f4f6;color:#374151;margin-left:8px;}}
        h2{{margin-bottom:16px;font-size:18px;}}p{{color:#6b7280;margin-bottom:12px;font-size:14px;}}
        </style></head><body>
        <h2>✏️ 调整「{section.title}」</h2>
        <p>当前版本：v{section.version}。请描述你希望如何调整这个段落。</p>
        <form method="post">
        <input type="hidden" name="csrfmiddlewaretoken" value="{request.META.get('CSRF_COOKIE', '')}">
        <textarea name="feedback" placeholder="例如：请更详细地分析违约责任的认定标准，并引用相关法条..."></textarea>
        <br><br>
        <button type="submit" class="btn">确认调整</button>
        <a href="{reverse('admin:legal_solution_solutiontask_change', args=[task_id])}" class="btn btn-cancel" style="text-decoration:none;display:inline-block;">取消</a>
        </form></body></html>
        """
        from django.middleware.csrf import get_token
        get_token(request)
        return HttpResponse(html.replace(
            request.META.get("CSRF_COOKIE", ""),
            get_token(request),
        ))

    def save_model(self, request: HttpRequest, obj: SolutionTask, form: Any, change: bool) -> None:
        if change:
            super().save_model(request, obj, form, change)
            return

        # 新建：设置创建人
        is_lawyer = getattr(getattr(request.user, "_meta", None), "label_lower", "") == "organization.lawyer"
        if is_lawyer and getattr(request.user, "id", None):
            obj.created_by_id = int(request.user.id)

        super().save_model(request, obj, form, change)

        # 提交到队列
        service = SolutionTaskService()
        service._dispatch(obj)
        if obj.status == SolutionTaskStatus.FAILED:
            messages.error(request, f"任务创建但提交失败：{obj.error}")
        else:
            messages.success(request, "法律服务方案任务已提交，请稍后刷新查看进度。")

    @admin.display(description="案情简述", ordering="case_summary")
    def case_summary_short(self, obj: SolutionTask) -> str:
        return obj.case_summary[:40] + "..." if len(obj.case_summary) > 40 else obj.case_summary

    @admin.display(description="HTML 预览")
    def preview_html_field(self, obj: SolutionTask) -> str:
        if not obj.html_content:
            return "—"
        preview_url = reverse("admin:legal_solution_solutiontask_preview", args=[obj.pk])
        return format_html(
            '<a href="{}" target="_blank" class="button">🔍 在新标签页预览</a>&nbsp;'
            '<iframe src="{}" style="width:100%;height:500px;border:1px solid #e2e8f0;border-radius:8px;margin-top:8px;" loading="lazy"></iframe>',
            preview_url,
            preview_url,
        )

    @admin.display(description="PDF 导出")
    def download_pdf_button(self, obj: SolutionTask) -> str:
        if not obj.html_content:
            return "—"
        pdf_url = reverse("admin:legal_solution_solutiontask_pdf", args=[obj.pk])
        return format_html('<a href="{}" target="_blank" class="button">⬇️ 导出 PDF</a>', pdf_url)

    @staticmethod
    def _build_model_choices() -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        seen: set[str] = set()
        default = LLMConfig.get_default_model().strip()
        if default:
            choices.append((default, f"{default}（默认）"))
            seen.add(default)
        try:
            for item in ModelListService().get_models():
                mid = str(item.get("id", "")).strip()
                mname = str(item.get("name", "")).strip()
                if mid and mid not in seen:
                    choices.append((mid, f"{mname} ({mid})" if mname and mname != mid else mid))
                    seen.add(mid)
        except Exception:
            pass
        return choices or [(default or "Qwen/Qwen2.5-7B-Instruct", "默认模型")]
