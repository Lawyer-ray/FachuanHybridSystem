from __future__ import annotations

from django.contrib import admin

from apps.cases.admin.base_admin import BaseModelAdmin
from apps.sales_dispute.models import LPRRate


@admin.register(LPRRate)
class LPRRateAdmin(BaseModelAdmin):
    list_display = ("effective_date", "rate_1y", "rate_5y", "updated_at")
    list_filter = ("effective_date",)
    ordering = ("-effective_date",)
