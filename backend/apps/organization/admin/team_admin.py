from __future__ import annotations

from typing import ClassVar

from django.contrib import admin

from apps.organization.models import Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin[Team]):
    list_display: ClassVar[tuple[str, ...]] = ("id", "name", "team_type", "law_firm")
    list_filter: ClassVar[tuple[str, ...]] = ("team_type", "law_firm")
    search_fields: ClassVar[tuple[str, ...]] = ("name",)
