from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import ContractPayment, Invoice, InvoiceStatus

if TYPE_CHECKING:
    BaseModelAdmin = admin.ModelAdmin
    BaseTabularInline = admin.TabularInline
else:
    try:
        import nested_admin

        BaseModelAdmin = nested_admin.NestedModelAdmin
        BaseTabularInline = nested_admin.NestedTabularInline
    except ImportError:
        BaseModelAdmin = admin.ModelAdmin
        BaseTabularInline = admin.TabularInline


class InvoiceAdminForm(forms.ModelForm[Invoice]):
    file = forms.FileField(
        required=False,
        label=_("上传发票"),
        help_text=_("支持 PDF、JPG、JPEG、PNG，最大 20MB"),
    )

    class Meta:
        model = Invoice
        fields = (
            "file",
            "original_filename",
            "invoice_code",
            "invoice_number",
            "invoice_date",
            "amount",
            "tax_amount",
            "total_amount",
            "remark",
        )
        widgets = {
            "remark": forms.Textarea(attrs={"rows": 2, "cols": 20, "style": "width:160px;resize:vertical;"}),
        }

    def save(self, commit: bool = True) -> Invoice:
        instance = super().save(commit=False)
        uploaded_file = self.cleaned_data.get("file")
        if uploaded_file:
            from apps.contracts.admin.wiring_admin import get_invoice_upload_service

            svc = get_invoice_upload_service()
            payment_id: int = instance.payment_id or self.instance.payment_id
            saved = svc.save_invoice_file(uploaded_file, payment_id)
            instance.file_path = saved.file_path
            instance.original_filename = saved.original_filename
            # 文件已由 service 创建记录，直接返回
            return saved
        if commit:
            instance.save()
        return instance


class InvoiceInline(BaseTabularInline):  # type: ignore[type-arg]
    model = Invoice
    form = InvoiceAdminForm
    extra = 1
    fields: ClassVar = (
        "file",
        "file_link",
        "total_amount",
    )
    readonly_fields: ClassVar = ("file_link",)

    # 隐藏 verbose_name_plural，避免显示识别结果
    verbose_name = _("发票")
    verbose_name_plural = _("发票")

    @admin.display(description=_("查看文件"))
    def file_link(self, obj: Invoice) -> str:
        if not obj.pk or not obj.file_path:
            return "-"
        from django.conf import settings

        # 确保 file_path 不为空字符串
        if not obj.file_path.strip():
            return "-"

        url = f"{settings.MEDIA_URL}{obj.file_path}"
        return format_html('<a href="{}" target="_blank">{}</a>', url, obj.original_filename or _("查看"))

    def delete_model(self, request: HttpRequest, obj: Invoice) -> None:
        from apps.contracts.admin.wiring_admin import get_invoice_upload_service

        svc = get_invoice_upload_service()
        try:
            svc.delete_invoice(obj.pk)
        except Exception:
            # 即使 service 抛出，也确保 Admin 不崩溃
            obj.delete()


class ContractPaymentInline(BaseTabularInline[ContractPayment, ContractPayment]):
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
                        form.add_error("invoiced_amount", _("开票金额不能大于收款金额"))
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
class ContractPaymentAdmin(BaseModelAdmin[ContractPayment]):  # type: ignore[type-arg]
    change_form_template = "admin/contracts/contractpayment/change_form.html"
    list_display = ("id", "contract", "amount", "received_at", "invoice_status", "invoiced_amount")
    list_filter = ("invoice_status", "received_at")
    search_fields = ("contract__name",)
    autocomplete_fields = ("contract",)
    inlines: ClassVar = [InvoiceInline]

    class Media:
        css = {"all": ("contracts/css/invoice_recognition.css",)}
        js = ("contracts/js/invoice_recognition.js",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[ContractPayment, ContractPayment]:
        return super().get_queryset(request).select_related("contract")
