from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.forms import ModelForm
from django.http import HttpRequest

from apps.cases.models import CaseLog, CaseLogAttachment

if TYPE_CHECKING:
    BaseModelAdmin = admin.ModelAdmin
else:
    try:
        import nested_admin

        BaseModelAdmin = nested_admin.NestedModelAdmin
    except Exception:
        BaseModelAdmin = admin.ModelAdmin


@admin.register(CaseLog)
class CaseLogAdmin(BaseModelAdmin):
    list_display = ("id", "case", "actor", "reminder_type", "reminder_time", "created_at", "updated_at")
    search_fields = ("content", "case__name")
    autocomplete_fields = ("case", "actor")
    exclude = ("actor",)

    def save_model(
        self,
        request: HttpRequest,
        obj: CaseLog,
        form: ModelForm[CaseLog],
        change: bool,
    ) -> None:
        if not getattr(obj, "actor_id", None):
            user_id = getattr(request.user, "id", None)
            if user_id is not None:
                obj.actor_id = user_id
        super().save_model(request, obj, form, change)


@admin.register(CaseLogAttachment)
class CaseLogAttachmentAdmin(BaseModelAdmin):
    list_display = ("id", "log", "uploaded_at")
    search_fields = ("log__case__name",)
    autocomplete_fields = ("log",)
