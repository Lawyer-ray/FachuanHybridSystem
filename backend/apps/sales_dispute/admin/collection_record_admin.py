"""催收记录 Admin 配置"""

from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.cases.admin.base_admin import BaseModelAdmin, BaseTabularInline
from apps.sales_dispute.models import CollectionLog, CollectionRecord


class CollectionLogInline(BaseTabularInline):
    """催收操作日志 Inline"""

    model = CollectionLog
    extra = 0
    readonly_fields = (
        "action_type",
        "action_date",
        "description",
        "document_type",
        "document_filename",
        "created_at",
    )
    ordering = ("-action_date", "-created_at")


@admin.register(CollectionRecord)
class CollectionRecordAdmin(BaseModelAdmin):
    """催收记录 Admin"""

    list_display = (
        "case",
        "current_stage",
        "start_date",
        "next_due_date",
        "is_overdue_display",
        "created_at",
    )
    list_filter = ("current_stage",)
    search_fields = ("case__name",)
    readonly_fields = ("days_elapsed", "is_overdue")
    inlines = [CollectionLogInline]

    @admin.display(boolean=True, description=_("是否逾期"))
    def is_overdue_display(self, obj: CollectionRecord) -> bool:
        return obj.is_overdue
