from django.contrib import admin
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponseRedirect
from django.urls import reverse
from django import forms
from ..models import (
    Contract, ContractParty, ContractReminder, ContractAssignment,
    SupplementaryAgreement, SupplementaryAgreementParty
)
from apps.core.enums import CaseStage
try:
    import nested_admin
    BaseModelAdmin = nested_admin.NestedModelAdmin
    BaseStackedInline = nested_admin.NestedStackedInline
    BaseTabularInline = nested_admin.NestedTabularInline
except Exception:
    BaseModelAdmin = admin.ModelAdmin
    BaseStackedInline = admin.StackedInline
    BaseTabularInline = admin.TabularInline


def _get_contract_admin_service():
    """工厂函数获取合同 Admin 服务"""
    from ..services.contract_admin_service import ContractAdminService
    return ContractAdminService()


class ContractPartyInline(BaseTabularInline):
    model = ContractParty
    extra = 1
    fields = ("client", "role")
    show_change_link = True


class ContractReminderInline(BaseTabularInline):
    model = ContractReminder
    extra = 1
    fields = ("kind", "content", "due_date")


class ContractAssignmentInline(BaseTabularInline):
    model = ContractAssignment
    extra = 1
    fields = ("lawyer", "is_primary", "order")
    autocomplete_fields = ["lawyer"]


class SupplementaryAgreementPartyInline(BaseTabularInline):
    """补充协议当事人内联（嵌套在补充协议中）"""
    model = SupplementaryAgreementParty
    extra = 1
    fields = ("client", "role")
    autocomplete_fields = ["client"]


class SupplementaryAgreementInline(BaseStackedInline):
    """补充协议内联（在合同中）"""
    model = SupplementaryAgreement
    extra = 0
    fields = ("name",)
    show_change_link = True


# 如果支持嵌套 Admin，添加当事人内联到补充协议
if BaseModelAdmin is not admin.ModelAdmin:
    SupplementaryAgreementInline.inlines = [SupplementaryAgreementPartyInline]


@admin.register(Contract)
class ContractAdmin(BaseModelAdmin):
    class ContractAdminForm(forms.ModelForm):
        representation_stages = forms.MultipleChoiceField(
            choices=CaseStage.choices,
            required=False,
            widget=forms.SelectMultiple,
            label="代理阶段",
        )
        class Meta:
            from ..models import Contract
            model = Contract
            fields = """__all__"""
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not getattr(self.instance, "pk", None):
                from apps.cases.models import CaseStatus
                self.fields["status"].initial = CaseStatus.ACTIVE
                self.fields["specified_date"].initial = timezone.localdate()
            # 初始化多选值
            self.fields["representation_stages"].initial = list(getattr(self.instance, "representation_stages", []) or [])

        def clean(self):
            cleaned = super().clean()
            try:
                from apps.cases.validators import normalize_stages
                ctype = cleaned.get("case_type")
                rep = cleaned.get("representation_stages") or []
                rep2, _ = normalize_stages(ctype, rep, None, strict=False)
                cleaned["representation_stages"] = rep2
            except Exception:
                pass
            return cleaned

    form = ContractAdminForm
    list_display = ("id", "name", "case_type", "status", "start_date", "end_date", "get_primary_lawyer", "fee_mode", "fixed_amount", "risk_rate", "is_archived")
    list_filter = ("case_type", "status", "fee_mode", "is_archived")
    search_fields = ("name",)
    readonly_fields = ("get_primary_lawyer_display",)
    
    def get_primary_lawyer(self, obj):
        """显示主办律师"""
        lawyer = obj.primary_lawyer
        if lawyer:
            return lawyer.real_name or lawyer.username
        return "-"
    get_primary_lawyer.short_description = "主办律师"
    
    def get_primary_lawyer_display(self, obj):
        """详情页显示主办律师（只读）"""
        lawyer = obj.primary_lawyer
        if lawyer:
            name = lawyer.real_name or lawyer.username
            return f"{name} (ID: {lawyer.id})"
        return "无"
    get_primary_lawyer_display.short_description = "主办律师"

    inlines = [
        ContractPartyInline,
        ContractAssignmentInline,
        SupplementaryAgreementInline,
        ContractReminderInline,
    ]

    class Media:
        js = ("cases/admin_case_form.js",)

    change_form_template = "admin/contracts/contract/change_form.html"

    def response_change(self, request, obj):
        """处理保存并复制、保存并创建案件按钮"""
        if "_save_and_duplicate" in request.POST:
            try:
                service = _get_contract_admin_service()
                new_contract = service.duplicate_contract(obj.pk)
                messages.success(request, f"已复制合同，正在编辑新合同: {new_contract.name}")
                return HttpResponseRedirect(
                    reverse("admin:contracts_contract_change", args=[new_contract.pk])
                )
            except Exception as e:
                messages.error(request, f"复制失败: {str(e)}")
                return HttpResponseRedirect(request.path)
        
        if "_save_and_create_case" in request.POST:
            try:
                service = _get_contract_admin_service()
                new_case = service.create_case_from_contract(obj.pk)
                messages.success(request, f"已创建案件: {new_case.name}")
                return HttpResponseRedirect(
                    reverse("admin:cases_case_change", args=[new_case.pk])
                )
            except Exception as e:
                messages.error(request, f"创建案件失败: {str(e)}")
                return HttpResponseRedirect(request.path)
        
        return super().response_change(request, obj)

    def response_add(self, request, obj, post_url_continue=None):
        """处理新建合同后的保存并创建案件按钮"""
        if "_save_and_create_case" in request.POST:
            try:
                service = _get_contract_admin_service()
                new_case = service.create_case_from_contract(obj.pk)
                messages.success(request, f"已创建案件: {new_case.name}")
                return HttpResponseRedirect(
                    reverse("admin:cases_case_change", args=[new_case.pk])
                )
            except Exception as e:
                messages.error(request, f"创建案件失败: {str(e)}")
                return HttpResponseRedirect(
                    reverse("admin:contracts_contract_change", args=[obj.pk])
                )
        
        return super().response_add(request, obj, post_url_continue)
