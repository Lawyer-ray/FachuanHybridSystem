"""Structure checks for tracked CI test tree."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path


def test_ci_tree_has_required_layers() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "structure").is_dir()
    assert (root / "unit").is_dir()
    assert (root / "integration").is_dir()
    assert (root / "property").is_dir()


def test_unit_regression_modules_are_importable() -> None:
    module = import_module("tests.ci.unit.test_regression_suite")
    names = [name for name in vars(module) if name.startswith("test_")]
    assert names
