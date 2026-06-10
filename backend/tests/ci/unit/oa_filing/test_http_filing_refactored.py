"""Tests for http_filing module-level pure functions."""

from __future__ import annotations

import json

import pytest

from apps.oa_filing.services.oa_scripts.jtn.filing.http_filing import (
    handler_url,
    normalize_text,
    parse_json_object,
    project_field_name,
)


class TestProjectFieldName:
    def test_basic(self) -> None:
        result = project_field_name("manager_id")
        assert result == "ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$project_manager_id"

    def test_contains_project_prefix(self) -> None:
        result = project_field_name("name")
        assert "project_name" in result

    def test_prefix_structure(self) -> None:
        result = project_field_name("test")
        assert result.startswith("ctl00$ctl00$")


class TestHandlerUrl:
    def test_basic(self) -> None:
        result = handler_url("CustSeachGetList")
        assert result.endswith("/CustSeachGetList")

    def test_contains_handler_base(self) -> None:
        result = handler_url("TestMethod")
        assert "handler" in result.lower() or "Handler" in result


class TestParseJsonObject:
    def test_valid_json(self) -> None:
        result = parse_json_object('{"key": "value"}')
        assert result == {"key": "value"}

    def test_with_bom(self) -> None:
        result = parse_json_object('﻿{"key": "value"}')
        assert result == {"key": "value"}

    def test_not_dict_raises(self) -> None:
        with pytest.raises(RuntimeError, match="格式异常"):
            parse_json_object('[1, 2, 3]')

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            parse_json_object("not json")

    def test_empty_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            parse_json_object("")


class TestNormalizeText:
    def test_basic(self) -> None:
        result = normalize_text("  hello world  ")
        assert result == "hello world"

    def test_cr_to_lf(self) -> None:
        result = normalize_text("line1\rline2")
        assert "\r" not in result
        assert "\n" in result

    def test_nbsp(self) -> None:
        result = normalize_text("hello\xa0world")
        assert "\xa0" not in result

    def test_fullwidth_space(self) -> None:
        result = normalize_text("hello　world")
        assert "　" not in result

    def test_collapse_spaces(self) -> None:
        result = normalize_text("a  \t  b")
        assert "  " not in result

    def test_none_input(self) -> None:
        result = normalize_text(None)
        assert result == ""
