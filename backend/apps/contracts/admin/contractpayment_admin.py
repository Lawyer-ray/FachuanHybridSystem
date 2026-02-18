from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.contracts.models import ContractPayment, InvoiceStatus

if TYPE_CHECKING:
    BaseModelAdmin = admin.ModelAdmin
    BaseTabularInline = admin.TabularInline
else:
    try:
        import nested_admin

        BaseModelAdmin = nested_admin.NestedModelAdmin
        BaseTabularInline = nested_admin.NestedTabularInline
    except Exception:
        BaseModelAdmin = admin.ModelAdmin
        BaseTabularInline = admin.TabularInline


class ContractPaymentInline(BaseTabularInline):
    model = ContractPayment
    extra = 0
    fields = ("amount", "received_at", "invoiced_amount", "invoice_status", "note")

    def get_formset(self, request: HttpRequest, obj: Any = None, **kwargs: Any) -> Any:
        FormSet = super().get_formset(request, obj, **kwargs)

        original_clean = FormSet.clean

        def clean_fs(self: Any) -> None:
            original_clean(self)
            for form in self.forms:
                if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                    continue
                amt = form.cleaned_data.get("amount")
                inv = form.cleaned_data.get("invoiced_amount") or 0
                if amt and inv is not None:
                    if float(inv) - float(amt) > 1e-6:
                        form.add_error("invoiced_amount", "开票金额不能大于收款金额")
                    else:
                        if float(inv) == 0:
                            form.cleaned_data["invoice_status"] = InvoiceStatus.UNINVOICED
                        elif 0 < float(inv) < float(amt):
                            form.cleaned_data["invoice_status"] = InvoiceStatus.INVOICED_PARTIAL
                        else:
                            form.cleaned_data["invoice_status"] = InvoiceStatus.INVOICED_FULL

        FormSet.clean = clean_fs  # type: ignore[method-assign]
        return FormSet


@admin.register(ContractPayment)
class ContractPaymentAdmin(admin.ModelAdmin[ContractPayment]):
    list_display = ("id", "contract", "amount", "received_at", "invoice_status", "invoiced_amount")
    list_filter = ("invoice_status", "received_at")
    search_fields = ("contract__name",)
    autocomplete_fields = ("contract",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[ContractPayment, ContractPayment]:
        return super().get_queryset(request).select_related("contract")
