import pytest


def test_perm_open_access_defaults_to_false_in_non_production(monkeypatch):
    from apps.core.config.django_runtime import resolve_perm_open_access

    monkeypatch.delenv("PERM_OPEN_ACCESS", raising=False)
    assert resolve_perm_open_access(is_production=False) is False


def test_perm_open_access_can_be_enabled_in_non_production(monkeypatch):
    from apps.core.config.django_runtime import resolve_perm_open_access

    monkeypatch.setenv("PERM_OPEN_ACCESS", "true")
    assert resolve_perm_open_access(is_production=False) is True


def test_perm_open_access_is_forbidden_in_production(monkeypatch):
    from apps.core.config.django_runtime import resolve_perm_open_access

    monkeypatch.setenv("PERM_OPEN_ACCESS", "true")
    with pytest.raises(RuntimeError):
        resolve_perm_open_access(is_production=True)
