import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.contract_review.models import ReviewTask

_PARTY_FIELDS = ("party_a", "party_b", "party_c", "party_d")


@admin.register(ReviewTask)
class ReviewTaskAdmin(admin.ModelAdmin[ReviewTask]):
    list_display = ("contract_title", "user", "status", "current_step_display", "created_at")
    list_filter = ("status", "represented_party", "created_at")
    search_fields = ("contract_title", "party_a", "party_b")
    readonly_fields = (
        "id",
        "original_file_link",
        "output_file_link",
        "error_message",
        "current_step",
        "review_report_html",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    @admin.display(description=_("当前处理步骤"))
    def current_step_display(self, obj: ReviewTask) -> str:
        if obj.status == "completed":
            return "✅ 已完成"
        if obj.status == "failed":
            return "❌ 失败"
        if obj.current_step:
            return obj.get_current_step_display()
        return "—"

    _STEP_LABELS: dict[str, str] = {
        "typo_check": "错别字校对",
        "format_document": "修订格式",
        "contract_review": "审查合同",
        "review_report": "输出审查报告",
    }

    @admin.display(description=_("选中的处理步骤"))
    def selected_steps_display(self, obj: ReviewTask) -> str:
        steps = obj.selected_steps or []
        if not steps:
            return "全部"
        labels = [self._STEP_LABELS.get(s, s) for s in steps]
        return "、".join(labels)

    def get_readonly_fields(
        self, request: HttpRequest, obj: ReviewTask | None = None
    ) -> tuple[str, ...]:
        base = (
            "id", "original_file_link", "output_file_link",
            "error_message", "current_step", "review_report_html",
            "selected_steps_display",
            "created_at", "updated_at",
        )
        if obj and obj.status in ("completed", "failed", "processing"):
            return base + (
                "user", "contract_title", "model_name", "reviewer_name",
                "party_a", "party_b", "party_c", "party_d",
                "represented_party", "status",
            )
        return base

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        obj = self.get_object(request, object_id)
        ctx = extra_context or {}
        if obj and obj.status in ("completed", "failed", "processing"):
            ctx["show_save"] = False
            ctx["show_save_and_add_another"] = False
            ctx["show_save_and_continue"] = False
            ctx["show_delete_link"] = True
        return super().change_view(request, object_id, form_url, ctx)

    @admin.display(description=_("原始文件"))
    def original_file_link(self, obj: ReviewTask) -> str:
        if not obj.original_file:
            return "—"
        return self._file_link(obj, obj.original_file)

    @admin.display(description=_("审查结果"))
    def output_file_link(self, obj: ReviewTask) -> str:
        if not obj.output_file:
            return "—"
        return self._file_link(obj, obj.output_file, primary=True)

    @admin.display(description=_("评估报告"))
    def review_report_html(self, obj: ReviewTask) -> str:
        if not obj.review_report:
            return "—"
        url = f"/admin/contract_review/reviewtask/{obj.pk}/report/"
        style = (
            "display:inline-flex;align-items:center;gap:6px;padding:8px 16px;"
            "border-radius:8px;text-decoration:none;font-weight:600;font-size:13px;"
            "background:var(--primary,#417690);color:#fff;"
        )
        return format_html('<a href="{}" style="{}" target="_blank">📋 查看评估报告</a>', url, style)

    @staticmethod
    def _file_link(obj: ReviewTask, file_path: str, primary: bool = False) -> str:
        name = Path(file_path).name
        url = f"/api/v1/contract-review/{obj.pk}/{'download' if primary else 'download-original'}"
        style = (
            "display:inline-flex;align-items:center;gap:6px;padding:8px 16px;"
            "border-radius:8px;text-decoration:none;font-weight:600;font-size:13px;"
        )
        if primary:
            style += "background:var(--primary,#417690);color:#fff;"
        else:
            style += "background:var(--darkened-bg,#f5f5f5);color:var(--body-fg,#333);border:1px solid var(--border-color,#ddd);"
        return format_html(
            '<a href="{}" style="{}" download>📥 {}</a>',
            url, style, name,
        )

    def get_fieldsets(
        self, request: HttpRequest, obj: ReviewTask | None = None
    ) -> list[tuple[str | None, dict[str, Any]]]:
        party_fields = tuple(
            f for f in _PARTY_FIELDS if obj and getattr(obj, f, "")
        ) or ("party_a", "party_b")

        fieldsets = [
            (None, {"fields": ("id", "user", "contract_title", "model_name", "reviewer_name")}),
            (_("当事人"), {"fields": (*party_fields, "represented_party")}),
            (_("处理步骤"), {"fields": ("selected_steps_display",)}),
            (_("状态"), {"fields": ("status", "current_step", "error_message")}),
            (_("文件"), {"fields": ("original_file_link", "output_file_link")}),
            (_("时间"), {"fields": ("created_at", "updated_at")}),
        ]
        if obj and obj.review_report:
            fieldsets.insert(4, (_("评估报告"), {"fields": ("review_report_html",)}))
        return fieldsets

    def add_view(
        self,
        request: HttpRequest,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        from apps.core.llm.model_list_service import ModelListService

        svc = ModelListService()
        models = svc.get_models()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": _("新建合同审查任务"),
            "has_view_permission": self.has_view_permission(request),
            "models_json": json.dumps(models, ensure_ascii=False),
        }
        return TemplateResponse(
            request,
            "admin/contract_review/reviewtask/upload.html",
            context,
        )

    def get_urls(self) -> list[Any]:
        custom = [
            path(
                "<uuid:task_id>/report/",
                self.admin_site.admin_view(self.report_view),
                name="contract_review_reviewtask_report",
            ),
            path(
                "<uuid:task_id>/report/pdf/",
                self.admin_site.admin_view(self.report_pdf_view),
                name="contract_review_reviewtask_report_pdf",
            ),
        ]
        return custom + super().get_urls()

    def report_view(self, request: HttpRequest, task_id: UUID) -> HttpResponse:
        import markdown

        task = ReviewTask.objects.get(id=task_id)
        text = task.review_report or ""
        text = re.sub(r"^```\w*\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text)
        report_html = markdown.markdown(text, extensions=["tables", "fenced_code"])

        context = {
            **self.admin_site.each_context(request),
            "task": task,
            "report_html": mark_safe(report_html),
            "title": f"评估报告 - {task.contract_title or task.id}",
        }
        return TemplateResponse(
            request,
            "admin/contract_review/reviewtask/report.html",
            context,
        )

    def report_pdf_view(self, request: HttpRequest, task_id: UUID) -> HttpResponse:
        import markdown
        from django.template.loader import render_to_string
        from weasyprint import HTML

        task = ReviewTask.objects.get(id=task_id)
        text = task.review_report or ""
        text = re.sub(r"^```\w*\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text)
        report_html = markdown.markdown(text, extensions=["tables", "fenced_code"])

        html_string = render_to_string(
            "admin/contract_review/reviewtask/report_pdf.html",
            {"task": task, "report_html": mark_safe(report_html),
             "title": f"评估报告 - {task.contract_title or task.id}"},
        )
        pdf = HTML(string=html_string).write_pdf()
        filename = f"评估报告-{task.contract_title or task.id}.pdf"
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response
