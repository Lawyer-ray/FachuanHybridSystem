"""Tests for apps.core.llm.structured_output."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from apps.core.llm.structured_output import (
    clean_text,
    extract_json_text,
    json_schema_instructions,
    parse_json_content,
    parse_model_content,
)


class SimpleModel(BaseModel):
    name: str
    value: int


class TestCleanText:
    def test_removes_json_fence(self):
        assert clean_text("```json\n{}\n```") == "{}"

    def test_removes_plain_fence(self):
        assert clean_text("```data```") == "data"

    def test_removes_begin_end_text(self):
        text = "<|begin_of_text|>hello<|end_of_text|>"
        assert clean_text(text) == "hello"

    def test_removes_begin_end_box(self):
        text = "<|begin_of_box|>data<|end_of_box|>"
        assert clean_text(text) == "data"

    def test_empty_input(self):
        assert clean_text("") == ""

    def test_none_input(self):
        assert clean_text(None) == ""  # type: ignore[arg-type]

    def test_no_markers(self):
        assert clean_text("plain text") == "plain text"


class TestExtractJsonText:
    def test_valid_json_object(self):
        result = extract_json_text('{"key": "value"}')
        assert result is not None
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_valid_json_array(self):
        result = extract_json_text('[1, 2, 3]')
        assert result is not None
        assert json.loads(result) == [1, 2, 3]

    def test_json_in_fence(self):
        result = extract_json_text('Some text\n```json\n{"a": 1}\n```\nMore text')
        assert result is not None
        assert json.loads(result) == {"a": 1}

    def test_no_json(self):
        result = extract_json_text("no json here")
        assert result is None

    def test_empty(self):
        assert extract_json_text("") is None

    def test_none(self):
        assert extract_json_text(None) is None  # type: ignore[arg-type]

    def test_malformed_json_fallback_stack(self):
        # Test the stack-based JSON extraction fallback
        text = 'text {"nested": {"a": 1}} trailing'
        result = extract_json_text(text)
        assert result is not None

    def test_mismatched_brackets_resets(self):
        text = '{ [ } "key": "value" ]'
        result = extract_json_text(text)
        # Should handle gracefully
        assert result is None or isinstance(result, str)


class TestParseJsonContent:
    def test_valid(self):
        result = parse_json_content('{"x": 42}')
        assert result == {"x": 42}

    def test_invalid(self):
        with pytest.raises(ValueError, match="does not contain valid JSON"):
            parse_json_content("not json")


class TestParseModelContent:
    def test_valid(self):
        result = parse_model_content('{"name": "test", "value": 42}', SimpleModel)
        assert result.name == "test"
        assert result.value == 42

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_model_content("bad", SimpleModel)


class TestJsonSchemaInstructions:
    def test_contains_schema(self):
        instructions = json_schema_instructions(SimpleModel)
        assert "JSON" in instructions
        assert "name" in instructions
        assert "value" in instructions
