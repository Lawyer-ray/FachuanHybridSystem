from __future__ import annotations

from django.apps import AppConfig


class DocSpaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.docspace"
    verbose_name = "DocSpace 云文档"
