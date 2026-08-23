from django.apps import AppConfig


class LaborArbitrationConfig(AppConfig):
    """劳动仲裁文书爬虫应用配置。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.labor_arbitration"
    verbose_name = "劳动仲裁文书爬虫"

    def ready(self) -> None:
        from apps.labor_arbitration.models.signals import register_signals

        register_signals()
