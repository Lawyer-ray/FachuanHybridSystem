"""配置模式管理模块"""

from typing import Any

from apps.core.config.exceptions import ConfigValidationError

from .field import ConfigField


class ConfigSchema:
    def __init__(self) -> None:
        self._fields: dict[str, ConfigField] = {}

    def register(self, field: ConfigField) -> None:
        if field.name in self._fields:
            raise ValueError(f"配置字段 '{field.name}' 已存在")
        self._fields[field.name] = field

    def get_field(self, key: str) -> ConfigField | None:
        return self._fields.get(key)

    def validate_and_raise(self, config: dict[str, Any]) -> None:
        errors = [f"缺少必填配置项: {f.name}" for f in self._fields.values() if f.required and f.name not in config]
        if errors:
            raise ConfigValidationError(errors)

    def get_suggestions(self, key: str, max_suggestions: int = 5) -> list[str]:
        key_lower = key.lower()
        suggestions: list[str] = []
        for matcher in [
            lambda name: name.lower() == key_lower,
            lambda name: name.lower().startswith(key_lower),
            lambda name: key_lower in name.lower(),
        ]:
            if len(suggestions) >= max_suggestions:
                break
            for field_name in self._fields:
                if field_name not in suggestions and matcher(field_name):
                    suggestions.append(field_name)
                    if len(suggestions) >= max_suggestions:
                        break
        return suggestions
