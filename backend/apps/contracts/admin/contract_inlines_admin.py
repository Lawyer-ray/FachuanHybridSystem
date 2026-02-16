"""
Contract Admin - Inline Classes

合同 Admin 的 Inline 类定义.
"""

from django.apps import apps as django_apps
from django.contrib import admin

try:
    import nested_admin

    BaseStackedInline = nested_admin.NestedStackedInline
    BaseTabularInline = nested_admin.NestedTabularInline
except ImportError:
    BaseStackedInline = admin.StackedInline
    BaseTabularInline = admin.TabularInline

from typing import Any, ClassVar

from apps.contracts.models import ContractAssignment, ContractParty, SupplementaryAgreement, SupplementaryAgreementParty

Reminder = django_apps.get_model("reminders", "Reminder")


class ContractPartyInline(BaseTabularInline):
    model = ContractParty
    extra: int = 1
    fields: tuple[Any, ...] = ("client", "role")
    autocomplete_fields: ClassVar = ["client"]
    show_change_link: bool = True


class ContractReminderInline(BaseTabularInline):
    model = Reminder
    extra: int = 1
    fields: tuple[Any, ...] = ("reminder_type", "content", "due_at")


class ContractAssignmentInline(BaseTabularInline):
    model = ContractAssignment
    extra: int = 1
    fields: tuple[Any, ...] = ("lawyer", "is_primary", "order")
    autocomplete_fields: ClassVar = ["lawyer"]
    ordering: tuple[Any, ...] = ("order",)


class SupplementaryAgreementPartyInlineAdmin(BaseTabularInline):
    """补充协议当事人内联管理"""

    model = SupplementaryAgreementParty
    extra: int = 1
    fields: tuple[Any, ...] = ("client", "role")
    autocomplete_fields: ClassVar = ["client"]


class SupplementaryAgreementInlineAdmin(BaseStackedInline):
    """合同补充协议内联管理

    Requirements: 5.1, 5.3
    """

    model = SupplementaryAgreement
    extra: int = 0
    fields: tuple[Any, ...] = ("name", "created_at", "updated_at")
    readonly_fields: tuple[Any, ...] = ("created_at", "updated_at")
    show_change_link: bool = True
    inlines: ClassVar = [SupplementaryAgreementPartyInlineAdmin]
