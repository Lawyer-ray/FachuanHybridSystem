"""Test that the four-layer architecture constraints are respected.

Layer rules:
- API layer: factory functions, parameter extraction. NO Model.objects calls.
- Service layer: business logic, transactions, permissions. NO @staticmethod.
- Admin layer: UI configuration, factory functions. NO direct Service instantiation.
- Model layer: field definitions, @property. NO business methods, no custom save().

These are *structural smoke tests* — they catch obvious violations in the
source text. They are not exhaustive (e.g., dynamic attribute access is
not detected), but they establish a ratchet baseline for the most common
anti-patterns.
"""

from __future__ import annotations

import re
from pathlib import Path

_APPS_ROOT = Path(__file__).resolve().parents[3] / "apps"

# ── Ratchet baselines ─────────────────────────────────────────
# Current counts as of 2026-04-20. These set upper limits on
# violations; the goal is to drive them toward zero.

# API layer calling Model.objects directly
API_MODEL_OBJECTS_RATCHET = 77

# Service layer using @staticmethod
SERVICE_STATIC_METHOD_RATCHET = 215


def _scan_api_model_objects() -> list[tuple[str, int, str]]:
    """Find Model.objects calls in API layer files."""
    violations: list[tuple[str, int, str]] = []
    pattern = re.compile(r"\.objects\.")

    for app_dir in sorted(_APPS_ROOT.iterdir()):
        if not app_dir.is_dir() or app_dir.name.startswith("_"):
            continue

        api_dir = app_dir / "api"
        if not api_dir.is_dir():
            continue

        for py_file in api_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    violations.append((str(py_file.relative_to(_APPS_ROOT)), line_no, line.strip()))

    return violations


def _scan_service_staticmethod() -> list[tuple[str, int, str]]:
    """Find @staticmethod usage in Service layer files."""
    violations: list[tuple[str, int, str]] = []
    pattern = re.compile(r"@\s*staticmethod")

    for app_dir in sorted(_APPS_ROOT.iterdir()):
        if not app_dir.is_dir() or app_dir.name.startswith("_"):
            continue

        services_dir = app_dir / "services"
        if not services_dir.is_dir():
            continue

        for py_file in services_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    violations.append((str(py_file.relative_to(_APPS_ROOT)), line_no, line.strip()))

    return violations


def test_api_layer_no_model_objects_calls() -> None:
    """API layer must not call Model.objects directly — use Service layer instead."""
    violations = _scan_api_model_objects()
    assert len(violations) <= API_MODEL_OBJECTS_RATCHET, (
        f"API layer contains {len(violations)} Model.objects call(s), "
        f"exceeding ratchet baseline {API_MODEL_OBJECTS_RATCHET}.\n"
        "Move ORM queries to Service layer.\n"
        + "\n".join(f"  {path}:{lineno}: {content}" for path, lineno, content in violations)
    )


def test_service_layer_staticmethod_count_within_ratchet() -> None:
    """Service layer @staticmethod usage must not exceed ratchet baseline."""
    violations = _scan_service_staticmethod()
    assert len(violations) <= SERVICE_STATIC_METHOD_RATCHET, (
        f"Service layer contains {len(violations)} @staticmethod usage(s), "
        f"exceeding ratchet baseline {SERVICE_STATIC_METHOD_RATCHET}.\n"
        "Prefer instance methods with dependency injection.\n"
        + "\n".join(f"  {path}:{lineno}: {content}" for path, lineno, content in violations[:10])
    )
