from django.apps import AppConfig


class AutomationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.automation"
    verbose_name = "自动化工具"

    def ready(self) -> None:
        """应用启动时的配置"""
        from django.contrib import admin

        from .admin.scraper.scraper_admin_site import customize_admin_index

        customize_admin_index(admin.site)

        from . import signals
