"""Module for registry."""

from __future__ import annotations

import importlib

from .base import ILLMBackend

_BACKEND_IMPORT_PATHS: dict[str, str] = {
    "siliconflow": "apps.core.llm.backends.siliconflow:SiliconFlowBackend",
    "ollama": "apps.core.llm.backends.ollama:OllamaBackend",
}


def register_backend(*, name: str, import_path: str) -> None:
    _BACKEND_IMPORT_PATHS[name] = import_path


def get_backend_class(name: str) -> type[ILLMBackend]:
    import_path = _BACKEND_IMPORT_PATHS.get(name)
    if not import_path:
        raise ValueError(f"未知的 LLM 后端: {name}")
    module_path, cls_name = import_path.split(":")
    module = importlib.import_module(module_path)
    backend_cls = getattr(module, cls_name)
    from typing import cast

    return cast(type[ILLMBackend], backend_cls)
