"""合同格式调整 Admin 页面

独立于合同审查任务的格式调整功能入口
"""

import logging
from pathlib import Path
from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path

from apps.contract_review.models import FormatNormalize, ReviewTask

logger = logging.getLogger(__name__)


@admin.register(FormatNormalize)
class FormatNormalizeAdmin(admin.ModelAdmin):
    """格式调整管理页面"""

    # 基本配置
    list_display = ("contract_title", "user", "status", "format_action")
    list_filter = ("status", "created_at")
    search_fields = ("contract_title",)

    # 隐藏不需要的字段
    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        return (
            "id",
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
            "current_step",
            "error_message",
            "original_file",
            "output_file",
            "selected_steps",
            "review_report",
            "pdf_cache_file",
            "created_at",
            "updated_at",
        )

    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> list[Any]:
        return [
            (None, {"fields": ("id", "user", "contract_title", "status")}),
            ("文件", {"fields": ("original_file", "output_file")}),
            ("时间", {"fields": ("created_at", "updated_at")}),
        ]

    @admin.display(description="操作")
    def format_action(self, obj: ReviewTask) -> str:
        if not obj.original_file:
            return "—"
        url = f"/admin/contract-review-format-normalize/{obj.pk}/execute/"
        return f'<a href="{url}" class="btn" onclick="return confirm(\'确定要执行格式规范化吗？\')">格式规范化</a>'

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def get_urls(self) -> list[Any]:
        custom = [
            path(
                "",
                self.admin_site.admin_view(self.changelist_view),
                name="contract_review_formatnormalize_changelist",
            ),
            path(
                "upload/",
                self.admin_site.admin_view(self.upload_view),
                name="contract_review_formatnormalize_upload",
            ),
            path(
                "<uuid:task_id>/execute/",
                self.admin_site.admin_view(self.execute_view),
                name="contract_review_formatnormalize_execute",
            ),
        ]
        return custom + super().get_urls()

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponse:
        """格式调整列表页面"""
        tasks = ReviewTask.objects.filter(
            original_file__isnull=False,
            original_file__gt="",
        ).order_by("-created_at")

        context = {
            **self.admin_site.each_context(request),
            "title": "合同格式调整",
            "opts": self.model._meta,
            "tasks": tasks,
        }
        return TemplateResponse(
            request,
            "admin/contract_review/format_normalize.html",
            context,
        )

    def upload_view(self, request: HttpRequest) -> HttpResponse:
        """上传合同文件页面"""
        from django.contrib import messages
        from django.http import HttpResponseRedirect

        if request.method == "POST":
            uploaded_file = request.FILES.get("contract_file")
            if not uploaded_file:
                messages.error(request, "请选择要上传的合同文件")
                return HttpResponseRedirect("/admin/contract_review/formatnormalize/upload/")

            if not uploaded_file.name or not uploaded_file.name.endswith((".docx", ".doc")):
                messages.error(request, "只支持 .docx 或 .doc 格式的文件")
                return HttpResponseRedirect("/admin/contract_review/formatnormalize/upload/")

            try:
                # 保存上传的文件
                from django.core.files.storage import default_storage

                file_path = f"contract_review/uploads/{uploaded_file.name}"
                saved_path = default_storage.save(file_path, uploaded_file)

                # 创建任务
                task = ReviewTask.objects.create(
                    user=request.user,  # type: ignore[misc]
                    contract_title=uploaded_file.name.rsplit(".", 1)[0],
                    original_file=saved_path,
                    status="pending",
                )
                messages.success(request, f"文件上传成功: {uploaded_file.name}")
                return HttpResponseRedirect(f"/admin/contract_review/formatnormalize/{task.id}/execute/")
            except Exception as e:
                logger.exception("文件上传失败: %s", e)
                messages.error(request, f"文件上传失败: {e!s}")
                return HttpResponseRedirect("/admin/contract_review/formatnormalize/upload/")

        context = {
            **self.admin_site.each_context(request),
            "title": "上传合同文件",
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request,
            "admin/contract_review/format_normalize_upload.html",
            context,
        )

    def execute_view(self, request: HttpRequest, task_id: Any) -> HttpResponse:
        """执行格式规范化"""
        from django.contrib import messages
        from django.http import HttpResponseRedirect

        from apps.contract_review.services.format_normalizer import DocxFormatNormalizer

        try:
            task = ReviewTask.objects.get(id=task_id)
        except ReviewTask.DoesNotExist:
            messages.error(request, "任务不存在")
            return HttpResponseRedirect("/admin/contract_review/formatnormalize/")

        if not task.original_file:
            messages.error(request, "该任务没有原始文件")
            return HttpResponseRedirect("/admin/contract_review/formatnormalize/")

        original_path = Path(task.original_file)
        if not original_path.exists():
            messages.error(request, f"原始文件不存在: {original_path}")
            return HttpResponseRedirect("/admin/contract_review/formatnormalize/")

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

            messages.success(request, f"格式规范化完成: {result_path.name}")

        except Exception as e:
            logger.exception("格式规范化失败: %s", e)
            messages.error(request, f"格式规范化失败: {e!s}")

        return HttpResponseRedirect("/admin/contract_review/formatnormalize/")
