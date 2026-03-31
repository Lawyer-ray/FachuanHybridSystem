"""doc_convert app 配置。"""

from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DocConvertConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.doc_convert"
    verbose_name = _("文书转换")
