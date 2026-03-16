"""Compatibility shim for moved image rotation services."""

from importlib import import_module
from typing import Any

_IMPL = import_module("apps.image_rotation.services.orientation.service")


def __getattr__(name: str) -> Any:
    return getattr(_IMPL, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_IMPL)))


__all__ = getattr(_IMPL, "__all__", [n for n in dir(_IMPL) if not n.startswith("_")])
