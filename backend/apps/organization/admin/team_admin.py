from django.contrib import admin
from ..models import Team

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "team_type", "law_firm")
    list_filter = ("team_type", "law_firm")
    search_fields = ("name",)
