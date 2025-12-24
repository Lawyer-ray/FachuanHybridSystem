from django.contrib import admin
from ..models import CaseNumber

@admin.register(CaseNumber)
class CaseNumberAdmin(admin.ModelAdmin):
    list_display = ("id", "number", "case", "remarks", "created_at")
    list_filter = ("created_at",)
    search_fields = ("number", "remarks")
    raw_id_fields = ("case",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("case")

    fieldsets = (
        (None, {
            "fields": ("case", "number", "remarks")
        }),
        ("时间信息", {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )
