"""Import smoke for tracked CI unit test modules."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest
from django.core.cache import cache


def _tracked_unit_modules() -> list[str]:
    unit_dir = Path(__file__).resolve().parent
    this_module = Path(__file__).stem
    return sorted(
        f"tests.ci.unit.{path.stem}"
        for path in unit_dir.glob("test_*.py")
        if path.is_file() and path.stem != this_module
    )


@pytest.fixture(autouse=True)
def _clear_ci_cache() -> None:
    cache.clear()


def test_tracked_ci_unit_modules_are_importable() -> None:
    modules = _tracked_unit_modules()
    assert modules
    for module_name in modules:
        import_module(module_name)
