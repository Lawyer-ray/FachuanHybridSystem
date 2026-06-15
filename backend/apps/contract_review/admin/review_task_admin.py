import json
import logging
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html

from apps.contract_review.models import ReviewTask, TaskStatus

logger = logging.getLogger(__name__)

_PARTY_FIELDS = ("party_a", "party_b", "party_c", "party_d")


@admin.register(ReviewTask)
class ReviewTaskAdmin(admin.ModelAdmin):  # pragma: no cover
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
    change_form_template = "admin/contract_review/reviewtask/change_form.html"
    actions = ["retry_selected_tasks", "delete_selected_with_files", "normalize_format"]

    @admin.action(description="重新执行选中的审查任务")
    def retry_selected_tasks(self, request: HttpRequest, queryset: Any) -> None:  # pragma: no cover
        from apps.core.tasking import submit_task

        count = 0
        for task in queryset:
            if task.status in [TaskStatus.FAILED, TaskStatus.COMPLETED]:
                task.status = TaskStatus.CONFIRMED
                task.save(update_fields=["status"])
                submit_task(
                    "apps.contract_review.services.review.review_service.process_review",
                    str(task.id),
                    timeout=1800,
                )
                count += 1
        self.message_user(request, f"已重新提交 {count} 个审查任务")

    @admin.action(description="删除选中任务及关联文件")
    def delete_selected_with_files(self, request: HttpRequest, queryset: Any) -> None:  # pragma: no cover
        from apps.contract_review.repositories.review_task_repository import ReviewTaskRepository

        repository = ReviewTaskRepository()
        deleted_count = 0
        file_count = 0

        for task in queryset:
            # 删除文件
            if task.original_file:
                original_path = Path(task.original_file)
                if original_path.exists():
                    try:
                        original_path.unlink()
                        file_count += 1
                    except OSError as e:
                        logger.warning("删除上传文件失败: %s - %s", original_path, e)

            if task.output_file:
                output_path = Path(task.output_file)
                if output_path.exists():
                    try:
                        output_path.unlink()
                        file_count += 1
                    except OSError as e:
                        logger.warning("删除输出文件失败: %s - %s", output_path, e)

            # 删除数据库记录
            repository.delete_by_id(task.id)
            deleted_count += 1

        self.message_user(request, f"已删除 {deleted_count} 个任务及 {file_count} 个关联文件")

    @admin.action(description="格式规范化（调整字体/行距/页边距）")
    def normalize_format(self, request: HttpRequest, queryset: Any) -> None:  # pragma: no cover
        from apps.contract_review.services.format_normalizer import DocxFormatNormalizer

        success_count = 0
        fail_count = 0

        for task in queryset:
            if not task.original_file:
                self.message_user(request, f"任务 {task.contract_title or task.id} 没有原始文件", level="warning")
                fail_count += 1
                continue

            original_path = Path(task.original_file)
            if not original_path.exists():
                self.message_user(request, f"任务 {task.contract_title or task.id} 的原始文件不存在", level="warning")
                fail_count += 1
                continue

            try:
                # 生成输出文件路径
                output_dir = original_path.parent
                output_filename = f"{original_path.stem}_规范化{original_path.suffix}"
                output_path = output_dir / output_filename

                # 执行格式规范化
                normalizer = DocxFormatNormalizer(original_path, output_path)
                result_path = normalizer.normalize()

                # 更新任务的输出文件
                task.output_file = str(result_path)
                task.save(update_fields=["output_file"])

                success_count += 1
                logger.info("格式规范化成功: %s -> %s", original_path, result_path)

            except Exception as e:
                logger.exception("格式规范化失败: %s", e)
                self.message_user(
                    request,
                    f"任务 {task.contract_title or task.id} 格式规范化失败: {e!s}",
                    level="error",
                )
                fail_count += 1

        if success_count > 0:
            self.message_user(request, f"成功规范化 {success_count} 个文件")
        if fail_count > 0:
            self.message_user(request, f"{fail_count} 个文件规范化失败", level="warning")

    @admin.display(description="当前处理步骤")
    def current_step_display(self, obj: ReviewTask) -> str:  # pragma: no cover
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

    @admin.display(description="选中的处理步骤")
    def selected_steps_display(self, obj: ReviewTask) -> str:  # pragma: no cover
        steps = obj.selected_steps or []
        if not steps:
            return "全部"
        labels = [self._STEP_LABELS.get(s, s) for s in steps]
        return "、".join(labels)

    def get_readonly_fields(self, request: HttpRequest, obj: ReviewTask | None = None) -> tuple[str, ...]:  # pragma: no cover
        base = (
            "id",
            "original_file_link",
            "output_file_link",
            "error_message",
            "current_step",
            "review_report_html",
            "selected_steps_display",
            "created_at",
            "updated_at",
        )
        if obj and obj.status in ("completed", "failed", "processing"):
            return base + (
                "user",
                "contract_title",
                "model_name",
                "reviewer_name",
                "party_a",
                "party_b",
                "party_c",
                "party_d",
                "represented_party",
                "status",
            )
        return base

    def change_view(  # pragma: no cover
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

    @admin.display(description="原始文件")
    def original_file_link(self, obj: ReviewTask) -> str:  # pragma: no cover
        if not obj.original_file:
            return "—"
        return self._file_link(obj, obj.original_file)

    @admin.display(description="审查结果")
    def output_file_link(self, obj: ReviewTask) -> str:  # pragma: no cover
        if not obj.output_file:
            return "—"
        return self._file_link(obj, obj.output_file, primary=True)

    @admin.display(description="评估报告")
    def review_report_html(self, obj: ReviewTask) -> str:  # pragma: no cover
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
    def _file_link(obj: ReviewTask, file_path: str, primary: bool = False) -> str:  # pragma: no cover
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
            url,
            style,
            name,
        )

    def get_fieldsets(  # pragma: no cover
        self, request: HttpRequest, obj: ReviewTask | None = None
    ) -> list[tuple[str | None, dict[str, Any]]]:
        party_fields = tuple(f for f in _PARTY_FIELDS if obj and getattr(obj, f, "")) or ("party_a", "party_b")

        fieldsets = [
            (None, {"fields": ("id", "user", "contract_title", "model_name", "reviewer_name")}),
            ("当事人", {"fields": (*party_fields, "represented_party")}),
            ("处理步骤", {"fields": ("selected_steps_display",)}),
            ("状态", {"fields": ("status", "current_step", "error_message")}),
            ("文件", {"fields": ("original_file_link", "output_file_link")}),
            ("时间", {"fields": ("created_at", "updated_at")}),
        ]
        if obj and obj.review_report:
            fieldsets.insert(4, ("评估报告", {"fields": ("review_report_html",)}))
        return fieldsets

    def add_view(  # pragma: no cover
        self,
        request: HttpRequest,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        from apps.core.llm.model_list_service import ModelListService

        svc = ModelListService()
        result = svc.get_result()
        models = result.models

        if result.is_fallback:
            from django.contrib import messages

            messages.warning(
                request,
                "模型列表获取失败：%(error)s，当前显示默认模型列表" % {"error": result.error_message},
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "新建合同审查任务",
            "has_view_permission": self.has_view_permission(request),
            "models_json": json.dumps(models, ensure_ascii=False),
        }
        return TemplateResponse(
            request,
            "admin/contract_review/reviewtask/upload.html",
            context,
        )

    def get_urls(self) -> list[Any]:  # pragma: no cover
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
            path(
                "format-normalize/",
                self.admin_site.admin_view(self.format_normalize_view),
                name="contract_review_reviewtask_format_normalize",
            ),
            path(
                "<uuid:task_id>/format-normalize/",
                self.admin_site.admin_view(self.format_normalize_task_view),
                name="contract_review_reviewtask_format_normalize_task",
            ),
        ]
        return custom + super().get_urls()

    def report_view(self, request: HttpRequest, task_id: UUID) -> HttpResponse:  # pragma: no cover
        import markdown

        task = ReviewTask.objects.get(id=task_id)
        text = task.review_report or ""
        text = re.sub(r"^```\w*\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text)
        report_html = markdown.markdown(text, extensions=["tables", "fenced_code"])

        context = {
            **self.admin_site.each_context(request),
            "task": task,
            "report_html": report_html,
            "title": f"评估报告 - {task.contract_title or task.id}",
        }
        return TemplateResponse(
            request,
            "admin/contract_review/reviewtask/report.html",
            context,
        )

    def report_pdf_view(self, request: HttpRequest, task_id: UUID) -> HttpResponse:  # pragma: no cover
        import markdown
        from django.conf import settings
        from django.template.loader import render_to_string
        from weasyprint import HTML

        task = ReviewTask.objects.get(id=task_id)

        # 检查缓存是否存在
        cache_path = Path(task.pdf_cache_file) if task.pdf_cache_file else None
        if cache_path and cache_path.exists():
            # 返回缓存的 PDF
            with open(cache_path, "rb") as f:
                pdf = f.read()
            filename = f"评估报告-{task.contract_title or task.id}.pdf"
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{filename}"'
            return response

        # 生成 PDF
        text = task.review_report or ""
        text = re.sub(r"^```\w*\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text)
        report_html = markdown.markdown(text, extensions=["tables", "fenced_code"])

        html_string = render_to_string(
            "admin/contract_review/reviewtask/report_pdf.html",
            {
                "task": task,
                "report_html": report_html,
                "title": f"评估报告 - {task.contract_title or task.id}",
            },
        )
        pdf = HTML(string=html_string).write_pdf()

        # 保存到缓存
        pdf_dir = Path(settings.MEDIA_ROOT) / "contract_review" / "pdf_cache"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        cache_path = pdf_dir / f"{task_id}.pdf"
        with open(cache_path, "wb") as f:
            f.write(pdf)

        # 更新数据库记录
        task.pdf_cache_file = str(cache_path)
        task.save(update_fields=["pdf_cache_file"])

        filename = f"评估报告-{task.contract_title or task.id}.pdf"
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response

    def format_normalize_view(self, request: HttpRequest) -> HttpResponse:  # pragma: no cover
        """格式调整页面"""
        # 获取所有有原始文件的任务
        tasks = ReviewTask.objects.filter(
            original_file__isnull=False,
            original_file__gt="",
        ).order_by("-created_at")[:50]

        context = {
            **self.admin_site.each_context(request),
            "title": "合同格式调整",
            "opts": self.model._meta,
            "tasks": tasks,
        }
        return TemplateResponse(
            request,
            "admin/contract_review/reviewtask/format_normalize.html",
            context,
        )

    def format_normalize_task_view(self, request: HttpRequest, task_id: UUID) -> HttpResponse:  # pragma: no cover
        """对单个任务执行格式调整"""
        from apps.contract_review.services.format_normalizer import DocxFormatNormalizer

        try:
            task = ReviewTask.objects.get(id=task_id)
        except ReviewTask.DoesNotExist:
            from django.http import Http404

            raise Http404("任务不存在")

        if not task.original_file:
            from django.contrib import messages

            messages.error(request, "该任务没有原始文件")
            return self._redirect_back(request)

        original_path = Path(task.original_file)
        if not original_path.exists():
            from django.contrib import messages

            messages.error(request, f"原始文件不存在: {original_path}")
            return self._redirect_back(request)

        try:
            # 生成输出文件路径
            output_dir = original_path.parent
            output_filename = f"{original_path.stem}_规范化{original_path.suffix}"
            output_path = output_dir / output_filename

            # 执行格式规范化
            normalizer = DocxFormatNormalizer(original_path, output_path)
            result_path = normalizer.normalize()

            # 更新任务的输出文件
            task.output_file = str(result_path)
            task.save(update_fields=["output_file"])

            from django.contrib import messages

            messages.success(request, f"格式规范化完成: {result_path.name}")

        except Exception as e:
            logger.exception("格式规范化失败: %s", e)
            from django.contrib import messages

            messages.error(request, f"格式规范化失败: {e!s}")

        return self._redirect_back(request)

    def _redirect_back(self, request: HttpRequest) -> HttpResponse:  # pragma: no cover
        """重定向回上一页"""
        from django.http import HttpResponseRedirect

        return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/admin/contract_review/reviewtask/"))
