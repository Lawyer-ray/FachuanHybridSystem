from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PdfSplittingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pdf_splitting"
    verbose_name = _("PDF 拆解")
