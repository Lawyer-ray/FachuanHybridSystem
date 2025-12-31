from django.contrib import admin
from django import forms
from django.forms.models import BaseInlineFormSet
from django.contrib.admin import ModelAdmin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponseRedirect
from django.urls import reverse

from ..models import Case, CaseParty, CaseAssignment, CaseLog, CaseLogAttachment, CaseStage, CaseNumber, SupervisingAuthority
from ..services.case_chat_service import CaseChatService
from ..exceptions import ChatProviderException
from apps.core.enums import ChatPlatform
from .case_chat_admin import CaseChatInline

try:
    import nested_admin
    BaseModelAdmin = nested_admin.NestedModelAdmin
    BaseStackedInline = nested_admin.NestedStackedInline
    BaseTabularInline = nested_admin.NestedTabularInline
except Exception:
    BaseModelAdmin = admin.ModelAdmin
    BaseStackedInline = admin.StackedInline
    BaseTabularInline = admin.TabularInline
from ..validators import normalize_stages


def _get_case_chat_service():
    """工厂函数获取案件群聊服务"""
    return CaseChatService()


def _get_case_admin_service():
    """工厂函数获取案件 Admin 服务"""
    from ..services.case_admin_service import CaseAdminService
    return CaseAdminService()


class CaseAdminForm(forms.ModelForm):
    current_stage = forms.ChoiceField(
        choices=[("", "---------")] + list(CaseStage.choices),
        required=False,
        label="当前阶段"
    )

    class Meta:
        model = Case
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        cur = cleaned.get("current_stage")
        contract = cleaned.get("contract")
        ctype = getattr(contract, "case_type", None) if contract else None
        rep = getattr(contract, "representation_stages", []) if contract else []
        try:
            _, cur2 = normalize_stages(ctype, rep, cur, strict=False)
            cleaned["current_stage"] = cur2
        except ValueError as e:
            code = str(e)
            if code == "invalid_cur":
                self.add_error("current_stage", "当前阶段不在可选范围内")
            elif code == "cur_not_in_rep":
                self.add_error("current_stage", "当前阶段必须在合同的代理阶段范围内")
        return cleaned


class CasePartyInlineForm(forms.ModelForm):
    """CaseParty Inline 表单，添加 CSS 类支持动态过滤"""
    
    class Meta:
        model = CaseParty
        fields = "__all__"
        widgets = {
            'client': forms.Select(attrs={
                'class': 'contract-party-client-select',
                'data-contract-party-filter': 'true',
            }),
        }


class CasePartyInline(BaseTabularInline):
    """
    案件当事人内联编辑组件
    
    支持动态过滤功能：
    - 当案件绑定合同时，client 选择框只显示合同及补充协议中的当事人
    - 当案件未绑定合同时，显示所有客户
    
    Requirements: 1.1, 1.2, 1.3
    """
    model = CaseParty
    form = CasePartyInlineForm
    extra = 1
    fields = ("client", "legal_status", "is_our_client_display")
    readonly_fields = ("is_our_client_display",)
    
    # CSS 类用于 JavaScript 选择器
    classes = ['contract-party-inline']

    class UniqueClientInlineFormSet(BaseInlineFormSet):
        def clean(self):
            super().clean()
            seen = set()
            case = getattr(self, "instance", None)
            existing = set()
            if case and case.pk:
                from ..models import CaseParty
                existing = set(CaseParty.objects.filter(case=case).values_list("client_id", flat=True))
            for form in self.forms:
                if not hasattr(form, "cleaned_data"):
                    continue
                if form.cleaned_data.get("DELETE"):
                    continue
                client = form.cleaned_data.get("client")
                if not client:
                    continue
                cid = client.pk
                if cid in seen:
                    form.add_error("client", "同一案件中当事人只能出现一次")
                else:
                    seen.add(cid)
                if cid in existing and not form.instance.pk:
                    form.add_error("client", "该当事人已存在于此案件")

    formset = UniqueClientInlineFormSet

    def is_our_client_display(self, obj):
        if obj and getattr(obj, "client", None):
            return bool(getattr(obj.client, "is_our_client", False))
        return None

    is_our_client_display.boolean = True
    is_our_client_display.short_description = "是否为我方当事人"

    class Media:
        js = (
            "cases/admin_caseparty.js",
            "cases/admin_case_form.js",
        )
        css = {
            'all': ('cases/admin_caseparty.css',)
        }


