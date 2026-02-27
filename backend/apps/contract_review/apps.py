from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContractReviewConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contract_review"
    verbose_name = _("合同审查")
