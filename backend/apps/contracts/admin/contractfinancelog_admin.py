from django.contrib import admin
from ..models import ContractFinanceLog

@admin.register(ContractFinanceLog)
class ContractFinanceLogAdmin(admin.ModelAdmin):
    list_display = ("id", "contract", "action", "level", "actor", "created_at")
    list_filter = ("level", "action")
    search_fields = ("contract__name", "action")
    autocomplete_fields = ("contract", "actor")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("contract", "actor")
