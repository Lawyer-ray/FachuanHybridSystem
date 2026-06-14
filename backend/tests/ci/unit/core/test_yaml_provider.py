"""Tests for apps.core.config.providers.yaml — YamlProvider."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from apps.core.config.exceptions import ConfigException, ConfigFileError


class TestYamlProvider:
    def _make_provider(self, content: str) -> tuple:
        """Create a YamlProvider with a temp YAML file."""
        from apps.core.config.providers.yaml import YamlProvider

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
        tmp.write(content)
        tmp.flush()
        tmp.close()
        provider = YamlProvider(tmp.name, watch_file=False)
        return provider, Path(tmp.name)

    def test_priority(self) -> None:
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/nonexistent")
        assert p.priority == 50

    def test_supports_reload(self) -> None:
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/nonexistent")
        assert p.supports_reload() is True

    def test_get_file_path(self) -> None:
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/tmp/test.yaml")
        assert p.get_file_path() == "/tmp/test.yaml"

    def test_load_missing_file(self) -> None:
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/nonexistent/path/config.yaml")
        with pytest.raises(ConfigFileError, match="不存在"):
            p.load()

    def test_load_valid_yaml(self) -> None:
        provider, path = self._make_provider("key1: value1\nkey2: value2\n")
        try:
            result = provider.load()
            assert result["key1"] == "value1"
            assert result["key2"] == "value2"
        finally:
            path.unlink()

    def test_load_nested_yaml(self) -> None:
        provider, path = self._make_provider("a:\n  b: 1\n  c: hello\n")
        try:
            result = provider.load()
            assert result["a.b"] == 1
            assert result["a.c"] == "hello"
        finally:
            path.unlink()

    def test_load_invalid_yaml(self) -> None:
        provider, path = self._make_provider("{{{{invalid yaml: [}}}}")
        try:
            with pytest.raises(ConfigFileError, match="YAML"):
                provider.load()
        finally:
            path.unlink()

    def test_load_returns_same_cache(self) -> None:
        provider, path = self._make_provider("key: val\n")
        try:
            r1 = provider.load()
            r2 = provider.load()
            assert r1 is r2  # Same cached dict
        finally:
            path.unlink()

    def test_variable_substitution(self) -> None:
        provider, path = self._make_provider("host: ${NONEXISTENT_VAR_12345:localhost}\n")
        try:
            result = provider.load()
            assert result["host"] == "localhost"
        finally:
            path.unlink()


class TestFlattenDict:
    def test_flat_dict(self) -> None:
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/tmp/x.yaml")
        result = p._flatten_dict({"a": 1, "b": 2})
        assert result == {"a": 1, "b": 2}

    def test_nested_dict(self) -> None:
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/tmp/x.yaml")
        result = p._flatten_dict({"a": {"b": 1, "c": 2}})
        assert result == {"a.b": 1, "a.c": 2}

    def test_deeply_nested(self) -> None:
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/tmp/x.yaml")
        result = p._flatten_dict({"a": {"b": {"c": 3}}})
        assert result == {"a.b.c": 3}

    def test_empty_dict(self) -> None:
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/tmp/x.yaml")
        assert p._flatten_dict({}) == {}


class TestSubstituteVariables:
    def test_env_var_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.core.config.providers.yaml import YamlProvider

        monkeypatch.setenv("TEST_YAML_VAR_XYZ", "found_it")
        p = YamlProvider("/tmp/x.yaml")
        result = p._substitute_variables("val: ${TEST_YAML_VAR_XYZ:fallback}")
        assert "found_it" in result

    def test_env_var_missing_with_default(self) -> None:
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/tmp/x.yaml")
        result = p._substitute_variables("val: ${NONEXISTENT_VAR_ABC:default_value}")
        assert "default_value" in result

    def test_env_var_missing_no_default(self) -> None:
        from apps.core.config.providers.yaml import YamlProvider

        p = YamlProvider("/tmp/x.yaml")
        result = p._substitute_variables("val: ${NONEXISTENT_VAR_ABC}")
        # Should substitute to empty string
        assert "NONEXISTENT_VAR_ABC" not in result
