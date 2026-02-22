"""
Contract Admin - Inline Classes

合同 Admin 的 Inline 类定义.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.apps import apps as django_apps
from django.contrib import admin

if TYPE_CHECKING:
    BaseStackedInline = admin.StackedInline
    BaseTabularInline = admin.TabularInline
else:
    try:
        import nested_admin

        BaseStackedInline = nested_admin.NestedStackedInline
        BaseTabularInline = nested_admin.NestedTabularInline
    except ImportError:
        BaseStackedInline = admin.StackedInline
        BaseTabularInline = admin.TabularInline

from apps.contracts.models import ContractAssignment, ContractParty, SupplementaryAgreement, SupplementaryAgreementParty

Reminder = django_apps.get_model("reminders", "Reminder")


class ContractPartyInline(BaseTabularInline[ContractParty, ContractParty]):
    model = ContractParty
    extra = 1
    fields = ("client", "role")
    autocomplete_fields: ClassVar = ["client"]
    show_change_link = True


class ReminderInline(BaseTabularInline[Any, Any]):
    model = Reminder
    extra = 1
    fields = ("reminder_type", "content", "due_at")


class ContractAssignmentInline(BaseTabularInline[ContractAssignment, ContractAssignment]):
    model = ContractAssignment
    extra = 1
    fields = ("lawyer", "is_primary", "order")
    autocomplete_fields: ClassVar = ["lawyer"]
    ordering = ("order",)


class SupplementaryAgreementPartyInlineAdmin(
    BaseTabularInline[SupplementaryAgreementParty, SupplementaryAgreementParty]
):
    """补充协议当事人内联管理"""

    model = SupplementaryAgreementParty
    extra = 1
    fields = ("client", "role")
    autocomplete_fields: ClassVar = ["client"]


class SupplementaryAgreementInlineAdmin(BaseStackedInline[SupplementaryAgreement, SupplementaryAgreement]):
    """合同补充协议内联管理

    Requirements: 5.1, 5.3
    """

    model = SupplementaryAgreement
    extra = 0
    fields = ("name", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    show_change_link = True
    inlines: ClassVar = [SupplementaryAgreementPartyInlineAdmin]
