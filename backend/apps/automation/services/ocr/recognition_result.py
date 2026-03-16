"""Compatibility shim for moved invoice recognition services."""

from importlib import import_module
from typing import Any

_IMPL = import_module("apps.invoice_recognition.services.recognition_result")


def __getattr__(name: str) -> Any:
    return getattr(_IMPL, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_IMPL)))


__all__ = getattr(_IMPL, "__all__", [n for n in dir(_IMPL) if not n.startswith("_")])

