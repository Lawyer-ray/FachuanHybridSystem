from django.contrib import admin
from ..models import CaseAssignment

@admin.register(CaseAssignment)
class CaseAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "lawyer")
    list_filter = ()
    search_fields = ("case__name", "lawyer__real_name")
