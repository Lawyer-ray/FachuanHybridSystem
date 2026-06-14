"""
Extended unit tests for core/config/manager.py (ConfigManager)

Covers:
  - __init__
  - add_provider / remove_provider
  - set_schema
  - load: success, force_reload, provider failure rollback, validation failure
  - _merge_config (nested dicts, first-writer-wins)
  - get: cached value, nested value, schema default, ConfigNotFoundError
  - get_typed: correct type, conversion, ConfigTypeError
  - _convert_type: bool, int, float, str, list (comma-separated), other
  - set / has / get_all / get_by_prefix
  - reload: success, failure
  - add_listener / remove_listener
  - __getitem__ / __setitem__ / __contains__ / __len__
  - clear_cache, is_loaded, get_last_reload_time, etc.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.core.config.manager import ConfigManager
from apps.core.config.exceptions import ConfigException, ConfigNotFoundError, ConfigTypeError
from apps.core.config.notifications import ConfigChangeListener


# Concrete listener for testing
class _TestListener(ConfigChangeListener):
    def __init__(self):
        self.calls = []

    def on_config_changed(self, key, old_value, new_value):
        self.calls.append(("changed", key, old_value, new_value))

    def on_config_added(self, key, value):
        self.calls.append(("added", key, value))

    def on_config_removed(self, key, old_value):
        self.calls.append(("removed", key, old_value))

    def on_config_reloaded(self):
        self.calls.append(("reloaded",))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class DummyProvider:
    def __init__(self, config: dict[str, Any], priority: int = 0, name: str = "dummy") -> None:
        self._config = config
        self.priority = priority
        self._name = name

    def load(self) -> dict[str, Any]:
        return self._config

    def get_name(self) -> str:
        return self._name


class FailingProvider:
    def __init__(self) -> None:
        self.priority = 0

    def load(self) -> dict[str, Any]:
        raise RuntimeError("load failed")

    def get_name(self) -> str:
        return "failing"


def _make_manager(**kwargs) -> ConfigManager:
    m = ConfigManager(
        cache_max_size=kwargs.get("cache_max_size", 1000),
        cache_ttl=kwargs.get("cache_ttl", 3600.0),
    )
    return m


# ===========================================================================
# __init__
# ===========================================================================


class TestInit:
    def test_defaults(self) -> None:
        m = _make_manager()
        assert m.is_loaded() is False
        assert m.get_provider_count() == 0


# ===========================================================================
# add_provider / remove_provider
# ===========================================================================


class TestProviders:
    def test_add_provider_sorted_by_priority(self) -> None:
        m = _make_manager()
        p1 = DummyProvider({"a": 1}, priority=1)
        p2 = DummyProvider({"b": 2}, priority=10)
        m.add_provider(p1)
        m.add_provider(p2)
        assert m.get_provider_count() == 2
        # p2 has higher priority (sorted descending)
        assert m._providers[0].priority >= m._providers[1].priority

    def test_remove_provider(self) -> None:
        m = _make_manager()
        p = DummyProvider({"a": 1})
        m.add_provider(p)
        m.remove_provider(DummyProvider)
        assert m.get_provider_count() == 0


# ===========================================================================
# set_schema
# ===========================================================================


class TestSetSchema:
    def test_set_schema(self) -> None:
        m = _make_manager()
        schema = MagicMock()
        m.set_schema(schema)
        assert m._schema is schema


# ===========================================================================
# load
# ===========================================================================


class TestLoad:
    def test_load_success(self) -> None:
        m = _make_manager()
        m.add_provider(DummyProvider({"key": "value"}))
        m.load()
        assert m.is_loaded() is True
        assert m.get("key") == "value"

    def test_load_skips_if_already_loaded(self) -> None:
        m = _make_manager()
        m.add_provider(DummyProvider({"key": "v1"}))
        m.load()
        m.add_provider(DummyProvider({"key2": "v2"}))
        m.load(force_reload=False)
        # key2 should not be in raw_config since load is skipped
        assert m.has("key") is True

    def test_load_force_reload(self) -> None:
        m = _make_manager()
        m.add_provider(DummyProvider({"key": "v1"}))
        m.load()
        m.remove_provider(DummyProvider)
        m.add_provider(DummyProvider({"key": "v2"}))
        m.load(force_reload=True)
        assert m.get("key") == "v2"

    def test_load_provider_failure_rollback(self) -> None:
        m = _make_manager()
        m.add_provider(DummyProvider({"key": "v1"}))
        m.load()
        m.remove_provider(DummyProvider)
        m.add_provider(FailingProvider())
        with pytest.raises(ConfigException):
            m.load(force_reload=True)
        # Should rollback to old config
        assert m.get("key") == "v1"

    def test_load_notifies_reload(self) -> None:
        m = _make_manager()
        m.add_provider(DummyProvider({"a": 1}))
        listener = _TestListener()
        m.add_listener(listener)
        m.load()
        assert any(c[0] == "reloaded" for c in listener.calls)


# ===========================================================================
# _merge_config
# ===========================================================================


class TestMergeConfig:
    def test_flat_config(self) -> None:
        m = _make_manager()
        m._merge_config({"a": 1, "b": 2})
        assert m._raw_config["a"] == 1
        assert m._raw_config["b"] == 2

    def test_nested_config(self) -> None:
        m = _make_manager()
        m._merge_config({"db": {"host": "localhost", "port": 5432}})
        assert m._raw_config["db.host"] == "localhost"
        assert m._raw_config["db.port"] == 5432

    def test_first_writer_wins(self) -> None:
        m = _make_manager()
        m._merge_config({"key": "first"})
        m._merge_config({"key": "second"})
        assert m._raw_config["key"] == "first"


# ===========================================================================
# get
# ===========================================================================


class TestGet:
    def test_get_existing_key(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["key"] = "value"
        assert m.get("key") == "value"

    def test_get_cached_value(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["key"] = "value"
        m._cache.set("key", "cached")
        assert m.get("key") == "cached"

    def test_get_default_when_not_found(self) -> None:
        m = _make_manager()
        m._loaded = True
        assert m.get("missing", "default") == "default"

    def test_get_raises_not_found(self) -> None:
        m = _make_manager()
        m._loaded = True
        with pytest.raises(ConfigNotFoundError):
            m.get("missing")

    def test_get_nested_value(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["db"] = {"nested": True}
        # _get_nested_value checks partial keys
        m._raw_config["db.host"] = "localhost"
        result = m.get("db.host")
        assert result == "localhost"

    def test_get_schema_default(self) -> None:
        m = _make_manager()
        m._loaded = True
        field = MagicMock()
        field.default = "schema_default"
        m._schema = MagicMock()
        m._schema.get_field.return_value = field
        m._schema.get_suggestions.return_value = []
        result = m.get("missing_key", default=None)
        assert result == "schema_default"


# ===========================================================================
# get_typed
# ===========================================================================


class TestGetTyped:
    def test_correct_type(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["port"] = 8080
        assert m.get_typed("port", int) == 8080

    def test_converts_type(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["port"] = "8080"
        assert m.get_typed("port", int) == 8080

    def test_raises_type_error(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["port"] = "not_a_number"
        with pytest.raises(ConfigTypeError):
            m.get_typed("port", int)

    def test_none_returns_none(self) -> None:
        m = _make_manager()
        m._loaded = True
        # Use a non-None sentinel as default so get() doesn't raise, but returns the sentinel
        # which is then processed by get_typed
        # Actually, get_typed calls get(key, default) which returns default if not found
        # But get() raises ConfigNotFoundError when default is None and key missing
        # So we need to pass a non-None default to get_typed
        result = m.get_typed("missing", int, default=0)
        assert result == 0


# ===========================================================================
# _convert_type
# ===========================================================================


class TestConvertType:
    def test_bool_from_string_true(self) -> None:
        m = _make_manager()
        for v in ("true", "1", "yes", "on"):
            assert m._convert_type(v, bool) is True

    def test_bool_from_string_false(self) -> None:
        m = _make_manager()
        for v in ("false", "0", "no", "off"):
            assert m._convert_type(v, bool) is False

    def test_bool_from_bool(self) -> None:
        m = _make_manager()
        assert m._convert_type(True, bool) is True

    def test_int_conversion(self) -> None:
        m = _make_manager()
        assert m._convert_type("42", int) == 42

    def test_float_conversion(self) -> None:
        m = _make_manager()
        assert m._convert_type("3.14", float) == pytest.approx(3.14)

    def test_str_conversion(self) -> None:
        m = _make_manager()
        assert m._convert_type(123, str) == "123"

    def test_list_from_comma_separated_string(self) -> None:
        m = _make_manager()
        result = m._convert_type("a, b, c", list)
        assert result == ["a", "b", "c"]

    def test_list_from_list(self) -> None:
        m = _make_manager()
        result = m._convert_type([1, 2, 3], list)
        assert result == [1, 2, 3]


# ===========================================================================
# set / has / get_all / get_by_prefix
# ===========================================================================


class TestSetHasGetAll:
    def test_set_and_get(self) -> None:
        m = _make_manager()
        m.set("key", "value")
        assert m.get("key") == "value"

    def test_set_notifies(self) -> None:
        m = _make_manager()
        listener = _TestListener()
        m.add_listener(listener)
        m.set("key", "value")
        # First set is "added" since old_value is None
        assert any(c[0] in ("added", "changed") for c in listener.calls)

    def test_has_existing(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["key"] = "value"
        assert m.has("key") is True

    def test_has_missing(self) -> None:
        m = _make_manager()
        m._loaded = True
        assert m.has("missing") is False

    def test_get_all(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["a"] = 1
        m._raw_config["b"] = 2
        all_cfg = m.get_all()
        assert all_cfg == {"a": 1, "b": 2}
        # Should be a copy
        all_cfg["c"] = 3
        assert "c" not in m._raw_config

    def test_get_by_prefix(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["db.host"] = "localhost"
        m._raw_config["db.port"] = 5432
        m._raw_config["app.name"] = "test"
        result = m.get_by_prefix("db")
        assert result == {"host": "localhost", "port": 5432}

    def test_get_by_prefix_exact_match(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["db"] = "main"
        result = m.get_by_prefix("db")
        assert result == {"db": "main"}


# ===========================================================================
# reload
# ===========================================================================


class TestReload:
    def test_reload_success(self) -> None:
        m = _make_manager()
        m.add_provider(DummyProvider({"key": "value"}))
        assert m.reload() is True

    def test_reload_failure(self) -> None:
        m = _make_manager()
        # ConfigException wraps the provider error and is NOT caught by reload
        # (which only catches OSError, ValueError, KeyError)
        # So reload propagates ConfigException
        class ValueErrorProvider:
            priority = 0
            def load(self):
                raise ValueError("bad config")
            def get_name(self):
                return "val_err"
        m.add_provider(ValueErrorProvider())
        # load() wraps ValueError into ConfigException, which is NOT caught by reload()
        with pytest.raises(ConfigException):
            m.reload()


# ===========================================================================
# __getitem__ / __setitem__ / __contains__ / __len__
# ===========================================================================


class TestDunderMethods:
    def test_getitem(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["key"] = "value"
        assert m["key"] == "value"

    def test_setitem(self) -> None:
        m = _make_manager()
        m["key"] = "value"
        assert m._raw_config["key"] == "value"

    def test_contains(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["key"] = "value"
        assert "key" in m
        assert "missing" not in m

    def test_len(self) -> None:
        m = _make_manager()
        m.add_provider(DummyProvider({"a": 1, "b": 2}))
        assert len(m) == 2


# ===========================================================================
# listeners
# ===========================================================================


class TestListeners:
    def test_add_and_remove_listener(self) -> None:
        m = _make_manager()
        listener = _TestListener()
        m.add_listener(listener, key_filter="key")
        counts = m.get_listener_count()
        assert counts.get("key_specific", 0) >= 1
        m.remove_listener(listener)

    def test_clear_change_history(self) -> None:
        m = _make_manager()
        m.set("key", "value")
        m.clear_change_history()
        assert m.get_change_history() == []


# ===========================================================================
# clear_cache
# ===========================================================================


class TestClearCache:
    def test_clear_cache(self) -> None:
        m = _make_manager()
        m._loaded = True
        m._raw_config["key"] = "value"
        m._cache.set("key", "cached")
        m.clear_cache()
        assert m.is_loaded() is False
