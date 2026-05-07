from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin

from apps.contacts.models import CaseContact

if TYPE_CHECKING:
    from typing import TypeAlias

    BaseTabularInline: TypeAlias = admin.TabularInline[Any, Any]
    BaseModelAdmin: TypeAlias = admin.ModelAdmin[Any]
else:
    try:
        import nested_admin

        BaseTabularInline = nested_admin.NestedTabularInline
        BaseModelAdmin = nested_admin.NestedModelAdmin
    except ImportError:
        BaseTabularInline = admin.TabularInline
        BaseModelAdmin = admin.ModelAdmin


class CaseContactInline(BaseTabularInline):
    model = CaseContact
    extra = 1
    fields = ("name", "role", "phone", "address", "stage", "authority", "note")


@admin.register(CaseContact)
class CaseContactAdmin(BaseModelAdmin):
    list_display = ("id", "case", "name", "role", "phone", "stage", "authority")
    list_filter = ("role", "stage")
    search_fields = ("name", "phone", "case__name")
    raw_id_fields = ("case", "authority")
