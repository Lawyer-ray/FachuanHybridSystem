from django.contrib import admin
from django.contrib.admin import ModelAdmin
from ..models import CaseLog, CaseLogAttachment
try:
    import nested_admin
    BaseModelAdmin = nested_admin.NestedModelAdmin
except Exception:
    BaseModelAdmin = admin.ModelAdmin


@admin.register(CaseLog)
class CaseLogAdmin(BaseModelAdmin):
    list_display = ("id", "case", "actor", "reminder_type", "reminder_time", "created_at", "updated_at")
    list_filter = ("reminder_type",)
    search_fields = ("content", "case__name")
    autocomplete_fields = ("case", "actor")
    exclude = ("actor",)

    def save_model(self, request, obj, form, change):
        if not getattr(obj, "actor_id", None):
            obj.actor_id = getattr(request.user, "id", None)
        super().save_model(request, obj, form, change)


@admin.register(CaseLogAttachment)
class CaseLogAttachmentAdmin(BaseModelAdmin):
    list_display = ("id", "log", "uploaded_at")
    search_fields = ("log__case__name",)
    autocomplete_fields = ("log",)
