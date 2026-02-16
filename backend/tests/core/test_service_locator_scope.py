from __future__ import annotations

from apps.core.service_locator_base import BaseServiceLocator


class _TestLocator(BaseServiceLocator):
    pass


def test_service_locator_scope_isolation():
    _TestLocator.clear()
    _TestLocator.register("k", "global")

    with _TestLocator.scope():
        assert _TestLocator.get("k") is None
        _TestLocator.register("k", "scoped")
        assert _TestLocator.get("k") == "scoped"

    assert _TestLocator.get("k") == "global"


def test_service_locator_scope_get_or_create_caches_in_scope():
    _TestLocator.clear()
    created = 0

    def factory():
        nonlocal created
        created += 1
        return object()

    with _TestLocator.scope():
        a = _TestLocator.get_or_create("x", factory)
        b = _TestLocator.get_or_create("x", factory)
        assert a is b
        assert created == 1

    c = _TestLocator.get_or_create("x", factory)
    assert c is not a
    assert created == 2
