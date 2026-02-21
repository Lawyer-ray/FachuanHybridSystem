"""
法院文书智能识别 Django Admin 独立页面

提供文书拖拽上传、异步识别、状态查询等功能。
Requirements: 1.1, 1.2, 5.1, 5.2, 5.3
"""

from typing import ClassVar
import logging

from django.contrib import admin
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect

from apps.automation.models import CourtSMS  # 使用现有模型作为代理
from apps.automation.models import DocumentRecognitionStatus, DocumentRecognitionTask

logger = logging.getLogger("apps.automation")


class DocumentRecognitionAdmin(admin.ModelAdmin):
    """
    文书识别管理页面 - 独立页面（异步模式）

    提供 /admin/automation/document-recognition/ 路径访问
    Requirements: 1.1, 1.2
    """

    def get_urls(self):
        """添加自定义 URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "recognition/",
                self.admin_site.admin_view(self.recognition_view),
                name="automation_document_recognition",
            ),
            path(
                "recognition/upload/",
                self.admin_site.admin_view(self.upload_view),
                name="automation_document_recognition_upload",
            ),
            path(
                "recognition/status/<int:task_id>/",
                self.admin_site.admin_view(self.status_view),
                name="automation_document_recognition_status",
            ),
        ]
        return custom_urls + urls

    def recognition_view(self, request):
        """文书识别页面视图"""
        context = {
            **self.admin_site.each_context(request),
            "title": "法院文书智能识别",
            "opts": self.model._meta,
            "has_view_permission": True,
        }
        return render(request, "admin/automation/document_recognition/recognition.html", context)

    @method_decorator(csrf_protect)
    def upload_view(self, request):
        """文件上传 API（异步提交任务）"""
        if request.method != "POST":
            return JsonResponse({"error": {"message": "只支持 POST 请求", "code": "METHOD_NOT_ALLOWED"}}, status=405)

        from apps.core.validators import Validators

        uploaded_file = request.FILES.get("file")

        try:
            Validators.validate_uploaded_file(uploaded_file, allowed_extensions=[".pdf", ".jpg", ".jpeg", ".png"])
        except Exception as e:
            return JsonResponse({"error": {"message": str(e), "code": "UNSUPPORTED_FILE_FORMAT"}}, status=400)

        file_ext = "." + uploaded_file.name.split(".")[-1].lower() if "." in uploaded_file.name else ""

        try:
            import uuid
            from pathlib import Path

            from django.conf import settings
            from django_q.tasks import async_task

            from apps.automation.models import DocumentRecognitionStatus, DocumentRecognitionTask

            upload_dir = Path(settings.MEDIA_ROOT) / "automation" / "document_recognition"
            upload_dir.mkdir(parents=True, exist_ok=True)

            unique_filename = f"{uuid.uuid4().hex}{file_ext}"
            file_path = str(upload_dir / unique_filename)

            with open(file_path, "wb+") as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            task = DocumentRecognitionTask.objects.create(
                file_path=file_path, original_filename=uploaded_file.name, status=DocumentRecognitionStatus.PENDING
            )

            async_task(
                "apps.automation.tasks.execute_document_recognition_task",
                task.id,
                task_name=f"doc_recognition_{task.id}",
            )

            logger.info(f"文书识别任务已提交: task_id={task.id}, file={uploaded_file.name}")
            return JsonResponse({"task_id": task.id, "status": "pending", "message": "任务已提交，正在后台处理"})

        except Exception as e:
            logger.error(f"文件上传失败: {e}", exc_info=True)
            return JsonResponse({"error": {"message": str(e), "code": "UPLOAD_ERROR"}}, status=500)

    def status_view(self, request, task_id):
        """查询任务状态 API"""
        from apps.automation.models import DocumentRecognitionTask

        try:
            task = DocumentRecognitionTask.objects.select_related("case").get(id=task_id)
        except DocumentRecognitionTask.DoesNotExist:
            return JsonResponse({"error": {"message": "任务不存在", "code": "TASK_NOT_FOUND"}}, status=404)

        response = {
            "task_id": task.id,
            "status": task.status,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat(),
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        }

        if task.status == "success":
            response["recognition"] = {
                "document_type": task.document_type,
                "case_number": task.case_number,
                "key_time": task.key_time.isoformat() if task.key_time else None,
                "confidence": task.confidence,
                "extraction_method": task.extraction_method,
                "raw_text": task.raw_text,
            }
            response["binding"] = {
                "success": task.binding_success,
                "case_id": task.case_id,
                "case_name": task.case.name if task.case else None,
                "case_log_id": task.case_log_id,
                "message": task.binding_message,
                "error_code": task.binding_error_code,
            }
            response["file_path"] = task.renamed_file_path or task.file_path

        return JsonResponse(response)

    def has_module_permission(self, request):
        return True

    def has_view_permission(self, request, obj=None):
        return True


class DocumentRecognitionProxy(CourtSMS):
    """文书识别代理模型（不创建数据库表）"""

    class Meta:
        proxy = True
        verbose_name = _("文书智能识别")
        verbose_name_plural = _("文书智能识别")
        app_label = "automation"


@admin.register(DocumentRecognitionProxy)
class DocumentRecognitionProxyAdmin(DocumentRecognitionAdmin):
    """文书识别 Admin（使用代理模型注册）"""

    def changelist_view(self, request, extra_context=None):
        from django.http import HttpResponseRedirect
        from django.urls import reverse

        return HttpResponseRedirect(reverse("admin:automation_document_recognition"))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return True


@admin.register(DocumentRecognitionTask)
class DocumentRecognitionTaskAdmin(admin.ModelAdmin):
    """
    文书识别任务管理

    显示任务列表、识别结果、绑定状态和通知状态
    Requirements: 5.1, 5.2, 5.3
    """

    def get_urls(self):
        """添加自定义 URL（放在默认 URL 之前）"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "recognize/",
                self.admin_site.admin_view(self.recognition_view),
                name="automation_documentrecognitiontask_recognize",
            ),
        ]
        return custom_urls + urls

    def recognition_view(self, request):
        """文书识别页面视图"""
        context = {
            **self.admin_site.each_context(request),
            "title": "法院文书智能识别",
            "opts": self.model._meta,
            "has_view_permission": True,
        }
        return render(request, "admin/automation/document_recognition/recognition.html", context)

    """
    文书识别任务管理

    显示任务列表、识别结果、绑定状态和通知状态
    Requirements: 5.1, 5.2, 5.3
    """

    # 列表显示字段
    list_display: ClassVar[list[str]] = [
        "id",
        "status_display",
        "original_filename",
        "document_type_display",
        "case_number",
        "case_display",
        "binding_status_display",
        "notification_status_display",
        "notification_sent_at",
        "created_at",
    ]

    # 列表筛选器
    list_filter: ClassVar[list[str]] = [
        "status",
        "document_type",
        "binding_success",
        "notification_sent",
        "created_at",
    ]

    # 搜索字段
    search_fields: ClassVar[list[str]] = [
        "original_filename",
        "case_number",
        "case__name",
    ]

    # 排序
    ordering: ClassVar[list[str]] = ["-created_at"]
    # 分页
    list_per_page = 20

    # 只读字段
    readonly_fields: ClassVar[list[str]] = [
        "id",
        "file_path",
        "original_filename",
        "status",
        "document_type",
        "case_number",
        "key_time",
        "confidence",
        "extraction_method",
        "raw_text_display",
        "renamed_file_path",
        "binding_success",
        "case",
        "case_log",
        "binding_message",
        "binding_error_code",
        "error_message",
        "notification_sent",
        "notification_sent_at",
        "notification_error",
        "notification_file_sent",
        "created_at",
        "started_at",
        "finished_at",
    ]

    # 字段分组
    fieldsets = (
        (
            _("基本信息"),
            {
                "fields": (
                    "id",
                    "original_filename",
                    "file_path",
                    "status",
                )
            },
        ),
        (
            _("识别结果"),
            {
                "fields": (
                    "document_type",
                    "case_number",
                    "key_time",
                    "confidence",
                    "extraction_method",
                    "renamed_file_path",
                )
            },
        ),
        (
            _("原始文本"),
            {
                "fields": ("raw_text_display",),
                "classes": ("collapse",),
            },
        ),
        (
            _("绑定结果"),
            {
                "fields": (
                    "binding_success",
                    "case",
                    "case_log",
                    "binding_message",
                    "binding_error_code",
                )
            },
        ),
        (
            _("通知状态"),
            {
                "fields": (
                    "notification_sent",
                    "notification_sent_at",
                    "notification_file_sent",
                    "notification_error",
                ),
                "description": "绑定成功后的飞书群通知状态",
            },
        ),
        (
            _("错误信息"),
            {
                "fields": ("error_message",),
                "classes": ("collapse",),
            },
        ),
        (
            _("时间戳"),
            {
                "fields": (
                    "created_at",
                    "started_at",
                    "finished_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def status_display(self, obj):
        """状态显示（带颜色）"""
        status_colors = {
            DocumentRecognitionStatus.PENDING: "orange",
            DocumentRecognitionStatus.PROCESSING: "blue",
            DocumentRecognitionStatus.SUCCESS: "green",
            DocumentRecognitionStatus.FAILED: "red",
        }
        color = status_colors.get(obj.status, "gray")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_display.short_description = _("任务状态")
    status_display.admin_order_field = "status"

    def document_type_display(self, obj):
        """文书类型显示"""
        if not obj.document_type:
            return "-"

        type_icons = {
            "summons": "📋",  # 传票
            "judgment": "⚖️",  # 判决书
            "ruling": "📜",  # 裁定书
            "notice": "📢",  # 通知书
            "unknown": "❓",  # 未知
        }
        icon = type_icons.get(obj.document_type, "📄")
        return f"{icon} {obj.document_type}"

    document_type_display.short_description = _("文书类型")
    document_type_display.admin_order_field = "document_type"

    def case_display(self, obj):
        """案件显示"""
        if obj.case:
            url = reverse("admin:cases_case_change", args=[obj.case.id])
            case_name = obj.case.name
            if len(case_name) > 30:
                case_name = case_name[:30] + "..."
            return format_html('<a href="{}" target="_blank">{}</a>', url, case_name)
        return "-"

    case_display.short_description = _("关联案件")

    def binding_status_display(self, obj):
        """绑定状态显示"""
        if obj.binding_success is None:
            return format_html('<span style="color: gray;">{}</span>', "- 未绑定")
        elif obj.binding_success:
            return format_html('<span style="color: green;">{}</span>', "✓ 绑定成功")
        else:
            error_preview = obj.binding_error_code or "未知错误"
            return format_html(
                '<span style="color: red;">✗ 绑定失败</span><br><small style="color: #d63384;">{}</small>',
                error_preview,
            )

    binding_status_display.short_description = _("绑定状态")

    def notification_status_display(self, obj):
        """
        通知状态显示

        Requirements: 5.1, 5.2, 5.3
        """
        if not obj.binding_success:
            return format_html('<span style="color: gray;">{}</span>', "- 无需通知")

        if obj.notification_sent:
            # 通知发送成功
            file_status = "✓ 文件已发送" if obj.notification_file_sent else "✗ 文件未发送"
            return format_html(
                '<span style="color: green;">✓ 通知成功</span><br><small style="color: #666;">{}</small>',
                file_status,
            )
        elif obj.notification_error:
            # 通知发送失败
            error_preview = obj.notification_error[:30] + ("..." if len(obj.notification_error) > 30 else "")
            return format_html(
                '<span style="color: red;">✗ 通知失败</span><br><small style="color: #d63384;">{}</small>',
                error_preview,
            )
        else:
            return format_html('<span style="color: orange;">{}</span>', "⏳ 待发送")

    notification_status_display.short_description = _("通知状态")

    def raw_text_display(self, obj):
        """原始文本显示（带滚动）"""
        if obj.raw_text:
            return format_html(
                '<div style="max-height: 300px; overflow-y: auto; '
                "white-space: pre-wrap; font-family: monospace; "
                'background: #f5f5f5; padding: 10px; border-radius: 4px;">{}</div>',
                obj.raw_text,
            )
        return "-"

    raw_text_display.short_description = _("原始文本")

    def get_queryset(self, request):
        """优化查询性能"""
        return super().get_queryset(request).select_related("case", "case_log")

    def has_add_permission(self, request):
        """禁止手动添加任务"""
        return False

    def has_change_permission(self, request, obj=None):
        """禁止修改任务"""
        return False

    def has_delete_permission(self, request, obj=None):
        """允许删除任务"""
        return True
