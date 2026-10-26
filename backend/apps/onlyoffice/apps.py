from __future__ import annotations

from django.apps import AppConfig


class OnlyOfficeAppConfig(AppConfig):
    """注意与 config.OnlyOfficeConfig（连接参数 dataclass）区分，二者仅重名。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.onlyoffice"
    verbose_name = "OnlyOffice 文档编辑器"
