from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin

if TYPE_CHECKING:
    from typing import TypeAlias

    BaseModelAdmin: TypeAlias = admin.ModelAdmin[Any]
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
