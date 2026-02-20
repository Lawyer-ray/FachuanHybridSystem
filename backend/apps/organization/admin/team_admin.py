from django.contrib import admin
from apps.organization.models import Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin[Team]):
    list_display = ("id", "name", "team_type", "law_firm")
    list_filter = ("team_type", "law_firm")
    search_fields = ("name",)
