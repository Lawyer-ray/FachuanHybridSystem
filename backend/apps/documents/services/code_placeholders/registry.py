"""Business logic services."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, TypeVar


@dataclass(frozen=True)
class CodePlaceholderDefinition:
    key: str
    source: str
    category: str
    display_name: str = ""
    description: str = ""
    example_value: str = ""


class CodePlaceholderRegistry:
    _instance: CodePlaceholderRegistry | None = None
    _definitions: dict[str, CodePlaceholderDefinition]

    def __new__(cls) -> CodePlaceholderRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._definitions = {}
        return cls._instance

    def register(self, definitions: Iterable[CodePlaceholderDefinition]) -> None:
        for definition in definitions:
            self._definitions.setdefault(definition.key, definition)

    def upsert(self, definitions: Iterable[CodePlaceholderDefinition]) -> None:
        for definition in definitions:
            self._definitions[definition.key] = definition

    def list_definitions(self) -> list[CodePlaceholderDefinition]:
        return sorted(self._definitions.values(), key=lambda d: d.key)

    def clear(self) -> None:
        self._definitions.clear()


T = TypeVar("T")


def expose_placeholders(
    *,
    keys: list[str],
    source: str,
    category: str,
    metadata: dict[str, dict[str, Any]] | None = None,
    description: str = "",
) -> Callable[[T], T]:
    def decorator(target: T) -> T:
        defs: list[CodePlaceholderDefinition] = []
        per_key = metadata or {}
        for key in keys:
            key_meta = per_key.get(key, {}) or {}
            defs.append(
                CodePlaceholderDefinition(
                    key=key,
                    source=source,
                    category=category,
                    display_name=key_meta.get("display_name") or "",
                    description=key_meta.get("description") or description or "",
                    example_value=key_meta.get("example_value") or "",
                )
            )

        target.__code_placeholder_definitions__ = defs  # target 是泛型 T，无法用显式属性赋值替代
        CodePlaceholderRegistry().register(defs)
        return target

    return decorator
