"""案件编辑页的客户回款 Inline"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import ClientPaymentRecord

if TYPE_CHECKING:
    BaseTabularInline = admin.TabularInline
else:
    try:
        import nested_admin

        BaseTabularInline = nested_admin.NestedTabularInline
    except ImportError:
        BaseTabularInline = admin.TabularInline  # type: ignore[assignment,misc]


class CaseClientPaymentInline(BaseTabularInline[ClientPaymentRecord, ClientPaymentRecord]):
    model = ClientPaymentRecord
    extra = 0
    fields = ("amount", "note")
    verbose_name = _("客户回款")
    verbose_name_plural = _("客户回款")
    can_delete = True

    def get_formset(self, request: HttpRequest, obj: Any = None, **kwargs: Any) -> Any:
        return super().get_formset(request, obj, **kwargs)

    def save_new(self, form: Any, commit: bool = True) -> ClientPaymentRecord:
        instance = super().save_new(form, commit=False)
        # self.instance 是父级 Case 对象
        parent_case = self.instance
        if parent_case and parent_case.pk:
            if not instance.contract_id:
                instance.contract_id = parent_case.contract_id
            if not instance.case_id:
                instance.case_id = parent_case.pk
        if commit:
            instance.save()
        return instance
