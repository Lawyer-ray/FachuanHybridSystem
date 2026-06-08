"""Unit tests for core.infrastructure.service_locator and service_locator_base."""

from __future__ import annotations

import pytest

from apps.core.infrastructure.service_locator_base import BaseServiceLocator


class TestBaseServiceLocator:
    """测试 BaseServiceLocator 基类"""

    def setup_method(self) -> None:
        BaseServiceLocator.clear()

    def test_register_and_get(self) -> None:
        BaseServiceLocator.register("test_key", "test_value")
        assert BaseServiceLocator.get("test_key") == "test_value"

    def test_get_nonexistent_returns_none(self) -> None:
        assert BaseServiceLocator.get("nonexistent") is None

    def test_get_or_create_creates(self) -> None:
        result = BaseServiceLocator.get_or_create("new_key", lambda: 42)
        assert result == 42
        assert BaseServiceLocator.get("new_key") == 42

    def test_get_or_create_returns_existing(self) -> None:
        BaseServiceLocator.register("existing", "original")
        result = BaseServiceLocator.get_or_create("existing", lambda: "new")
        assert result == "original"

    def test_clear_single(self) -> None:
        BaseServiceLocator.register("a", 1)
        BaseServiceLocator.register("b", 2)
        BaseServiceLocator.clear("a")
        assert BaseServiceLocator.get("a") is None
        assert BaseServiceLocator.get("b") == 2

    def test_clear_all(self) -> None:
        BaseServiceLocator.register("a", 1)
        BaseServiceLocator.register("b", 2)
        BaseServiceLocator.clear()
        assert BaseServiceLocator.get("a") is None
        assert BaseServiceLocator.get("b") is None

    def test_scope_context_manager(self) -> None:
        BaseServiceLocator.register("global_key", "global_value")
        with BaseServiceLocator.scope():
            # Inside scope, storage is isolated
            BaseServiceLocator.register("scoped_key", "scoped_value")
            assert BaseServiceLocator.get("scoped_key") == "scoped_value"
            # Global key should not be visible in scope
            assert BaseServiceLocator.get("global_key") is None
        # After scope exits, global storage is restored
        assert BaseServiceLocator.get("global_key") == "global_value"
        assert BaseServiceLocator.get("scoped_key") is None

    def test_nested_scopes(self) -> None:
        BaseServiceLocator.register("g", 1)
        with BaseServiceLocator.scope():
            BaseServiceLocator.register("s1", 2)
            with BaseServiceLocator.scope():
                BaseServiceLocator.register("s2", 3)
                assert BaseServiceLocator.get("s2") == 3
            assert BaseServiceLocator.get("s1") == 2
        assert BaseServiceLocator.get("g") == 1

    def test_overwrite_value(self) -> None:
        BaseServiceLocator.register("k", "old")
        BaseServiceLocator.register("k", "new")
        assert BaseServiceLocator.get("k") == "new"


class TestServiceLocator:
    """测试 ServiceLocator 子类"""

    def test_service_locator_exists(self) -> None:
        from apps.core.infrastructure.service_locator import ServiceLocator
        assert ServiceLocator is not None

    def test_service_locator_inherits_base(self) -> None:
        from apps.core.infrastructure.service_locator import ServiceLocator
        from apps.core.infrastructure.service_locator_base import BaseServiceLocator
        assert issubclass(ServiceLocator, BaseServiceLocator)
