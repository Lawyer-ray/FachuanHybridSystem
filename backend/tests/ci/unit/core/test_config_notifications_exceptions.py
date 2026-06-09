"""Tests for core config exceptions, notifications, and manager."""

from __future__ import annotations

import time
from abc import ABC
from unittest.mock import MagicMock

import pytest

from apps.core.config.exceptions import (
    ConfigException,
    ConfigFileError,
    ConfigNotFoundError,
    ConfigTypeError,
    ConfigValidationError,
    SensitiveConfigError,
)
from apps.core.config.notifications import (
    ConfigChangeEvent,
    ConfigChangeListener,
    ConfigNotificationManager,
)


# ---------------------------------------------------------------------------
# Config exceptions
# ---------------------------------------------------------------------------


class TestConfigException:
    def test_basic(self) -> None:
        e = ConfigException("something wrong")
        assert e.message == "something wrong"
        assert e.code == "ConfigException"
        assert "something wrong" in str(e)

    def test_with_code(self) -> None:
        e = ConfigException("error", code="MY_CODE")
        assert e.code == "MY_CODE"

    def test_repr(self) -> None:
        e = ConfigException("msg")
        assert "ConfigException" in repr(e)
        assert "msg" in repr(e)


class TestConfigNotFoundError:
    def test_basic(self) -> None:
        e = ConfigNotFoundError("my.key")
        assert e.key == "my.key"
        assert e.suggestions == []
        assert "my.key" in str(e)

    def test_with_suggestions(self) -> None:
        e = ConfigNotFoundError("my.key", suggestions=["my.key1", "my.key2"])
        assert "my.key1" in str(e)
        assert e.code == "CONFIG_NOT_FOUND"


class TestConfigTypeError:
    def test_basic(self) -> None:
        e = ConfigTypeError("key", int, str)
        assert e.key == "key"
        assert e.expected_type is int
        assert e.actual_type is str
        assert "int" in str(e)
        assert "str" in str(e)

    def test_with_value(self) -> None:
        e = ConfigTypeError("key", int, str, value="abc")
        assert e.value == "abc"
        assert "abc" in str(e)


class TestConfigValidationError:
    def test_basic(self) -> None:
        e = ConfigValidationError(["error1", "error2"])
        assert e.errors == ["error1", "error2"]
        assert "error1" in str(e)

    def test_with_key(self) -> None:
        e = ConfigValidationError(["out of range"], key="port")
        assert e.key == "port"
        assert "port" in str(e)


class TestConfigFileError:
    def test_basic(self) -> None:
        e = ConfigFileError("/etc/config.yaml")
        assert e.path == "/etc/config.yaml"
        assert e.line is None

    def test_with_line(self) -> None:
        e = ConfigFileError("/etc/config.yaml", line=42)
        assert "42" in str(e)

    def test_with_message(self) -> None:
        e = ConfigFileError("/etc/config.yaml", message="invalid syntax")
        assert "invalid syntax" in str(e)

    def test_with_original_error(self) -> None:
        orig = ValueError("bad value")
        e = ConfigFileError("/etc/config.yaml", original_error=orig)
        assert "bad value" in str(e)


class TestSensitiveConfigError:
    def test_basic(self) -> None:
        e = SensitiveConfigError("SECRET_KEY")
        assert e.key == "SECRET_KEY"
        assert "SECRET_KEY" in str(e)

    def test_with_environment(self) -> None:
        e = SensitiveConfigError("SECRET_KEY", environment="production")
        assert "production" in str(e)


# ---------------------------------------------------------------------------
# ConfigChangeListener
# ---------------------------------------------------------------------------


class TestConfigChangeListener:
    def test_abstract(self) -> None:
        with pytest.raises(TypeError):
            ConfigChangeListener()  # type: ignore[abstract]

    def test_concrete_subclass(self) -> None:
        class MyListener(ConfigChangeListener):
            def on_config_changed(self, key, old_value, new_value):
                pass

        listener = MyListener()
        listener.on_config_added("k", "v")
        listener.on_config_removed("k", "v")
        listener.on_config_reloaded()


# ---------------------------------------------------------------------------
# ConfigChangeEvent
# ---------------------------------------------------------------------------


