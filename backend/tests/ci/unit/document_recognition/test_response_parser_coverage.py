"""Coverage tests for document_recognition/services/_response_parser_mixin.py.

Covers:
  - _extract_json_from_response (all paths: direct JSON, brace extraction, ```json, ```)
  - _parse_datetime (all format paths + regex fallbacks)
  - _parse_summons_response
  - _parse_execution_response
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest

from apps.document_recognition.services._response_parser_mixin import ResponseParserMixin


class _ConcreteParser(ResponseParserMixin):
    """Concrete implementation for testing."""

    def _normalize_case_number(self, case_number: str) -> str:
        return case_number.strip()


class TestExtractJsonFromResponse:
    def setup_method(self):
        self.parser = _ConcreteParser()

    def test_direct_json(self):
        data = {"key": "value"}
        result = self.parser._extract_json_from_response(json.dumps(data))
        assert result == data

    def test_json_embedded_in_text(self):
        text = 'Here is the result: {"key": "value"} and more text'
        result = self.parser._extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_json_in_code_block(self):
        text = '```json\n{"key": "value"}\n```'
        result = self.parser._extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_json_in_plain_code_block(self):
        text = '```\n{"key": "value"}\n```'
        result = self.parser._extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_no_json_found(self):
        result = self.parser._extract_json_from_response("no json here")
        assert result is None

    def test_malformed_json(self):
        result = self.parser._extract_json_from_response("{broken")
        assert result is None

    def test_nested_json(self):
        data = {"outer": {"inner": 42}}
        result = self.parser._extract_json_from_response(json.dumps(data))
        assert result == data


class TestParseDatetime:
    def setup_method(self):
        self.parser = _ConcreteParser()

    def test_format_yyyy_mm_dd_hh_mm(self):
        result = self.parser._parse_datetime("2024-01-15 10:30")
        assert result == datetime(2024, 1, 15, 10, 30)

    def test_format_yyyy_mm_dd_hh_mm_ss(self):
        result = self.parser._parse_datetime("2024-01-15 10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30)

    def test_format_cn_yyyy_nian_mm_yue_dd_ri_hh_mm(self):
        result = self.parser._parse_datetime("2024年1月15日 10:30")
        assert result == datetime(2024, 1, 15, 10, 30)

    def test_format_cn_hh_shi_mm_fen(self):
        result = self.parser._parse_datetime("2024年1月15日 10时30分")
        assert result == datetime(2024, 1, 15, 10, 30)

    def test_format_cn_compact(self):
        result = self.parser._parse_datetime("2024年1月15日10时30分")
        assert result == datetime(2024, 1, 15, 10, 30)

    def test_format_slash(self):
        result = self.parser._parse_datetime("2024/01/15 10:30")
        assert result == datetime(2024, 1, 15, 10, 30)

    def test_format_dot(self):
        result = self.parser._parse_datetime("2024.01.15 10:30")
        assert result == datetime(2024, 1, 15, 10, 30)

    def test_empty_string(self):
        assert self.parser._parse_datetime("") is None

    def test_invalid_format(self):
        assert self.parser._parse_datetime("not a date") is None

    def test_regex_fallback_cn(self):
        result = self.parser._parse_datetime("开庭时间：2024年3月5日9时30分")
        assert result == datetime(2024, 3, 5, 9, 30)

    def test_regex_fallback_std(self):
        result = self.parser._parse_datetime("时间: 2024-03-05 09:30")
        assert result == datetime(2024, 3, 5, 9, 30)

    def test_invalid_regex_match(self):
        # Regex matches but values are invalid
        result = self.parser._parse_datetime("2024-13-32 25:61")
        assert result is None


class TestParseSummonsResponse:
    def setup_method(self):
        self.parser = _ConcreteParser()

    def test_valid_response(self):
        response = {
            "message": {
                "content": json.dumps({"case_number": "(2024)粤01民初1号", "court_time": "2024-06-15 09:00"})
            }
        }
        result = self.parser._parse_summons_response(response)
        assert result["case_number"] == "(2024)粤01民初1号"
        assert result["court_time"] is not None

    def test_null_case_number(self):
        response = {"message": {"content": json.dumps({"case_number": "null", "court_time": "null"})}}
        result = self.parser._parse_summons_response(response)
        assert result["case_number"] is None
        assert result["court_time"] is None

    def test_missing_message(self):
        result = self.parser._parse_summons_response({})
        assert result["case_number"] is None

    def test_missing_content(self):
        result = self.parser._parse_summons_response({"message": {}})
        assert result["case_number"] is None

    def test_no_json_in_content(self):
        result = self.parser._parse_summons_response({"message": {"content": "no json"}})
        assert result["case_number"] is None


class TestParseExecutionResponse:
    def setup_method(self):
        self.parser = _ConcreteParser()

    def test_valid_response(self):
        response = {
            "message": {
                "content": json.dumps({"case_number": "(2024)执123号", "preservation_deadline": "2024-12-31"})
            }
        }
        result = self.parser._parse_execution_response(response)
        assert result["case_number"] == "(2024)执123号"

    def test_null_values(self):
        response = {"message": {"content": json.dumps({"case_number": "null", "preservation_deadline": "null"})}}
        result = self.parser._parse_execution_response(response)
        assert result["case_number"] is None
        assert result["preservation_deadline"] is None

    def test_missing_message(self):
        result = self.parser._parse_execution_response({})
        assert result["case_number"] is None

    def test_no_json(self):
        result = self.parser._parse_execution_response({"message": {"content": "plain text"}})
        assert result["case_number"] is None
