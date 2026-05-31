from __future__ import annotations

from django.apps import AppConfig

class SalesDisputeConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.sales_dispute"
    verbose_name: str = "买卖纠纷计算"  # type: ignore[assignment]
