"""客户回款记录 Admin 配置"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import ClientPaymentRecord

if TYPE_CHECKING:
    pass


class ClientPaymentRecordAdminForm(forms.ModelForm[ClientPaymentRecord]):
    """客户回款记录表单"""

    image = forms.ImageField(
        required=False,
        label=_("上传凭证图片"),
        help_text=_("支持 JPG、PNG、JPEG，最大 10MB"),
    )

    class Meta:
        model = ClientPaymentRecord
        fields = ("contract", "cases", "amount", "image", "note")
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3, "cols": 40}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # 动态过滤案件选项：只显示所选合同的案件
        if self.instance and self.instance.contract_id:
            from apps.cases.models import Case

            self.fields["cases"].queryset = Case.objects.filter(contract_id=self.instance.contract_id)
        else:
            from apps.cases.models import Case

            self.fields["cases"].queryset = Case.objects.none()

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        contract = cleaned_data.get("contract")
        cases = cleaned_data.get("cases")

        # 验证案件归属
        if contract and cases:
            from apps.contracts.services.client_payment import ClientPaymentRecordService

            service = ClientPaymentRecordService()
            case_ids = [case.id for case in cases]
            if not service.validate_cases_belong_to_contract(contract.id, case_ids):
                raise forms.ValidationError(_("所选案件不属于该合同"))

        return cleaned_data

    def save(self, commit: bool = True) -> ClientPaymentRecord:
        instance = super().save(commit=False)
        uploaded_file = self.cleaned_data.get("image")

        if uploaded_file:
            from apps.contracts.services.client_payment import ClientPaymentImageService

            image_service = ClientPaymentImageService()
            # 如果是新建，先保存实例以获取 ID
            if not instance.pk:
                instance.save()
                self.save_m2m()

            # 删除旧图片
            if instance.image_path:
                image_service.delete_image(instance.image_path)

            # 保存新图片
            image_path = image_service.save_image(uploaded_file, instance.id)
            instance.image_path = image_path

        if commit:
            instance.save()
            if not uploaded_file:
                self.save_m2m()

        return instance


@admin.register(ClientPaymentRecord)
class ClientPaymentRecordAdmin(admin.ModelAdmin[ClientPaymentRecord]):
    """客户回款记录 Admin"""

    form = ClientPaymentRecordAdminForm
    list_display = ("id", "contract", "get_cases_display", "amount", "created_at")
    list_filter = ("contract", "created_at")
    search_fields = ("contract__name", "note")
    autocomplete_fields = ("contract",)
    filter_horizontal = ("cases",)
    readonly_fields = ("created_at", "image_preview")
    fieldsets: ClassVar = (
        (
            None,
            {
                "fields": ("contract", "cases", "amount", "note"),
            },
        ),
        (
            _("凭证图片"),
            {
                "fields": ("image", "image_preview"),
            },
        ),
        (
            _("系统信息"),
            {
                "fields": ("created_at",),
            },
        ),
    )

    @admin.display(description=_("关联案件"))
    def get_cases_display(self, obj: ClientPaymentRecord) -> str:
        """展示关联案件"""
        if not obj.pk:
            return "-"
        cases = obj.cases.all()
        if not cases:
            return "-"
        return ", ".join([case.name for case in cases[:3]]) + ("..." if cases.count() > 3 else "")

    @admin.display(description=_("图片预览"))
    def image_preview(self, obj: ClientPaymentRecord) -> str:
        """展示图片预览"""
        if not obj.pk or not obj.image_path:
            return "-"

        from apps.contracts.services.client_payment import ClientPaymentImageService

        image_service = ClientPaymentImageService()
        url = image_service.get_image_url(obj.image_path)
        return format_html(
            '<a href="{}" target="_blank"><img src="{}" style="max-width:200px;max-height:200px;" /></a>',
            url,
            url,
        )

    def get_queryset(self, request: HttpRequest) -> QuerySet[ClientPaymentRecord, ClientPaymentRecord]:
        """优化查询"""
        return super().get_queryset(request).select_related("contract").prefetch_related("cases")

    def save_model(self, request: HttpRequest, obj: ClientPaymentRecord, form: Any, change: bool) -> None:
        """保存模型时调用 Service 层验证"""
        from apps.contracts.services.client_payment import ClientPaymentRecordService

        service = ClientPaymentRecordService()

        if not change:
            # 新建：通过 Service 创建
            case_ids = [case.id for case in form.cleaned_data.get("cases", [])]
            created = service.create_payment_record(
                contract_id=obj.contract_id,
                amount=obj.amount,
                case_ids=case_ids if case_ids else None,
                note=obj.note or "",
            )
            # 更新实例 ID
            obj.pk = created.pk
            obj.id = created.id
        else:
            # 更新：通过 Service 更新
            case_ids = [case.id for case in form.cleaned_data.get("cases", [])]
            service.update_payment_record(
                record_id=obj.id,
                amount=obj.amount,
                case_ids=case_ids,
                note=obj.note,
            )

    def delete_model(self, request: HttpRequest, obj: ClientPaymentRecord) -> None:
        """删除模型时调用 Service 层"""
        from apps.contracts.services.client_payment import ClientPaymentRecordService

        service = ClientPaymentRecordService()
        service.delete_payment_record(obj.id)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[ClientPaymentRecord, ClientPaymentRecord]) -> None:
        """批量删除时调用 Service 层"""
        from apps.contracts.services.client_payment import ClientPaymentRecordService

        service = ClientPaymentRecordService()
        for obj in queryset:
            service.delete_payment_record(obj.id)

    class Media:
        js = ("admin/js/jquery.init.js",)
