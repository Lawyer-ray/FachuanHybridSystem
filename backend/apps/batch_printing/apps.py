from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BatchPrintingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.batch_printing"
    verbose_name = _("批量打印")
