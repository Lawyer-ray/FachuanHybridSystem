from __future__ import annotations

from django.apps import AppConfig

class ContractsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contracts"
    verbose_name = "合同管理"

    def ready(self) -> None:
        import apps.contracts.signals
