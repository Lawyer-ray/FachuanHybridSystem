"""文档解析 Django Admin"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib import admin, messages
from django.core.files.storage import default_storage
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from apps.core.services.storage_service import sanitize_upload_filename
from apps.document_parsing.models import DocumentParsingTask, DocumentParsingTool

logger = logging.getLogger(__name__)


@admin.register(DocumentParsingTool)
class DocumentParsingToolAdmin(admin.ModelAdmin):  # pragma: no cover
    """文档解析工具 Admin（上传页面入口）"""

    def get_urls(self) -> list:
        urls = super().get_urls()
        custom_urls = [
            path(
                "upload/",
                self.admin_site.admin_view(self.upload_view),
                name="document_parsing_documentparsingtool_upload",
            ),
        ]
        return custom_urls + urls

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> TemplateResponse:
        context = {
            **self.admin_site.each_context(request),
            "title": "文档解析",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
        }
        return TemplateResponse(request, "admin/document_parsing/documentparsingtool/workbench.html", context)

    def upload_view(self, request: HttpRequest) -> HttpResponse:
        """处理文件上传，调用 MinerU 解析，存储结果"""
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:document_parsing_documentparsingtool_changelist"))

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            messages.error(request, "请选择文件")
            return HttpResponseRedirect(reverse("admin:document_parsing_documentparsingtool_changelist"))

        # 保存文件
        rel_dir = "document_parsing/uploads"
        safe_name = sanitize_upload_filename(uploaded_file.name or "uploaded")
        rel_path = f"{rel_dir}/{safe_name}"
        saved_name = default_storage.save(rel_path, uploaded_file)
        file_path = Path(settings.MEDIA_ROOT) / saved_name

        # 创建任务记录
        task = DocumentParsingTask.objects.create(  # type: ignore[misc]
            file_name=uploaded_file.name,
            file_path=str(file_path),
            file_size=uploaded_file.size,
            status=DocumentParsingTask.Status.PROCESSING,
        )

        # 同步调用 MinerU 解析（< 10 秒）
        try:
            from apps.document_parsing.services import get_document_parser

            parser = get_document_parser()
            result = parser.parse_document(
                file_path=str(file_path),
                file_type=Path(uploaded_file.name or "uploaded").suffix.lstrip("."),
                extract_tables=True,
                extract_images=False,
                return_markdown=True,
            )

            task.mark_completed(
                text=result.text,
                markdown=result.markdown or "",
                metadata=result.metadata or {},
                backend_used=result.parse_method,
            )
            messages.success(request, f"解析完成：{uploaded_file.name}")

        except Exception as e:
            logger.error("文档解析失败: %s - %s", uploaded_file.name, str(e))
            task.mark_failed(str(e))
            messages.error(request, f"解析失败：{e}")

        # 跳转到任务详情
        return HttpResponseRedirect(reverse("admin:document_parsing_documentparsingtask_change", args=[task.id]))

    def has_add_permission(self, request: HttpRequest) -> bool:  # pragma: no cover
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # pragma: no cover
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # pragma: no cover
        return False

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:  # pragma: no cover
        return {"view": True}


@admin.register(DocumentParsingTask)
class DocumentParsingTaskAdmin(admin.ModelAdmin):  # pragma: no cover
    """解析任务列表和详情 Admin"""

    list_display = [
        "id",
        "status_display",
        "file_name",
        "file_size_display",
        "backend_used",
        "text_preview",
        "created_at",
        "completed_at",
    ]
    list_filter = ["status", "backend_used", "created_at"]
    search_fields = ["file_name"]
    ordering = ["-created_at"]
    list_per_page = 20

    readonly_fields = [
        "id",
        "file_name",
        "file_path",
        "file_size",
        "status",
        "backend_used",
        "text",
        "markdown",
        "metadata",
        "error_message",
        "created_at",
        "completed_at",
    ]

    fieldsets = (
        (
            "基本信息",
            {
                "fields": ("id", "file_name", "file_path", "file_size", "status", "backend_used"),
            },
        ),
        (
            "解析结果",
            {
                "fields": ("text", "markdown"),
            },
        ),
        (
            "元数据",
            {
                "fields": ("metadata", "error_message"),
                "classes": ("collapse",),
            },
        ),
        (
            "时间",
            {
                "fields": ("created_at", "completed_at"),
                "classes": ("collapse",),
            },
        ),
    )

    change_form_template = "admin/document_parsing/documentparsingtask/change_form.html"

    @admin.display(description="状态")
    def status_display(self, obj: DocumentParsingTask) -> str:
        colors = {
            "pending": "#6c757d",
            "processing": "#ffc107",
            "completed": "#28a745",
            "failed": "#dc3545",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="文件大小")
    def file_size_display(self, obj: DocumentParsingTask) -> str:
        size = obj.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    @admin.display(description="文本预览")
    def text_preview(self, obj: DocumentParsingTask) -> str:
        if obj.text:
            preview = obj.text[:100].replace("\n", " ")
            return format_html('<span title="{}">{}...</span>', obj.text[:500], preview)
        return "-"

    def has_add_permission(self, request: HttpRequest) -> bool:  # pragma: no cover
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # pragma: no cover
        return False
