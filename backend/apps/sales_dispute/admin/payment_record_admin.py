from __future__ import annotations

from django.contrib import admin

from apps.cases.admin.base_admin import BaseModelAdmin
from apps.sales_dispute.models import PaymentRecord


@admin.register(PaymentRecord)
class PaymentRecordAdmin(BaseModelAdmin):
    list_display = (
        "case",
        "payment_date",
        "payment_amount",
        "offset_fee",
        "offset_interest",
        "offset_principal",
        "remaining_principal",
    )
    list_filter = ("payment_date",)
    autocomplete_fields = ("case",)
