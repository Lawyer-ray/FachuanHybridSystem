from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import admin

from apps.cases.admin.base import BaseModelAdmin, BaseStackedInline, BaseTabularInline
from apps.cases.admin.case_chat_admin import CaseChatInline
from apps.cases.admin.case_forms_admin import CaseAdminForm, SupervisingAuthorityInlineForm
from apps.cases.models import (
    Case,
    CaseAssignment,
    CaseLog,
    CaseLogAttachment,
    CaseNumber,
    CaseParty,
    SupervisingAuthority,
)
from apps.cases.admin.mixins import (
    CaseAdminActionsMixin,
    CaseAdminSaveMixin,
    CaseAdminServiceMixin,
    CaseAdminViewsMixin,
)


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

    def has_view_or_change_permission(self, request: Any, obj: Any = None) -> bool:
        return False


class SupervisingAuthorityInline(BaseTabularInline):
    """主管机关内联"""

    model = SupervisingAuthority
    form = SupervisingAuthorityInlineForm
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
class CaseAdmin(CaseAdminActionsMixin, CaseAdminSaveMixin, CaseAdminViewsMixin, CaseAdminServiceMixin, BaseModelAdmin):
    form = CaseAdminForm
    list_display = ("id", "name_link", "status", "start_date", "effective_date", "is_archived")
    list_display_links = None
    list_filter = ("status", "is_archived")
    search_fields = ("name",)
    change_form_template = "admin/cases/case/change_form.html"
    readonly_fields = ("filing_number",)

    actions = ["create_feishu_chat_for_selected_cases"]

    class Media:
        js = (
            "cases/admin_case_form.js",
            "cases/js/autocomplete.js",
            "cases/js/autocomplete_init.js",
        )

    inlines = [
        CasePartyInline,
        CaseAssignmentInline,
        SupervisingAuthorityInline,
        CaseNumberInline,
        CaseLogInline,
        CaseChatInline,
    ]


