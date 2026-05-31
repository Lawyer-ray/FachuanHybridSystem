"""案件材料整理 app 配置"""

from django.apps import AppConfig

class EvidenceSortingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.evidence_sorting"
    verbose_name = "案件材料整理"
