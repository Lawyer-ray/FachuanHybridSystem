"""Module for provider registry."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from apps.core.config.providers.base import ConfigProvider


class ConfigProviderRegistry:
    def __init__(self) -> None:
        self._providers: list[ConfigProvider] = []

    @property
    def providers(self) -> Sequence[ConfigProvider]:
        return tuple(self._providers)

    def add(self, provider: ConfigProvider) -> None:
        self._providers.append(provider)
        self._providers.sort(key=lambda p: p.priority, reverse=True)

    def remove(self, provider_class: type) -> None:
        self._providers = [p for p in self._providers if not isinstance(p, provider_class)]

    def count(self) -> int:
        return len(self._providers)

    def iter(self) -> Iterable[ConfigProvider]:
        return iter(self._providers)

    def find_reloadable_provider_by_file_path(self, file_path: str) -> ConfigProvider | None:
        for provider in self._providers:
            if (
                hasattr(provider, "get_file_path")
                and provider.supports_reload()
                and str(provider.get_file_path()) == str(file_path)
            ):
                return provider
        return None
