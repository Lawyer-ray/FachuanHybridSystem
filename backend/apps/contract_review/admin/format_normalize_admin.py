"""合同格式调整 Admin 页面（完整版）

包含：
1. 用户感知功能（显示使用的是POI还是Python）
2. 健康检查功能
3. 自动降级逻辑
4. 批注和版本管理功能
"""

import logging
from pathlib import Path
from typing import Any

from django.contrib import admin
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html
from django.utils import timezone

from apps.contract_review.models import FormatNormalize, ReviewTask

logger = logging.getLogger(__name__)


@admin.register(FormatNormalize)
class FormatNormalizeAdmin(admin.ModelAdmin):
    """格式调整管理页面（完整版）"""

    # 基本配置
    list_display = (
        "contract_title",
        "user",
        "status",
        "created_at",
        "format_action",
    )
    list_filter = ("status", "created_at")
    search_fields = ("contract_title",)

    # 只读字段
    readonly_fields = (
        "id",
        "user",
        "contract_title",
        "status",
        "original_file",
        "output_file",
        "created_at",
        "updated_at",
    )

    # 字段集
    def get_fieldsets(self, request: HttpRequest, obj: Any = None) -> list[Any]:
        return [
            (None, {"fields": ("id", "user", "contract_title", "status")}),
            ("文件", {"fields": ("original_file", "output_file")}),
            ("时间", {"fields": ("created_at", "updated_at")}),
        ]

    # 格式化操作按钮
    @admin.display(description="操作")
    def format_action(self, obj: ReviewTask) -> str:
        if not obj.original_file:
            return "—"

        # 检查是否有输出文件
        if obj.output_file:
            # 已处理：显示下载按钮
            download_url = f"/media/{obj.output_file}"
            reformat_url = f"/admin/contract_review/formatnormalize/{obj.pk}/execute/"
            return format_html(
                '<a href="{}" class="btn btn-success" download style="background: #4CAF50; color: white; padding: 5px 10px; border-radius: 3px; text-decoration: none; margin-right: 5px;">下载</a>'
                '<a href="{}" class="btn btn-warning" onclick="return confirm(\'确定要重新格式化吗？\')" style="background: #FF9800; color: white; padding: 5px 10px; border-radius: 3px; text-decoration: none;">重新格式化</a>',
                download_url,
                reformat_url
            )
        else:
            # 未处理：显示格式化按钮
            url = f"/admin/contract_review/formatnormalize/{obj.pk}/execute/"

            # 检查POI服务状态
            from apps.core.services.poi_client import get_poi_client
            poi_client = get_poi_client()
            is_poi_available = poi_client.health_check()

            if is_poi_available:
                return format_html(
                    '<a href="{}" class="btn btn-primary" onclick="return confirm(\'使用POI服务格式化？\')" style="background: #417690; color: white; padding: 5px 10px; border-radius: 3px; text-decoration: none;">格式化</a>',
                    url
                )
            else:
                return format_html(
                    '<a href="{}" class="btn btn-warning" onclick="return confirm(\'POI服务不可用，将使用Python格式化？\')" style="background: #FF9800; color: white; padding: 5px 10px; border-radius: 3px; text-decoration: none;">格式化(Python)</a>',
                    url
                )

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
            path(
                "<uuid:task_id>/add-annotation/",
                self.admin_site.admin_view(self.add_annotation_view),
                name="contract_review_formatnormalize_add_annotation",
            ),
            path(
                "health-check/",
                self.admin_site.admin_view(self.health_check_view),
                name="contract_review_formatnormalize_health_check",
            ),
        ]
        return custom + super().get_urls()

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponse:
        """格式调整列表页面"""
        tasks = ReviewTask.objects.filter(
            original_file__isnull=False,
            original_file__gt="",
        ).order_by("-created_at")

        # 检查POI服务状态
        from apps.core.services.poi_client import get_poi_client
        poi_client = get_poi_client()
        poi_status = poi_client.health_check()

        context = {
            **self.admin_site.each_context(request),
            "title": "合同格式调整",
            "opts": self.model._meta,
            "tasks": tasks,
            "poi_status": poi_status,
            "poi_status_text": "在线" if poi_status else "离线",
            "poi_status_color": "green" if poi_status else "red",
            "has_add_permission": False,
            "has_change_permission": False,
            "has_delete_permission": False,
        }
        return TemplateResponse(
            request,
            "admin/contract_review/format_normalize.html",
            context,
        )

    def upload_view(self, request: HttpRequest) -> HttpResponse:
        """上传合同文件页面"""
        if request.method == "POST":
            uploaded_file = request.FILES.get("contract_file")
            numbering_type = request.POST.get("numbering_type", "chinese")

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

                # 创建任务，并保存编号类型
                task = ReviewTask.objects.create(
                    user=request.user,  # type: ignore[misc]
                    contract_title=uploaded_file.name.rsplit(".", 1)[0],
                    original_file=saved_path,
                    status="pending",
                    selected_steps=[numbering_type],  # 保存编号类型
                )
                messages.success(request, f"文件上传成功: {uploaded_file.name}")
                return HttpResponseRedirect(f"/admin/contract_review/formatnormalize/{task.id}/execute/")
            except Exception as e:
                logger.exception("文件上传失败: %s", e)
                messages.error(request, f"文件上传失败: {e!s}")
                return HttpResponseRedirect("/admin/contract_review/formatnormalize/upload/")

        # 检查POI服务状态
        from apps.core.services.poi_client import get_poi_client
        poi_client = get_poi_client()
        poi_status = poi_client.health_check()

        context = {
            **self.admin_site.each_context(request),
            "title": "上传合同文件",
            "opts": self.model._meta,
            "poi_status": poi_status,
            "poi_status_text": "在线" if poi_status else "离线",
            "poi_status_color": "green" if poi_status else "red",
        }
        return TemplateResponse(
            request,
            "admin/contract_review/format_normalize_upload.html",
            context,
        )

    def execute_view(self, request: HttpRequest, task_id: Any) -> HttpResponse:
        """执行格式规范化"""
        from django.conf import settings
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

        # 使用MEDIA_ROOT构造完整的绝对路径
        original_path = Path(settings.MEDIA_ROOT) / task.original_file
        if not original_path.exists():
            messages.error(request, f"原始文件不存在: {original_path}")
            return HttpResponseRedirect("/admin/contract_review/formatnormalize/")

        try:
            # 生成输出文件路径
            output_dir = original_path.parent
            output_filename = f"{original_path.stem}_规范化{original_path.suffix}"
            output_path = output_dir / output_filename

            # 确定编号类型
            numbering_type = "chinese"  # 默认
            if task.selected_steps and len(task.selected_steps) > 0:
                numbering_type = task.selected_steps[0]

            # 执行格式规范化
            normalizer = DocxFormatNormalizer(original_path, output_path)
            result_path = normalizer.normalize()

            # 更新任务状态
            task.output_file = str(result_path.relative_to(settings.MEDIA_ROOT))
            task.status = "completed"
            task.save(update_fields=["output_file", "status"])

            messages.success(
                request,
                f"✓ 格式规范化完成！<br>"
                f"<a href='/media/{task.output_file}' download style='color: #4CAF50; font-weight: bold;'>点击下载格式化后的文件</a>"
            )

        except Exception as e:
            logger.exception("格式规范化失败: %s", e)
            task.status = "failed"
            task.save(update_fields=["status"])
            messages.error(request, f"格式规范化失败: {e!s}")

        return HttpResponseRedirect("/admin/contract_review/formatnormalize/")

    def add_annotation_view(self, request: HttpRequest, task_id: Any) -> HttpResponse:
        """添加批注"""
        from django.http import HttpResponseRedirect

        try:
            task = ReviewTask.objects.get(id=task_id)
        except ReviewTask.DoesNotExist:
            messages.error(request, "任务不存在")
            return HttpResponseRedirect("/admin/contract_review/formatnormalize/")

        if request.method == "POST":
            annotation_content = request.POST.get("annotation_content", "")
            if annotation_content:
                # 获取或创建FormatNormalize记录
                format_record, created = FormatNormalize.objects.get_or_create(
                    task=task,
                    defaults={
                        "status": "pending",
                        "annotations": []
                    }
                )

                # 添加批注
                annotation = {
                    "author": request.user.get_full_name() or request.user.username,
                    "content": annotation_content,
                    "created_at": timezone.now().isoformat()
                }

                if not format_record.annotations:
                    format_record.annotations = []
                format_record.annotations.append(annotation)
                format_record.save(update_fields=["annotations"])

                messages.success(request, "批注添加成功")
            else:
                messages.error(request, "批注内容不能为空")

        return HttpResponseRedirect(f"/admin/contract_review/formatnormalize/")

    def health_check_view(self, request: HttpRequest) -> HttpResponse:
        """健康检查页面（简化版）"""
        from django.http import HttpResponse
        import json

        from apps.core.services.poi_client import get_poi_client

        poi_client = get_poi_client()
        poi_status = poi_client.health_check()

        response_data = {
            "poi_service": {
                "status": "online" if poi_status else "offline",
                "available": poi_status
            }
        }

        return HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            content_type="application/json"
        )
