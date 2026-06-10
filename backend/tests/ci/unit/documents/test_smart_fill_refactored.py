"""Tests for refactored pure functions from documents/services/smart_fill/."""

from __future__ import annotations

import pytest

from apps.documents.services.smart_fill.service import (
    AUTO_FILL_KEYS,
    PlaceholderResult,
    SmartFillResult,
    SmartFillService,
)


class TestAutoFillKeys:
    """Tests for AUTO_FILL_KEYS constant."""

    def test_contains_today_date(self):
        assert "今天日期" in AUTO_FILL_KEYS

    def test_contains_current_date(self):
        assert "当前日期" in AUTO_FILL_KEYS

    def test_contains_current_year(self):
        assert "今年年份" in AUTO_FILL_KEYS

    def test_is_set(self):
        assert isinstance(AUTO_FILL_KEYS, set)


class TestPlaceholderResult:
    """Tests for PlaceholderResult dataclass."""

    def test_basic_creation(self):
        result = PlaceholderResult(key="name", value="Alice", source="llm")
        assert result.key == "name"
        assert result.value == "Alice"
        assert result.source == "llm"

    def test_auto_source(self):
        result = PlaceholderResult(key="今天日期", value="2026年01月15日", source="auto")
        assert result.source == "auto"

    def test_fallback_source(self):
        result = PlaceholderResult(key="unknown", value="/", source="fallback")
        assert result.source == "fallback"


class TestSmartFillResult:
    """Tests for SmartFillResult dataclass."""

    def test_default_values(self):
        result = SmartFillResult()
        assert result.placeholders == []
        assert result.rendered_bytes is None
        assert result.error is None

    def test_with_placeholders(self):
        items = [PlaceholderResult(key="a", value="1", source="llm")]
        result = SmartFillResult(placeholders=items)
        assert len(result.placeholders) == 1

    def test_with_error(self):
        result = SmartFillResult(error="Something failed")
        assert result.error == "Something failed"

    def test_with_rendered_bytes(self):
        result = SmartFillResult(rendered_bytes=b"pdf content")
        assert result.rendered_bytes == b"pdf content"


class TestSmartFillServiceBuildCatalog:
    """Tests for _build_catalog method."""

    def setup_method(self):
        # Mock LLM service
        class MockLLM:
            def complete(self, **kwargs):
                pass

        self.service = SmartFillService(llm_service=MockLLM())

    def test_empty_keys(self):
        result = self.service._build_catalog([])
        assert result == ""

    def test_auto_fill_key(self):
        result = self.service._build_catalog(["今天日期"])
        assert "自动填充" in result
        assert "{{ 今天日期 }}" in result

    def test_custom_placeholder(self):
        result = self.service._build_catalog(["自定义占位符"])
        assert "模板自定义占位符" in result

    def test_multiple_keys(self):
        result = self.service._build_catalog(["今天日期", "自定义"])
        lines = result.split("\n")
        assert len(lines) == 2


class TestSmartFillServiceBuildResultItems:
    """Tests for _build_result_items method."""

    def setup_method(self):
        class MockLLM:
            def complete(self, **kwargs):
                pass

        self.service = SmartFillService(llm_service=MockLLM())

    def test_auto_fill_items(self):
        keys = ["今天日期", "当前日期", "今年年份"]
        items = self.service._build_result_items(keys, {})
        assert len(items) == 3
        for item in items:
            assert item.source == "auto"

    def test_llm_items(self):
        keys = ["name"]
        llm_values = {"name": "Alice"}
        items = self.service._build_result_items(keys, llm_values)
        assert len(items) == 1
        assert items[0].source == "llm"
        assert items[0].value == "Alice"

    def test_fallback_items(self):
        keys = ["unknown"]
        items = self.service._build_result_items(keys, {})
        assert len(items) == 1
        assert items[0].source == "fallback"

    def test_mixed_items(self):
        keys = ["今天日期", "name", "unknown"]
        llm_values = {"name": "Alice"}
        items = self.service._build_result_items(keys, llm_values)
        assert len(items) == 3
        sources = [item.source for item in items]
        assert "auto" in sources
        assert "llm" in sources
        assert "fallback" in sources

    def test_empty_keys(self):
        items = self.service._build_result_items([], {})
        assert items == []

    def test_llm_value_empty_string_goes_to_fallback(self):
        keys = ["name"]
        llm_values = {"name": ""}
        items = self.service._build_result_items(keys, llm_values)
        assert items[0].source == "fallback"


class TestSmartFillServiceCallLLM:
    """Tests for _call_llm method."""

    def setup_method(self):
        class MockLLM:
            def complete(self, **kwargs):
                class Response:
                    content = '{"name": "Alice", "date": "2026-01-15"}'

                return Response()

        self.service = SmartFillService(llm_service=MockLLM())

    def test_basic_call(self):
        result = self.service._call_llm("catalog", "user input")
        assert isinstance(result, dict)
        assert "name" in result

    def test_values_are_strings(self):
        result = self.service._call_llm("catalog", "user input")
        for v in result.values():
            assert isinstance(v, str)
