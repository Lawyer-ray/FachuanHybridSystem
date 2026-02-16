import importlib
from pathlib import Path

import pytest


def test_core_interfaces_service_locator_is_importable(monkeypatch: pytest.MonkeyPatch):
    backend_path = Path(__file__).resolve().parents[2]
    api_system_path = backend_path / "apiSystem"

    monkeypatch.syspath_prepend(str(backend_path))
    monkeypatch.syspath_prepend(str(api_system_path))
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
    monkeypatch.setenv("DJANGO_DEBUG", "1")
    monkeypatch.setenv("DATABASE_PATH", "/tmp/fachuan_import_health.sqlite3")

    import django

    django.setup()

    core_interfaces = importlib.import_module("apps.core.interfaces")
    service_locator = getattr(core_interfaces, "ServiceLocator")
    assert service_locator is not None
