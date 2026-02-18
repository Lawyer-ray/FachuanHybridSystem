from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.contracts.models import ContractFinanceLog


@admin.register(ContractFinanceLog)
class ContractFinanceLogAdmin(admin.ModelAdmin[ContractFinanceLog]):
    list_display = ("id", "contract", "action", "level", "actor", "created_at")
    list_filter = ("level", "action")
    search_fields = ("contract__name", "action")
    autocomplete_fields = ("contract", "actor")

    def get_queryset(self, request: HttpRequest) -> QuerySet[ContractFinanceLog, ContractFinanceLog]:
        return super().get_queryset(request).select_related("contract", "actor")
