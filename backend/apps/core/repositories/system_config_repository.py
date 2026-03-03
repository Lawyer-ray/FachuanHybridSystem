"""
SystemConfig Repository

封装 SystemConfig 模型的数据访问操作
"""

from typing import Any

from django.db.models import QuerySet

from apps.core.models.system_config import SystemConfig


class SystemConfigRepository:
    """系统配置数据访问层"""

    def create(
        self,
        key: str,
        value: str,
        category: str = "general",
        description: str = "",
        is_secret: bool = False,
        is_active: bool = True,
    ) -> SystemConfig:
        return SystemConfig.objects.create(
            key=key,
            value=value,
            category=category,
            description=description,
            is_secret=is_secret,
            is_active=is_active,
        )

    def get_by_id(self, config_id: int) -> SystemConfig | None:
        return SystemConfig.objects.filter(id=config_id).first()

    def get_by_key(self, key: str) -> SystemConfig | None:
        return SystemConfig.objects.filter(key=key).first()

    def get_by_keys(self, keys: list[str]) -> QuerySet[SystemConfig]:
        return SystemConfig.objects.filter(key__in=keys, is_active=True)

    def get_all(self) -> QuerySet[SystemConfig]:
        return SystemConfig.objects.all()

    def get_all_active(self) -> list[SystemConfig]:
        return list(SystemConfig.objects.filter(is_active=True))

    def get_by_category(self, category: str) -> QuerySet[SystemConfig]:
        return SystemConfig.objects.filter(category=category, is_active=True)

    def update_or_create(self, *, key: str, defaults: dict[str, Any]) -> SystemConfig:
        config, _created = SystemConfig.objects.update_or_create(key=key, defaults=defaults)
        return config

    def delete(self, config_id: int) -> tuple[int, dict[str, int]]:
        return SystemConfig.objects.filter(id=config_id).delete()
