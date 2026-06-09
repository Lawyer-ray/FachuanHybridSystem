"""Tests for core config.manager.ConfigManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.config.cache import ConfigCache
from apps.core.config.exceptions import ConfigNotFoundError, ConfigTypeError
from apps.core.config.manager import ConfigManager
from apps.core.config.notifications import ConfigChangeListener
from apps.core.config.schema.schema import ConfigSchema


class TestConfigManager:
    def setup_method(self) -> None:
        self.mgr = ConfigManager(cache_max_size=100, cache_ttl=60.0)

    def _make_provider(self, data: dict) -> MagicMock:
        provider = MagicMock()
        provider.priority = 10
        provider.load.return_value = data
        provider.get_name.return_value = "TestProvider"
        return provider

    def test_add_provider(self) -> None:
        p = self._make_provider({})
        self.mgr.add_provider(p)
        assert self.mgr.get_provider_count() == 1

    def test_remove_provider(self) -> None:
        p = self._make_provider({})
        self.mgr.add_provider(p)
        self.mgr.remove_provider(type(p))
        assert self.mgr.get_provider_count() == 0

    def test_load_basic(self) -> None:
        p = self._make_provider({"key1": "val1", "key2": "val2"})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr.is_loaded() is True
        assert self.mgr.get("key1") == "val1"

    def test_load_no_reload(self) -> None:
        p = self._make_provider({"key": "val"})
        self.mgr.add_provider(p)
        self.mgr.load()
        p.load.call_count
        self.mgr.load()  # should not reload
        # Provider load should be called only once
        assert p.load.call_count == 1

    def test_load_force_reload(self) -> None:
        p = self._make_provider({"key": "val"})
        self.mgr.add_provider(p)
        self.mgr.load()
        self.mgr.load(force_reload=True)
        assert p.load.call_count == 2

    def test_load_provider_failure(self) -> None:
        p = MagicMock()
        p.priority = 10
        p.load.side_effect = Exception("provider error")
        p.get_name.return_value = "BadProvider"
        self.mgr.add_provider(p)
        with pytest.raises(Exception, match="provider error"):
            self.mgr.load()

    def test_get_with_cache(self) -> None:
        p = self._make_provider({"key": "val"})
        self.mgr.add_provider(p)
        self.mgr.load()
        # First get: from raw config -> cached
        v1 = self.mgr.get("key")
        # Second get: from cache
        v2 = self.mgr.get("key")
        assert v1 == v2 == "val"

    def test_get_not_found_raises(self) -> None:
        p = self._make_provider({})
        self.mgr.add_provider(p)
        self.mgr.load()
        with pytest.raises(ConfigNotFoundError):
            self.mgr.get("nonexistent")

    def test_get_with_default(self) -> None:
        p = self._make_provider({})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr.get("nonexistent", "default") == "default"

    def test_get_before_loaded(self) -> None:
        """get() should auto-load if not loaded yet."""
        p = self._make_provider({"auto_key": "auto_val"})
        self.mgr.add_provider(p)
        assert self.mgr.is_loaded() is False
        val = self.mgr.get("auto_key")
        assert val == "auto_val"
        assert self.mgr.is_loaded() is True

    def test_set_and_get(self) -> None:
        self.mgr.set("dynamic_key", "dynamic_val")
        assert self.mgr.get("dynamic_key") == "dynamic_val"

    def test_has(self) -> None:
        p = self._make_provider({"exists": "yes"})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr.has("exists") is True
        assert self.mgr.has("nope") is False

    def test_get_all(self) -> None:
        p = self._make_provider({"k1": "v1", "k2": "v2"})
        self.mgr.add_provider(p)
        self.mgr.load()
        all_config = self.mgr.get_all()
        assert all_config["k1"] == "v1"
        assert all_config["k2"] == "v2"

    def test_get_by_prefix(self) -> None:
        p = self._make_provider({"app.debug": True, "app.name": "test", "db.host": "localhost"})
        self.mgr.add_provider(p)
        self.mgr.load()
        result = self.mgr.get_by_prefix("app")
        assert "debug" in result
        assert "name" in result
        assert "db.host" not in result

    def test_get_typed_correct_type(self) -> None:
        p = self._make_provider({"port": 8080})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr.get_typed("port", int) == 8080

    def test_get_typed_converts(self) -> None:
        p = self._make_provider({"port": "8080"})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr.get_typed("port", int) == 8080

    def test_get_typed_bool_conversion(self) -> None:
        p = self._make_provider({"debug": "true", "verbose": "no"})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr.get_typed("debug", bool) is True
        assert self.mgr.get_typed("verbose", bool) is False

    def test_get_typed_list_conversion(self) -> None:
        p = self._make_provider({"items": "a,b,c"})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr.get_typed("items", list) == ["a", "b", "c"]

    def test_get_typed_type_error(self) -> None:
        p = self._make_provider({"port": "not_a_number"})
        self.mgr.add_provider(p)
        self.mgr.load()
        with pytest.raises(ConfigTypeError):
            self.mgr.get_typed("port", int)

    def test_get_typed_none_default(self) -> None:
        p = self._make_provider({})
        self.mgr.add_provider(p)
        self.mgr.load()
        with pytest.raises(ConfigNotFoundError):
            self.mgr.get_typed("nonexistent", int)

    def test_reload_success(self) -> None:
        p = self._make_provider({"key": "val"})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr.reload() is True

    def test_reload_failure(self) -> None:
        from apps.core.config.exceptions import ConfigException

        p = MagicMock()
        p.priority = 10
        p.load.side_effect = ConfigException("config error")
        p.get_name.return_value = "BadProvider"
        self.mgr.add_provider(p)
        # ConfigException wraps ValueError-like errors but is a base Exception
        # The reload method catches (OSError, ValueError, KeyError) specifically
        # ConfigException will propagate
        with pytest.raises(ConfigException):
            self.mgr.reload()

    def test_listener_management(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener, key_filter="test.key")
        assert self.mgr.get_listener_count()["key_specific"] == 1
        self.mgr.remove_listener(listener)
        assert self.mgr.get_listener_count()["key_specific"] == 0

    def test_change_notification_on_set(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener, key_filter="test.key")
        self.mgr.set("test.key", "new_val")
        listener.on_config_added.assert_called_once_with("test.key", "new_val")

    def test_change_history(self) -> None:
        self.mgr.set("k1", "v1")
        self.mgr.set("k2", "v2")
        history = self.mgr.get_change_history()
        assert len(history) == 2

    def test_clear_change_history(self) -> None:
        self.mgr.set("k1", "v1")
        self.mgr.clear_change_history()
        assert self.mgr.get_change_history() == []

    def test_clear_cache(self) -> None:
        p = self._make_provider({"key": "val"})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr.is_loaded() is True
        self.mgr.clear_cache()
        assert self.mgr.is_loaded() is False

    def test_getitem(self) -> None:
        p = self._make_provider({"key": "val"})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr["key"] == "val"

    def test_setitem(self) -> None:
        self.mgr["key"] = "val"
        assert self.mgr.get("key") == "val"

    def test_contains(self) -> None:
        p = self._make_provider({"key": "val"})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert "key" in self.mgr
        assert "nope" not in self.mgr

    def test_len(self) -> None:
        p = self._make_provider({"k1": "v1", "k2": "v2"})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert len(self.mgr) == 2

    def test_get_last_reload_time(self) -> None:
        assert self.mgr.get_last_reload_time() == 0.0
        p = self._make_provider({"k": "v"})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr.get_last_reload_time() > 0

    def test_set_schema(self) -> None:
        schema = MagicMock(spec=ConfigSchema)
        self.mgr.set_schema(schema)
        # Should not raise

    def test_nested_config_merge(self) -> None:
        p = self._make_provider({"app": {"debug": True, "name": "test"}})
        self.mgr.add_provider(p)
        self.mgr.load()
        assert self.mgr.get("app.debug") is True
        assert self.mgr.get("app.name") == "test"

    def test_provider_priority_ordering(self) -> None:
        p1 = self._make_provider({"key": "low"})
        p1.priority = 1
        p2 = self._make_provider({"key": "high"})
        p2.priority = 10
        self.mgr.add_provider(p1)
        self.mgr.add_provider(p2)
        self.mgr.load()
        # Higher priority provider should win (loaded first, key not yet set)
        assert self.mgr.get("key") == "high"
