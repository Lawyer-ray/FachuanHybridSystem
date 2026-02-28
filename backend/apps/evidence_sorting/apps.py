"""案件材料整理 app 配置"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EvidenceSortingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.evidence_sorting"
    verbose_name = _("案件材料整理")
