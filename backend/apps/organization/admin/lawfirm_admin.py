from __future__ import annotations

from typing import ClassVar

from django.contrib import admin

from apps.organization.models import LawFirm


@admin.register(LawFirm)
class LawFirmAdmin(admin.ModelAdmin[LawFirm]):
    list_display: ClassVar[tuple[str, ...]] = ("id", "name", "phone", "social_credit_code")
    search_fields: ClassVar[tuple[str, ...]] = ("name", "social_credit_code")
