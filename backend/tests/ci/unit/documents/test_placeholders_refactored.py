"""Tests for refactored pure functions from documents/services/placeholders/."""

from __future__ import annotations

import pytest

from apps.documents.services.placeholders.fallback import (
    PLACEHOLDER_FALLBACK_VALUE,
    normalize_placeholder_value,
    normalize_service_result,
    ensure_required_placeholders,
    resolve_render_variable,
    get_service_placeholder_keys,
)


class TestNormalizePlaceholderValue:
    """Tests for normalize_placeholder_value pure function."""

    def test_none_returns_fallback(self):
        assert normalize_placeholder_value(None) == PLACEHOLDER_FALLBACK_VALUE

    def test_empty_string_returns_fallback(self):
        assert normalize_placeholder_value("") == PLACEHOLDER_FALLBACK_VALUE

    def test_whitespace_string_returns_fallback(self):
        assert normalize_placeholder_value("   ") == PLACEHOLDER_FALLBACK_VALUE

    def test_non_empty_string_returned(self):
        assert normalize_placeholder_value("hello") == "hello"

    def test_number_returned(self):
        assert normalize_placeholder_value(42) == 42

    def test_zero_returned(self):
        assert normalize_placeholder_value(0) == 0

    def test_false_returned(self):
        assert normalize_placeholder_value(False) is False

    def test_list_returned(self):
        assert normalize_placeholder_value([1, 2]) == [1, 2]

    def test_empty_list_returned(self):
        assert normalize_placeholder_value([]) == []

    def test_custom_fallback(self):
        assert normalize_placeholder_value(None, fallback_value="N/A") == "N/A"

    def test_empty_string_custom_fallback(self):
        assert normalize_placeholder_value("", fallback_value="-") == "-"


class TestNormalizeServiceResult:
    """Tests for normalize_service_result pure function."""

    def test_none_returns_expected_keys_with_fallback(self):
        result = normalize_service_result(None, expected_keys=["a", "b"])
        assert result == {"a": PLACEHOLDER_FALLBACK_VALUE, "b": PLACEHOLDER_FALLBACK_VALUE}

    def test_empty_dict_returns_expected_keys(self):
        result = normalize_service_result({}, expected_keys=["a"])
        assert result == {"a": PLACEHOLDER_FALLBACK_VALUE}

    def test_values_normalized(self):
        result = normalize_service_result({"a": "value", "b": None}, expected_keys=["a", "b", "c"])
        assert result["a"] == "value"
        assert result["b"] == PLACEHOLDER_FALLBACK_VALUE
        assert result["c"] == PLACEHOLDER_FALLBACK_VALUE

    def test_no_expected_keys(self):
        result = normalize_service_result({"a": "value"}, expected_keys=[])
        assert result == {"a": "value"}

    def test_none_no_expected_keys(self):
        result = normalize_service_result(None, expected_keys=[])
        assert result == {}

    def test_custom_fallback(self):
        result = normalize_service_result({"a": None}, expected_keys=["b"], fallback_value="N/A")
        assert result == {"a": "N/A", "b": "N/A"}

    def test_existing_value_preserved(self):
        result = normalize_service_result({"a": "hello"}, expected_keys=["a"])
        assert result["a"] == "hello"


class TestEnsureRequiredPlaceholders:
    """Tests for ensure_required_placeholders pure function."""

    def test_empty_context_empty_required(self):
        result = ensure_required_placeholders({}, None)
        assert result == {}

    def test_empty_context_with_required(self):
        result = ensure_required_placeholders({}, ["a", "b"])
        assert result == {"a": PLACEHOLDER_FALLBACK_VALUE, "b": PLACEHOLDER_FALLBACK_VALUE}

    def test_context_with_required(self):
        result = ensure_required_placeholders({"a": "value"}, ["a", "b"])
        assert result == {"a": "value", "b": PLACEHOLDER_FALLBACK_VALUE}

    def test_none_values_normalized(self):
        result = ensure_required_placeholders({"a": None}, ["a"])
        assert result == {"a": PLACEHOLDER_FALLBACK_VALUE}

    def test_empty_string_normalized(self):
        result = ensure_required_placeholders({"a": ""}, ["a"])
        assert result == {"a": PLACEHOLDER_FALLBACK_VALUE}

    def test_custom_fallback(self):
        result = ensure_required_placeholders({}, ["a"], fallback_value="N/A")
        assert result == {"a": "N/A"}

    def test_none_required_placeholders(self):
        result = ensure_required_placeholders({"a": "value"}, None)
        assert result == {"a": "value"}


class TestResolveRenderVariable:
    """Tests for resolve_render_variable pure function."""

    def test_variable_exists(self):
        found, value = resolve_render_variable({"name": "test"}, "name")
        assert found is True
        assert value == "test"

    def test_variable_not_found(self):
        found, value = resolve_render_variable({}, "name")
        assert found is False
        assert value == PLACEHOLDER_FALLBACK_VALUE

    def test_variable_none(self):
        found, value = resolve_render_variable({"name": None}, "name")
        assert found is False
        assert value == PLACEHOLDER_FALLBACK_VALUE

    def test_variable_number(self):
        found, value = resolve_render_variable({"count": 42}, "count")
        assert found is True
        assert value == "42"

    def test_custom_fallback(self):
        found, value = resolve_render_variable({}, "name", fallback_value="N/A")
        assert found is False
        assert value == "N/A"

    def test_empty_string_found(self):
        found, value = resolve_render_variable({"name": ""}, "name")
        assert found is True
        assert value == ""


class TestGetServicePlaceholderKeys:
    """Tests for get_service_placeholder_keys pure function."""

    def test_service_with_get_placeholder_keys(self):
        class MockService:
            def get_placeholder_keys(self):
                return ["a", "b"]

        result = get_service_placeholder_keys(MockService())
        assert result == ["a", "b"]

    def test_service_with_placeholder_keys_attr(self):
        class MockService:
            placeholder_keys = ["x", "y"]

        result = get_service_placeholder_keys(MockService())
        assert result == ["x", "y"]

    def test_service_with_no_keys(self):
        class MockService:
            pass

        result = get_service_placeholder_keys(MockService())
        assert result == []

    def test_service_with_string_keys_filtered(self):
        class MockService:
            def get_placeholder_keys(self):
                return ["a", "", "  ", "b"]

        result = get_service_placeholder_keys(MockService())
        assert result == ["a", "b"]

    def test_service_with_non_iterable_keys(self):
        class MockService:
            def get_placeholder_keys(self):
                return "not a list"

        result = get_service_placeholder_keys(MockService())
        assert result == []

    def test_service_with_none_keys(self):
        class MockService:
            def get_placeholder_keys(self):
                return None

        result = get_service_placeholder_keys(MockService())
        assert result == []