class CaseAssignmentInline(BaseTabularInline):
    model = CaseAssignment
    extra = 1


class SupervisingAuthorityInline(BaseTabularInline):
    """主管机关内联"""
    model = SupervisingAuthority
    extra = 1
    fields = ("name", "authority_type")


class CaseLogAttachmentInline(BaseTabularInline):
    model = CaseLogAttachment
    extra = 0


class CaseNumberInline(BaseTabularInline):
    model = CaseNumber
    extra = 1
    fields = ("number", "remarks")


class CaseLogInline(BaseStackedInline):
    model = CaseLog
    extra = 0
    fields = ("content", "reminder_type", "reminder_time")
    exclude = ("actor",)
    readonly_fields = ()
    show_change_link = True

    if BaseModelAdmin is not admin.ModelAdmin:
        inlines = [CaseLogAttachmentInline]


@admin.register(Case)
class CaseAdmin(BaseModelAdmin):
    form = CaseAdminForm
    list_display = ("id", "name", "status", "start_date", "effective_date", "is_archived")
    list_filter = ("status", "is_archived")
    search_fields = ("name",)
    change_form_template = "admin/cases/case/change_form.html"
    
    actions = ['create_feishu_chat_for_selected_cases']

    class Media:
        js = ("cases/admin_case_form.js",)

    inlines = [CasePartyInline, CaseAssignmentInline, SupervisingAuthorityInline, CaseNumberInline, CaseLogInline, CaseChatInline]

    def response_change(self, request, obj):
        """处理保存并复制按钮"""
        if "_save_and_duplicate" in request.POST:
            try:
                service = _get_case_admin_service()
                new_case = service.duplicate_case(obj.pk)
                messages.success(request, f"已复制案件，正在编辑新案件: {new_case.name}")
                return HttpResponseRedirect(
                    reverse("admin:cases_case_change", args=[new_case.pk])
                )
            except Exception as e:
                messages.error(request, f"复制失败: {str(e)}")
                return HttpResponseRedirect(request.path)
        return super().response_change(request, obj)

    def create_feishu_chat_for_selected_cases(self, request, queryset):
        """为选中的案件创建飞书群聊"""
        service = _get_case_chat_service()
        success_count = 0
        error_count = 0
        
        for case in queryset:
            try:
                # 检查是否已存在飞书群聊
                existing_chat = case.chats.filter(
                    platform=ChatPlatform.FEISHU,
                    is_active=True
                ).first()
                
                if existing_chat:
                    messages.warning(
                        request,
                        f"案件 {case.name} 已存在飞书群聊: {existing_chat.name}"
                    )
                    continue
                
                # 创建群聊
                chat = service.create_chat_for_case(case.id, ChatPlatform.FEISHU)
                success_count += 1
                
                messages.success(
                    request,
                    f"成功为案件 {case.name} 创建飞书群聊: {chat.name}"
                )
                
            except ChatProviderException as e:
                error_count += 1
                messages.error(
                    request,
                    f"为案件 {case.name} 创建飞书群聊失败: {str(e)}"
                )
            except Exception as e:
                error_count += 1
                messages.error(
                    request,
                    f"为案件 {case.name} 创建群聊时发生未知错误: {str(e)}"
                )
        
        if success_count > 0:
            messages.success(
                request,
                f"总计成功创建 {success_count} 个飞书群聊"
            )
        
        if error_count > 0:
            messages.error(
                request,
                f"总计 {error_count} 个案件创建群聊失败"
            )
    
    create_feishu_chat_for_selected_cases.short_description = _("为选中案件创建飞书群聊")

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, CaseLog) and not getattr(obj, "actor_id", None):
                obj.actor_id = getattr(request.user, "id", None)
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            try:
                obj.delete()
            except Exception:
                pass
