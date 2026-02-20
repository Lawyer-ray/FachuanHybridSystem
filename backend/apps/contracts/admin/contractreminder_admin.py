from __future__ import annotations

from django.contrib import admin

from apps.contracts.models import ContractReminder


# 已废弃：使用 apps.reminders.Reminder 替代
# ContractReminder 模型保留用于数据迁移，但不再注册 Admin
class ContractReminderAdmin(admin.ModelAdmin[ContractReminder]):
    list_display = ("id", "contract", "kind", "content", "due_date", "created_at")
    list_filter = ("kind", "due_date")
    search_fields = ("contract__name", "content")
    autocomplete_fields = ("contract",)
