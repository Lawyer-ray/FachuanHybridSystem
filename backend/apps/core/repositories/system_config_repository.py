"""
SystemConfig Repository

封装 SystemConfig 模型的数据访问操作
"""

from typing import Any

from apps.core.models.system_config import SystemConfig


class SystemConfigRepository:
    """系统配置数据访问层"""

    def __init__(self, *, model: type[Any] = SystemConfig) -> None:
        self._model = model

    def create(
        self,
        key: str,
        value: str,
        category: str = "general",
        description: str = "",
        is_secret: bool = False,
        is_active: bool = True,
    ) -> SystemConfig:
        """创建配置"""
        return self._model.objects.create(
            key=key,
            value=value,
            category=category,
            description=description,
            is_secret=is_secret,
            is_active=is_active,
        )

    def get_by_id(self, config_id: int) -> SystemConfig | None:
        """根据 ID 获取配置"""
        return self._model.objects.filter(id=config_id).first()

    def get_by_key(self, key: str) -> SystemConfig | None:
        """根据 key 获取配置"""
        return self._model.objects.filter(key=key).first()

    def get_all_active(self) -> list[SystemConfig]:
        """获取所有启用的配置"""
        return list(self._model.objects.filter(is_active=True))

    def get_by_category(self, category: str) -> list[SystemConfig]:
        """根据分类获取配置"""
        return list(self._model.objects.filter(category=category, is_active=True))

    def delete(self, config_id: int) -> tuple[int, dict[str, int]]:
        """删除配置"""
        return self._model.objects.filter(id=config_id).delete()

    def exists_by_key(self, key: str) -> bool:
        """检查 key 是否存在"""
        return self._model.objects.filter(key=key).exists()
