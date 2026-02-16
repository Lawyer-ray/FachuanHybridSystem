"""Module for system config protocols."""

from typing import Any, Protocol


class ISystemConfigService(Protocol):
    def get_value(self, key: str, default: str = "") -> str: ...

    def get_category_configs(self, category: str) -> dict[str, str]: ...

    def set_value(
        self,
        key: str,
        value: str,
        category: str = "general",
        description: str = "",
        is_secret: bool = False,
    ) -> Any: ...

    def get_value_internal(self, key: str, default: str = "") -> str: ...

    def get_category_configs_internal(self, category: str) -> dict[str, str]: ...


class IBusinessConfigService(Protocol):
    def get_stages_for_case_type(self, case_type: str | None) -> list[tuple[Any, ...]]: ...