class TestConfigChangeEvent:
    def test_dataclass(self) -> None:
        e = ConfigChangeEvent(key="k", old_value="old", new_value="new", change_type="modified")
        assert e.key == "k"
        assert e.change_type == "modified"
        assert isinstance(e.timestamp, float)


# ---------------------------------------------------------------------------
# ConfigNotificationManager
# ---------------------------------------------------------------------------


class TestConfigNotificationManager:
    def setup_method(self) -> None:
        self.mgr = ConfigNotificationManager()

    def test_add_global_listener(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener)
        counts = self.mgr.get_listener_count()
        assert counts["global"] == 1

    def test_add_key_listener(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener, key_filter="my.key")
        counts = self.mgr.get_listener_count()
        assert counts["key_specific"] == 1

    def test_add_prefix_listener(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener, prefix_filter="app.")
        counts = self.mgr.get_listener_count()
        assert counts["prefix_specific"] == 1

    def test_add_duplicate_listener_not_duplicated(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener)
        self.mgr.add_listener(listener)
        assert self.mgr.get_listener_count()["global"] == 1

    def test_remove_global_listener(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener)
        self.mgr.remove_listener(listener)
        assert self.mgr.get_listener_count()["global"] == 0

    def test_remove_key_listener(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener, key_filter="my.key")
        self.mgr.remove_listener(listener)
        assert self.mgr.get_listener_count()["key_specific"] == 0

    def test_remove_prefix_listener(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener, prefix_filter="app.")
        self.mgr.remove_listener(listener)
        assert self.mgr.get_listener_count()["prefix_specific"] == 0

    def test_notify_change_modified(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener)
        self.mgr.notify_change("key", "old", "new")
        listener.on_config_changed.assert_called_once_with("key", "old", "new")

    def test_notify_change_added(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener)
        self.mgr.notify_change("key", None, "new")
        listener.on_config_added.assert_called_once_with("key", "new")

    def test_notify_change_removed(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener)
        self.mgr.notify_change("key", "old", None)
        listener.on_config_removed.assert_called_once_with("key", "old")

    def test_notify_key_specific_listener(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener, key_filter="target.key")
        self.mgr.notify_change("target.key", "old", "new")
        listener.on_config_changed.assert_called_once()

    def test_notify_prefix_listener(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener, prefix_filter="app.")
        self.mgr.notify_change("app.setting", "old", "new")
        listener.on_config_changed.assert_called_once()

    def test_notify_prefix_listener_not_matching(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener, prefix_filter="app.")
        self.mgr.notify_change("other.setting", "old", "new")
        listener.on_config_changed.assert_not_called()

    def test_determine_change_type(self) -> None:
        assert ConfigNotificationManager._determine_change_type(None, "v") == "added"
        assert ConfigNotificationManager._determine_change_type("v", None) == "removed"
        assert ConfigNotificationManager._determine_change_type("old", "new") == "modified"

    def test_dispatch_exception_handled(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        listener.on_config_changed.side_effect = Exception("boom")
        self.mgr.add_listener(listener)
        # Should not raise
        self.mgr.notify_change("key", "old", "new")

    def test_notify_reload(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        self.mgr.add_listener(listener)
        self.mgr.notify_reload()
        listener.on_config_reloaded.assert_called_once()

    def test_notify_reload_exception_handled(self) -> None:
        listener = MagicMock(spec=ConfigChangeListener)
        listener.on_config_reloaded.side_effect = Exception("boom")
        self.mgr.add_listener(listener)
        # Should not raise
        self.mgr.notify_reload()

    def test_event_history(self) -> None:
        self.mgr.notify_change("k1", None, "v1")
        self.mgr.notify_change("k2", "old", "new")
        history = self.mgr.get_event_history()
        assert len(history) == 2

    def test_event_history_with_limit(self) -> None:
        for i in range(5):
            self.mgr.notify_change(f"k{i}", None, f"v{i}")
        history = self.mgr.get_event_history(limit=2)
        assert len(history) == 2

    def test_clear_history(self) -> None:
        self.mgr.notify_change("k", None, "v")
        self.mgr.clear_history()
        assert self.mgr.get_event_history() == []

    def test_history_max_size(self) -> None:
        mgr = ConfigNotificationManager()
        mgr._max_history = 3
        for i in range(5):
            mgr.notify_change(f"k{i}", None, f"v{i}")
        assert len(mgr.get_event_history()) == 3
