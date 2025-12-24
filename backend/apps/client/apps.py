from django.apps import AppConfig


class ClientConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.client"
    verbose_name = "当事人管理"