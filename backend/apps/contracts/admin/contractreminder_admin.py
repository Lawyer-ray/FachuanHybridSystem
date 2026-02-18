from __future__ import annotations

from django.contrib import admin

from apps.contracts.models import ContractReminder


@admin.register(ContractReminder)
class ContractReminderAdmin(admin.ModelAdmin[ContractReminder]):
    list_display = ("id", "contract", "kind", "content", "due_date", "created_at")
    list_filter = ("kind", "due_date")
    search_fields = ("contract__name", "content")
    autocomplete_fields = ("contract",)
