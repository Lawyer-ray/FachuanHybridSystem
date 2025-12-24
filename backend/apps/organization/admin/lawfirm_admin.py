from django.contrib import admin
from ..models import LawFirm

@admin.register(LawFirm)
class LawFirmAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "social_credit_code")
    search_fields = ("name", "social_credit_code")
