"""Helpers to expose app-level tests under tracked CI tree."""

from __future__ import annotations

from importlib import import_module
from typing import Any


def _is_pytest_fixture(obj: Any) -> bool:
    return getattr(obj, "_pytestfixturefunction", None) is not None


def expose_test_functions(namespace: dict[str, Any], modules: list[str]) -> None:
    """Import test modules and re-export test functions into current namespace."""
    for module_name in modules:
        module = import_module(module_name)
        suffix = module_name.rsplit(".", 1)[-1]
        for name, obj in vars(module).items():
            if name.startswith("__"):
                continue
            if not _is_pytest_fixture(obj):
                continue
            namespace[name] = obj

        for name, obj in vars(module).items():
            if not name.startswith("test_"):
                continue
            if not callable(obj):
                continue
            exported_name = f"test_{suffix}__{name}"
            namespace[exported_name] = obj
