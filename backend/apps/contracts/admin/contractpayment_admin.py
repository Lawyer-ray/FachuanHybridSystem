from django.contrib import admin
from django.forms.models import BaseInlineFormSet
from ..models import ContractPayment, InvoiceStatus
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

    def get_formset(self, request, obj=None, **kwargs):
        FormSet = super().get_formset(request, obj, **kwargs)
        def clean_fs(self):
            super(FormSet, self).clean()
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
        FormSet.clean = clean_fs
        return FormSet


@admin.register(ContractPayment)
class ContractPaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "contract", "amount", "received_at", "invoice_status", "invoiced_amount")
    list_filter = ("invoice_status", "received_at")
    search_fields = ("contract__name",)
    autocomplete_fields = ("contract",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("contract")
