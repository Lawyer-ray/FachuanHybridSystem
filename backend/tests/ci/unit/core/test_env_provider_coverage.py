"""Coverage tests for core.config.providers.env — EnvProvider."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from apps.core.config.exceptions import ConfigException
from apps.core.config.providers.env import EnvProvider


class TestEnvProviderInit:
    def test_default_init(self) -> None:
        provider = EnvProvider()
        assert provider.prefix == ""
        assert provider.type_mapping == {}
        assert provider.priority == 100
        assert provider.supports_reload() is False

    def test_init_with_prefix(self) -> None:
        provider = EnvProvider(prefix="MYAPP_")
        assert provider.prefix == "MYAPP_"

    def test_init_with_type_mapping(self) -> None:
        provider = EnvProvider(type_mapping={"PORT": int, "DEBUG": bool})
        assert provider.type_mapping == {"PORT": int, "DEBUG": bool}


class TestEnvProviderLoad:
    def test_load_filters_by_prefix(self) -> None:
        provider = EnvProvider(prefix="TEST_ENV_PREFIX_")
        with patch.dict(os.environ, {"TEST_ENV_PREFIX_FOO": "bar", "OTHER_VAR": "baz"}):
            config = provider.load()
            assert config.get("foo") == "bar"
            assert "other_var" not in config

    def test_load_without_prefix(self) -> None:
        provider = EnvProvider()
        with patch.dict(os.environ, {"MY_TEST_VAR_XYZ": "value123"}):
            config = provider.load()
            assert "my.test.var.xyz" in config or "MY_TEST_VAR_XYZ" in config

    def test_load_type_conversion_int(self) -> None:
        provider = EnvProvider(type_mapping={"TEST_PORT_NUM": int})
        with patch.dict(os.environ, {"TEST_PORT_NUM": "8080"}):
            config = provider.load()
            assert config.get("test.port.num") == 8080

    def test_load_type_conversion_float(self) -> None:
        provider = EnvProvider(type_mapping={"TEST_RATE": float})
        with patch.dict(os.environ, {"TEST_RATE": "3.14"}):
            config = provider.load()
            assert config.get("test.rate") == 3.14

    def test_load_type_conversion_bool(self) -> None:
        provider = EnvProvider(type_mapping={"TEST_FLAG": bool})
        with patch.dict(os.environ, {"TEST_FLAG": "true"}):
            config = provider.load()
            assert config.get("test.flag") is True

    def test_load_type_conversion_list(self) -> None:
        provider = EnvProvider(type_mapping={"TEST_ITEMS": list})
        with patch.dict(os.environ, {"TEST_ITEMS": "a,b,c"}):
            config = provider.load()
            assert config.get("test.items") == ["a", "b", "c"]

    def test_load_type_conversion_dict(self) -> None:
        provider = EnvProvider(type_mapping={"TEST_MAP": dict})
        with patch.dict(os.environ, {"TEST_MAP": "key1=val1,key2=val2"}):
            config = provider.load()
            assert config.get("test.map") == {"key1": "val1", "key2": "val2"}

    def test_load_type_conversion_str_fallback(self) -> None:
        provider = EnvProvider(type_mapping={"TEST_STR": str})
        with patch.dict(os.environ, {"TEST_STR": "hello"}):
            config = provider.load()
            assert config.get("test.str") == "hello"

    def test_load_type_conversion_failure(self) -> None:
        provider = EnvProvider(type_mapping={"TEST_BAD": int})
        with patch.dict(os.environ, {"TEST_BAD": "not_a_number"}):
            with pytest.raises(ConfigException, match="类型转换失败"):
                provider.load()


class TestAutoCast:
    def test_auto_cast_bool_true(self) -> None:
        provider = EnvProvider()
        assert provider._auto_cast("true") is True
        assert provider._auto_cast("yes") is True
        assert provider._auto_cast("1") is True

    def test_auto_cast_bool_false(self) -> None:
        provider = EnvProvider()
        assert provider._auto_cast("false") is False
        assert provider._auto_cast("no") is False
        assert provider._auto_cast("0") is False

    def test_auto_cast_integer(self) -> None:
        provider = EnvProvider()
        assert provider._auto_cast("42") == 42
        assert provider._auto_cast("-7") == -7

    def test_auto_cast_float(self) -> None:
        provider = EnvProvider()
        assert provider._auto_cast("3.14") == 3.14

    def test_auto_cast_list(self) -> None:
        provider = EnvProvider()
        assert provider._auto_cast("a,b,c") == ["a", "b", "c"]

    def test_auto_cast_string_fallback(self) -> None:
        provider = EnvProvider()
        assert provider._auto_cast("hello world") == "hello world"

    def test_auto_cast_float_value_error(self) -> None:
        """When float() fails on a string with a dot, returns the string."""
        provider = EnvProvider()
        result = provider._auto_cast("1.2.3")
        assert result == "1.2.3"

    def test_parse_bool_variants(self) -> None:
        provider = EnvProvider()
        assert provider._parse_bool("TRUE") is True
        assert provider._parse_bool("FALSE") is False
        assert provider._parse_bool("on") is True
        assert provider._parse_bool("enabled") is True
        assert provider._parse_bool("OFF") is False


class TestParseListAndDict:
    def test_parse_list_with_spaces(self) -> None:
        provider = EnvProvider()
        result = provider._parse_list(" a , b , c ")
        assert result == ["a", "b", "c"]

    def test_parse_list_empty_items_filtered(self) -> None:
        provider = EnvProvider()
        result = provider._parse_list("a,,b,,")
        assert result == ["a", "b"]

    def test_parse_dict_basic(self) -> None:
        provider = EnvProvider()
        result = provider._parse_dict("k1=v1,k2=v2")
        assert result == {"k1": "v1", "k2": "v2"}

    def test_parse_dict_with_equals_in_value(self) -> None:
        provider = EnvProvider()
        result = provider._parse_dict("k1=v=1")
        assert result == {"k1": "v=1"}

    def test_parse_dict_no_equals(self) -> None:
        provider = EnvProvider()
        result = provider._parse_dict("invalid_entry")
        assert result == {}


class TestNormalizeKey:
    def test_normalize_key(self) -> None:
        provider = EnvProvider()
        assert provider._normalize_key("DB_HOST") == "db.host"
        assert provider._normalize_key("SIMPLE") == "simple"
        assert provider._normalize_key("A_B_C") == "a.b.c"
