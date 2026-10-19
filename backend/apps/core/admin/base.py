"""Admin 基类兜底别名（nested_admin 可选依赖）。

解耦（2026-10-19）：从 cases/admin/base_admin.py、contracts/admin/contract_admin.py、
contracts/admin/contractpayment_admin.py、contacts/admin.py 各自重复的
TYPE_CHECKING/try-nested_admin 块上提到 core，统一一处维护；
finance/admin/lpr_admin.py 原先跨 app 引 cases 的别名，一并改引此处。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin

if TYPE_CHECKING:
    from typing import TypeAlias

    BaseModelAdmin: TypeAlias = admin.ModelAdmin
    BaseStackedInline: TypeAlias = admin.StackedInline[Any, Any]
    BaseTabularInline: TypeAlias = admin.TabularInline[Any, Any]
else:
    try:
        import nested_admin

        BaseModelAdmin = nested_admin.NestedModelAdmin
        BaseStackedInline = nested_admin.NestedStackedInline
        BaseTabularInline = nested_admin.NestedTabularInline
    except ImportError:
        BaseModelAdmin = admin.ModelAdmin
        BaseStackedInline = admin.StackedInline
        BaseTabularInline = admin.TabularInline

__all__ = ["BaseModelAdmin", "BaseStackedInline", "BaseTabularInline"]
