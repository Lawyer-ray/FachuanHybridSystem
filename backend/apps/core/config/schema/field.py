"""配置字段定义模块"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfigField:
    """配置字段定义"""

    name: str
    type: type
    default: Any = None
    required: bool = False
    sensitive: bool = False
    description: str = ""
    min_value: int | float | None = None
    max_value: int | float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    choices: list[Any] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    env_var: str | None = None
    validator: Callable[[Any], bool] | None = None
    transformer: Callable[[Any], Any] | None = None

    def __post_init__(self) -> None:
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError(
                f"字段 '{self.name}' 的 min_value ({self.min_value}) 不能大于 max_value ({self.max_value})"
            )
        if self.min_length is not None and self.max_length is not None and self.min_length > self.max_length:
            raise ValueError(
                f"字段 '{self.name}' 的 min_length ({self.min_length}) 不能大于 max_length ({self.max_length})"
            )
        if self.required and self.default is not None:
            raise ValueError(f"字段 '{self.name}' 不能同时设置为必需字段和提供默认值")
