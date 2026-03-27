"""Module for router."""

from __future__ import annotations

from typing import ClassVar

from .backends import BackendConfig, ILLMBackend
from .backends.registry import get_backend_class


class LLMBackendRouter:
    DEFAULT_PRIORITIES: ClassVar = {
        "siliconflow": 1,
        "ollama": 2,
        "openai_compatible": 3,
        "moonshot": 3,
    }

    def __init__(self, *, backend_configs: dict[str, BackendConfig] | None = None) -> None:
        self._backend_configs = backend_configs
        self._backends: dict[str, ILLMBackend] = {}

    def get_backend_config(self, name: str) -> BackendConfig:
        if self._backend_configs and name in self._backend_configs:
            return self._backend_configs[name]
        return BackendConfig(
            name=name,
            enabled=True,
            priority=self.DEFAULT_PRIORITIES.get(name, 99),
            default_model="",
        )

    def get_backend(self, name: str) -> ILLMBackend:
        if name in self._backends:
            return self._backends[name]

        config = self.get_backend_config(name)
        backend_cls = get_backend_class(name)
        backend = backend_cls(config)  # type: ignore[call-arg]

        self._backends[name] = backend
        return backend

    def get_backends_by_priority(self, names: list[str] | None = None) -> list[tuple[str, ILLMBackend]]:
        backend_names = names or ["siliconflow", "ollama", "openai_compatible"]

        backends_with_priority: list[tuple[int, str]] = []
        for name in backend_names:
            config = self.get_backend_config(name)
            if config.enabled:
                backends_with_priority.append((config.priority, name))

        backends_with_priority.sort(key=lambda x: x[0])
        return [(name, self.get_backend(name)) for _, name in backends_with_priority]
