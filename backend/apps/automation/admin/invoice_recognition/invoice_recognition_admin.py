"""Legacy invoice recognition admin compatibility layer."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import reverse

from apps.automation.models.invoice_recognition import InvoiceRecognitionTask


@admin.register(InvoiceRecognitionTask)
class InvoiceRecognitionTaskAdmin(admin.ModelAdmin[InvoiceRecognitionTask]):
    """兼容旧 admin URL，重定向到独立 app。"""

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponseRedirect:
        return HttpResponseRedirect(reverse("admin:invoice_recognition_invoicerecognitiontask_changelist"))

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponseRedirect:
        return HttpResponseRedirect(
            reverse("admin:invoice_recognition_invoicerecognitiontask_change", args=[object_id]),
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: InvoiceRecognitionTask | None = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: InvoiceRecognitionTask | None = None) -> bool:
        return False

    def get_model_perms(self, request: HttpRequest) -> dict[str, bool]:
        return {}

