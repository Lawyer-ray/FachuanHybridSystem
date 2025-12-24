"""
ContractAssignment Admin 配置
管理合同律师指派
"""
from django.contrib import admin
from ..models import ContractAssignment


@admin.register(ContractAssignment)
class ContractAssignmentAdmin(admin.ModelAdmin):
    """合同律师指派 Admin"""
    
    list_display = (
        "id",
        "contract",
        "lawyer",
        "is_primary",
        "order",
    )
    
    list_filter = (
        "is_primary",
    )
    
    search_fields = (
        "contract__name",
        "lawyer__name",
    )
    
    autocomplete_fields = ["contract", "lawyer"]
    
    ordering = ["-is_primary", "order"]
