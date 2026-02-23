"""发票识别任务 Django Admin"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from apps.automation.models.invoice_recognition import (
    InvoiceRecognitionTask,
    InvoiceRecognitionTaskStatus,
)

logger = logging.getLogger("apps.automation")


@admin.register(InvoiceRecognitionTask)
class InvoiceRecognitionTaskAdmin(admin.ModelAdmin[InvoiceRecognitionTask]):
    """发票识别任务管理"""

    list_display = [
        "name",
        "status_display",
        "record_count",
        "total_amount_display",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["name"]
    ordering = ["-created_at"]
    readonly_fields = [
        "status",
        "created_by",
        "created_at",
        "finished_at",
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return True

    def has_change_permission(
        self, request: HttpRequest, obj: InvoiceRecognitionTask | None = None
    ) -> bool:
        return True

    def get_fields(  # type: ignore[override]
        self, request: HttpRequest, obj: InvoiceRecognitionTask | None = None
    ) -> list[str]:
        if obj is None:
            return ["name"]
        return ["name", "status", "created_by", "created_at", "finished_at"]

    def has_delete_permission(
        self, request: HttpRequest, obj: InvoiceRecognitionTask | None = None
    ) -> bool:
        return True

    def save_model(
        self,
        request: HttpRequest,
        obj: InvoiceRecognitionTask,
        form: Any,
        change: bool,
    ) -> None:
        if not change and obj.created_by_id is None:
            obj.created_by = request.user  # type: ignore[assignment]
        # 保存合并分组配置
        merge_config_raw = request.POST.get("merge_config", "")
        if merge_config_raw:
            import json
            try:
                obj.merge_config = json.loads(merge_config_raw)
            except (ValueError, TypeError):
                pass
        super().save_model(request, obj, form, change)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        extra: dict[str, Any] = extra_context or {}
        try:
            task = InvoiceRecognitionTask.objects.get(pk=object_id)
            grouped_data: dict[str, Any] = self._get_service().get_grouped_records(task.id)
            extra["invoice_task"] = task
            extra["invoice_grouped_data"] = grouped_data
        except InvoiceRecognitionTask.DoesNotExist:
            pass
        return super().change_view(request, object_id, form_url, extra_context=extra)

    def status_display(self, obj: InvoiceRecognitionTask) -> SafeString:
        """状态显示（带颜色）"""
        color_map: dict[str, str] = {
            InvoiceRecognitionTaskStatus.PENDING: "orange",
            InvoiceRecognitionTaskStatus.PROCESSING: "blue",
            InvoiceRecognitionTaskStatus.COMPLETED: "green",
            InvoiceRecognitionTaskStatus.FAILED: "red",
        }
        label_map: dict[str, str] = {
            InvoiceRecognitionTaskStatus.PENDING: str(_("待处理")),
            InvoiceRecognitionTaskStatus.PROCESSING: str(_("处理中")),
            InvoiceRecognitionTaskStatus.COMPLETED: str(_("已完成")),
            InvoiceRecognitionTaskStatus.FAILED: str(_("失败")),
        }
        color = color_map.get(obj.status, "gray")
        label = label_map.get(obj.status, obj.status)
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>', color, label
        )

    status_display.short_description = _("状态")  # type: ignore[attr-defined]

    def record_count(self, obj: InvoiceRecognitionTask) -> int:
        """发票数量"""
        return int(obj.records.count())

    record_count.short_description = _("发票数量")  # type: ignore[attr-defined]

    def total_amount_display(self, obj: InvoiceRecognitionTask) -> str:
        """非重复总金额"""
        try:
            amount: Decimal = self._get_service().get_total_amount(obj.id)
            return f"¥{amount}"
        except Exception as exc:
            logger.error("获取总金额失败: task_id=%s, error=%s", obj.id, exc)
            return "-"

    total_amount_display.short_description = _("非重复总金额")  # type: ignore[attr-defined]

    def _get_service(self) -> Any:
        from apps.automation.services.wiring import get_invoice_recognition_service

        return get_invoice_recognition_service()
