"""
ContractAssignment Admin 配置
管理合同律师指派
"""

from __future__ import annotations

from typing import ClassVar

from apps.contracts.models import ContractAssignment


class ContractAssignmentAdmin(admin.ModelAdmin[ContractAssignment]):
    """合同律师指派 Admin"""

    list_display = (
        "id",
        "contract",
        "lawyer",
        "is_primary",
        "order",
    )

    list_filter = ("is_primary",)

    search_fields = (
        "contract__name",
        "lawyer__name",
    )

    autocomplete_fields: ClassVar = ["contract", "lawyer"]

    ordering: ClassVar = ["-is_primary", "order"]
