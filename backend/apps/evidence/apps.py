"""证据管理模块"""

from django.apps import AppConfig


class EvidenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.evidence"
    verbose_name = "证据管理"

    def ready(self) -> None:  # pragma: no cover
        from . import signals

        # 隐藏原始模型的 admin（它们通过 proxy model 注册在 /admin/evidence/ 下）
        from django.contrib import admin
        from django.contrib.admin.exceptions import NotRegistered

        from apps.evidence.models import EvidenceItem, EvidenceList

        for model in (EvidenceList, EvidenceItem):
            try:
                admin.site.unregister(model)
            except NotRegistered:
                pass
