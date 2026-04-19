from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Final

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeData
from django.utils.translation import gettext as _
from apps.core.tasking import submit_task

from apps.express_query.models import ExpressCarrierType, ExpressQueryTask, ExpressQueryTaskStatus, ExpressQueryTool

logger = logging.getLogger("apps.express_query")

# 运单号正则（与 TrackingExtractionService 保持一致）
_SF_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<![A-Z0-9])SF\d{10,20}(?![A-Z0-9])", re.IGNORECASE)
_EMS_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<!\d)\d{13}(?!\d)")


@admin.register(ExpressQueryTool)
class ExpressQueryToolAdmin(admin.ModelAdmin[ExpressQueryTool]):
    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> TemplateResponse | HttpResponse:
        if request.method == "POST":
            return self._handle_post(request)

        context = {
            **self.admin_site.each_context(request),
            "title": _("快递查询上传"),
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "task_list_url": reverse("admin:express_query_expressquerytask_changelist"),
        }
        return TemplateResponse(request, "admin/express_query/workbench.html", context)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: ExpressQueryTool | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: ExpressQueryTool | None = None) -> bool:
        return False

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        return {"view": True}

    def _handle_post(self, request: HttpRequest) -> HttpResponseRedirect:
        """处理POST请求：支持文件上传和手动输入运单号"""
        # 判断是文件上传还是手动输入
        tracking_number = str(request.POST.get("tracking_number", "")).strip().upper()
        carrier_type_raw = str(request.POST.get("carrier_type", "")).strip()

        if tracking_number and carrier_type_raw:
            # 手动输入模式
            return self._handle_manual_input(
                request=request,
                title=str(request.POST.get("title", "")).strip(),
                carrier_type=carrier_type_raw,
                tracking_number=tracking_number,
            )
        else:
            # 文件上传模式
            return self._handle_upload(request)

    def _handle_manual_input(
        self,
        request: HttpRequest,
        title: str,
        carrier_type: str,
        tracking_number: str,
    ) -> HttpResponseRedirect:
        """处理手动输入运单号"""
        # 校验承运商
        if carrier_type not in {ExpressCarrierType.SF, ExpressCarrierType.EMS}:
            self.message_user(request, _("不支持的承运商，仅允许顺丰(SF)和EMS(EMS)。"), level=messages.ERROR)
            return HttpResponseRedirect(request.path)

        # 校验运单号格式
        if carrier_type == ExpressCarrierType.SF and not _SF_PATTERN.match(tracking_number):
            self.message_user(
                request,
                _("顺丰单号格式错误：应为 SF 开头 + 10~20 位数字（如 SF1569188465678）。"),
                level=messages.ERROR,
            )
            return HttpResponseRedirect(request.path)

        if carrier_type == ExpressCarrierType.EMS and not _EMS_PATTERN.match(tracking_number):
            self.message_user(
                request,
                _("EMS 单号格式错误：应为 13 位纯数字（如 1313351023914）。"),
                level=messages.ERROR,
            )
            return HttpResponseRedirect(request.path)

        # 创建任务（无上传文件）
        task = ExpressQueryTask(title=title or f"{carrier_type.upper()}-{tracking_number}")
        if request.user.is_authenticated:
            task.created_by = request.user

        # 直接设置承运商和运单号（跳过OCR）
        task.carrier_type = carrier_type
        task.tracking_number = tracking_number
        task.ocr_text = _("手动输入运单号")
        task.status = ExpressQueryTaskStatus.QUERYING  # 跳过OCR，直接进入查询状态
        task.save()

        # 入队执行浏览器查询
        queue_task_id = str(submit_task("apps.express_query.tasks.execute_manual_express_query_task", task.id))
        task.queue_task_id = queue_task_id
        task.save(update_fields=["queue_task_id", "updated_at"])

        logger.info(
            "快递查询任务已创建（手动输入）",
            extra={
                "task_id": task.id,
                "queue_task_id": queue_task_id,
                "carrier_type": carrier_type,
                "tracking_number": tracking_number,
            },
        )

        self.message_user(
            request,
            _("任务已创建并进入队列：%s-%s") % (carrier_type.upper(), tracking_number),
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:express_query_expressquerytask_changelist"))

    def _handle_upload(self, request: HttpRequest) -> HttpResponseRedirect:
        """处理文件上传"""
        upload_file = request.FILES.get("waybill_file")
        title = str(request.POST.get("title", "")).strip()

        if upload_file is None:
            self.message_user(request, _("请先选择要上传的文件。"), level=messages.ERROR)
            return HttpResponseRedirect(request.path)

        file_name = upload_file.name or ""
        if not file_name:
            self.message_user(request, _("上传文件名无效。"), level=messages.ERROR)
            return HttpResponseRedirect(request.path)

        extension = Path(file_name).suffix.lower()
        allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
        if extension not in allowed_extensions:
            self.message_user(request, _("仅支持 PDF、PNG、JPG、JPEG、WEBP 文件。"), level=messages.ERROR)
            return HttpResponseRedirect(request.path)

        task = ExpressQueryTask(title=title, waybill_image=upload_file)
        if request.user.is_authenticated:
            task.created_by = request.user
        task.save()

        queue_task_id = str(async_task("apps.express_query.tasks.execute_express_query_task", task.id))
        task.queue_task_id = queue_task_id
        task.save(update_fields=["queue_task_id", "updated_at"])

        logger.info("快递查询任务已创建并入队", extra={"task_id": task.id, "queue_task_id": queue_task_id})
        self.message_user(request, _("上传成功，任务已创建并进入队列。"), level=messages.SUCCESS)
        return HttpResponseRedirect(reverse("admin:express_query_expressquerytask_changelist"))


@admin.register(ExpressQueryTask)
class ExpressQueryTaskAdmin(admin.ModelAdmin[ExpressQueryTask]):
    list_display = (
        "id",
        "title",
        "status_colored",
        "carrier_type",
        "tracking_number",
        "result_pdf_link",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "carrier_type", "created_at")
    search_fields = ("title", "tracking_number", "ocr_text", "error_message")
    readonly_fields = (
        "title",
        "waybill_image_link",
        "status",
        "carrier_type",
        "tracking_number",
        "ocr_text_display",
        "query_url_link",
        "result_pdf_link",
        "result_payload",
        "queue_task_id",
        "error_message",
        "created_by",
        "created_at",
        "started_at",
        "finished_at",
        "updated_at",
    )
    fieldsets = (
        (_("上传信息"), {"fields": ("title", "waybill_image_link")}),
        (_("识别与查询结果"), {"fields": ("status", "carrier_type", "tracking_number", "ocr_text_display")}),
        (_("任务详情"), {"fields": ("query_url_link", "result_pdf_link", "result_payload", "queue_task_id")}),
        (_("错误信息"), {"fields": ("error_message",), "classes": ("collapse",)}),
        (_("时间信息"), {"fields": ("created_by", "created_at", "started_at", "finished_at", "updated_at")}),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: ExpressQueryTask | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: ExpressQueryTask | None = None) -> bool:
        return True

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        actions = super().get_actions(request)
        # 仅保留删除操作，移除其他批量操作
        if "delete_selected" in actions:
            return {"delete_selected": actions["delete_selected"]}
        return {}

    @admin.display(description=_("状态"))
    def status_colored(self, obj: ExpressQueryTask) -> SafeData:
        color_map: dict[str, str] = {
            "pending": "#ff9800",
            "ocr_parsing": "#8e24aa",
            "waiting_login": "#1e88e5",
            "querying": "#3949ab",
            "success": "#2e7d32",
            "failed": "#d32f2f",
        }
        color = color_map.get(obj.status, "#616161")
        return format_html('<span style="color:{};font-weight:700;">{}</span>', color, obj.status)

    @admin.display(description=_("邮单文件"))
    def waybill_image_link(self, obj: ExpressQueryTask) -> SafeData | str:
        if not obj.waybill_image:
            return "-"
        return format_html('<a href="{}" target="_blank">{}</a>', obj.waybill_image.url, obj.waybill_image.name)

    @admin.display(description=_("OCR 文本"))
    def ocr_text_display(self, obj: ExpressQueryTask) -> SafeData | str:
        if not obj.ocr_text:
            return "-"
        return format_html(
            '<div style="max-height:280px;overflow:auto;white-space:pre-wrap;'
            'background:#f5f5f5;padding:8px 10px;border-radius:4px;">{}</div>',
            obj.ocr_text,
        )

    @admin.display(description=_("查询URL"))
    def query_url_link(self, obj: ExpressQueryTask) -> SafeData | str:
        if not obj.query_url:
            return "-"
        return format_html('<a href="{}" target="_blank">{}</a>', obj.query_url, obj.query_url)

    @admin.display(description=_("结果 PDF"))
    def result_pdf_link(self, obj: ExpressQueryTask) -> SafeData | str:
        if not obj.result_pdf:
            return "-"
        return format_html('<a href="{}" target="_blank">{}</a>', obj.result_pdf.url, obj.result_pdf.name)

    def get_queryset(self, request: HttpRequest) -> QuerySet[ExpressQueryTask]:
        return super().get_queryset(request).select_related("created_by")
