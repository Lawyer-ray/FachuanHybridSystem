from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, ClassVar

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.forms import ModelForm
from django.forms.models import BaseInlineFormSet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.cases.admin.case_chat_admin import CaseChatInline
from apps.cases.admin.case_forms_admin import CaseAdminForm
from apps.cases.exceptions import ChatProviderException
from apps.cases.models import (
    Case,
    CaseAssignment,
    CaseLog,
    CaseLogAttachment,
    CaseNumber,
    CaseParty,
    CaseStage,
    SupervisingAuthority,
)
from apps.cases.services.case_chat_service import CaseChatService
from apps.cases.admin.mixins import CaseAdminViewsMixin
from apps.core.enums import ChatPlatform

if TYPE_CHECKING:
    BaseModelAdmin = admin.ModelAdmin
    BaseStackedInline = admin.StackedInline
    BaseTabularInline = admin.TabularInline
else:
    try:
        import nested_admin

        BaseModelAdmin = nested_admin.NestedModelAdmin
        BaseStackedInline = nested_admin.NestedStackedInline
        BaseTabularInline = nested_admin.NestedTabularInline
    except Exception:
        BaseModelAdmin = admin.ModelAdmin
        BaseStackedInline = admin.StackedInline
        BaseTabularInline = admin.TabularInline


def _get_case_chat_service() -> CaseChatService:
    """工厂函数获取案件群聊服务"""
    return CaseChatService()


def _get_case_admin_service() -> Any:
    """工厂函数获取案件 Admin 服务"""
    from apps.cases.services.case_admin_service import CaseAdminService

    return CaseAdminService()


class CasePartyInline(BaseTabularInline):
    """案件当事人内联编辑组件"""

    model = CaseParty
    extra = 1
    fields = ("client", "legal_status")
    classes = ["contract-party-inline"]

    class Media:
        js = (
            "cases/admin_caseparty.js",
            "cases/admin_case_form.js",
        )
        css: ClassVar[dict[str, tuple[str, ...]]] = {"all": ("cases/admin_caseparty.css",)}


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
    readonly_fields = ("reminder_type", "reminder_time")
    show_change_link = True

    if BaseModelAdmin is not admin.ModelAdmin:
        inlines = [CaseLogAttachmentInline]


@admin.register(Case)
class CaseAdmin(CaseAdminViewsMixin, BaseModelAdmin):
    form = CaseAdminForm
    list_display = ("id", "name", "status", "start_date", "effective_date", "is_archived")
    list_filter = ("status", "is_archived")
    search_fields = ("name",)
    change_form_template = "admin/cases/case/change_form.html"
    readonly_fields = ("filing_number",)

    actions = ["create_feishu_chat_for_selected_cases"]

    class Media:
        js = ("cases/admin_case_form.js",)

    inlines = [
        CasePartyInline,
        CaseAssignmentInline,
        SupervisingAuthorityInline,
        CaseNumberInline,
        CaseLogInline,
        CaseChatInline,
    ]

    def response_change(self, request: HttpRequest, obj: Case) -> HttpResponse:
        """处理保存并复制按钮"""
        if "_save_and_duplicate" in request.POST:
            try:
                service = _get_case_admin_service()
                new_case = service.duplicate_case(obj.pk)
                messages.success(request, f"已复制案件，正在编辑新案件: {new_case.name}")
                return HttpResponseRedirect(reverse("admin:cases_case_change", args=[new_case.pk]))
            except Exception as e:
                messages.error(request, f"复制失败: {e!s}")
                return HttpResponseRedirect(request.path)
        return super().response_change(request, obj)

    def create_feishu_chat_for_selected_cases(self, request: HttpRequest, queryset: QuerySet[Case, Case]) -> None:
        """为选中的案件创建飞书群聊"""
        service = _get_case_chat_service()
        success_count = 0
        error_count = 0

        for case in queryset:
            try:
                existing_chat = case.chats.filter(platform=ChatPlatform.FEISHU, is_active=True).first()

                if existing_chat:
                    messages.warning(request, f"案件 {case.name} 已存在飞书群聊: {existing_chat.name}")
                    continue

                chat = service.create_chat_for_case(case.id, ChatPlatform.FEISHU)
                success_count += 1

                messages.success(request, f"成功为案件 {case.name} 创建飞书群聊: {chat.name}")

            except ChatProviderException as e:
                error_count += 1
                messages.error(request, f"为案件 {case.name} 创建飞书群聊失败: {e!s}")
            except Exception as e:
                error_count += 1
                messages.error(request, f"为案件 {case.name} 创建群聊时发生未知错误: {e!s}")

        if success_count > 0:
            messages.success(request, f"总计成功创建 {success_count} 个飞书群聊")

        if error_count > 0:
            messages.error(request, f"总计 {error_count} 个案件创建群聊失败")

    create_feishu_chat_for_selected_cases.short_description = _("为选中案件创建飞书群聊")  # type: ignore[attr-defined]

    def save_formset(self, request: HttpRequest, form: ModelForm[Case], formset: Any, change: bool) -> None:
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, CaseLog) and not getattr(obj, "actor_id", None):
                user_id = getattr(request.user, "id", None)
                if user_id is not None:
                    obj.actor_id = user_id
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            with contextlib.suppress(Exception):
                obj.delete()
