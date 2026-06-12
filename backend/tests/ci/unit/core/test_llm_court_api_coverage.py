"""Comprehensive tests for LLM config and court API client data processing functions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.llm.config import LLMConfig
from apps.core.services.court_api_client import (
    CourtApiClient,
    CauseItem,
    CourtItem,
)


# ===========================================================================
# LLMConfig tests
# ===========================================================================
class TestLLMConfigNormalizeApiKey:
    def test_plain_key(self):
        assert LLMConfig._normalize_api_key("sk-abc123") == "sk-abc123"

    def test_bearer_prefix(self):
        assert LLMConfig._normalize_api_key("Bearer sk-abc123") == "sk-abc123"

    def test_bearer_lowercase(self):
        assert LLMConfig._normalize_api_key("bearer sk-abc123") == "sk-abc123"

    def test_empty(self):
        assert LLMConfig._normalize_api_key("") == ""

    def test_none(self):
        assert LLMConfig._normalize_api_key(None) == ""  # type: ignore[arg-type]

    def test_whitespace(self):
        assert LLMConfig._normalize_api_key("  sk-abc123  ") == "sk-abc123"


class TestLLMConfigNormalizeBaseUrl:
    def test_plain_url(self):
        assert LLMConfig._normalize_base_url("https://api.example.com/v1") == "https://api.example.com/v1"

    def test_trailing_slash(self):
        assert LLMConfig._normalize_base_url("https://api.example.com/v1/") == "https://api.example.com/v1"

    def test_multiple_trailing_slashes(self):
        assert LLMConfig._normalize_base_url("https://api.example.com/v1///") == "https://api.example.com/v1"

    def test_empty_returns_default(self):
        assert LLMConfig._normalize_base_url("") == LLMConfig.DEFAULT_BASE_URL

    def test_none(self):
        assert LLMConfig._normalize_base_url(None) == LLMConfig.DEFAULT_BASE_URL  # type: ignore[arg-type]


class TestLLMConfigResolveBackendForModel:
    def test_openai_compatible_model(self):
        assert LLMConfig.resolve_backend_for_model("Qwen/Qwen2.5-7B-Instruct") == "openai_compatible"

    def test_ollama_model(self):
        assert LLMConfig.resolve_backend_for_model("qwen3:0.6b") == "ollama"

    @patch.object(LLMConfig, "get_default_backend", return_value="openai_compatible")
    def test_empty_model(self, mock_backend):
        result = LLMConfig.resolve_backend_for_model("")
        assert result == "openai_compatible"


class TestLLMConfigParseBool:
    def test_true_values(self):
        for v in ("1", "true", "True", "yes", "Yes", "y", "on", "ON"):
            assert LLMConfig._parse_bool(v, False) is True, f"Failed for {v}"

    def test_false_values(self):
        for v in ("0", "false", "False", "no", "No", "n", "off", "OFF"):
            assert LLMConfig._parse_bool(v, True) is False, f"Failed for {v}"

    def test_empty_returns_default(self):
        assert LLMConfig._parse_bool("", True) is True
        assert LLMConfig._parse_bool("", False) is False

    def test_none_returns_default(self):
        assert LLMConfig._parse_bool(None, True) is True

    def test_bool_passthrough(self):
        assert LLMConfig._parse_bool(True, False) is True
        assert LLMConfig._parse_bool(False, True) is False

    def test_unknown_returns_default(self):
        assert LLMConfig._parse_bool("maybe", True) is True


class TestLLMConfigParseInt:
    def test_valid_int(self):
        assert LLMConfig._parse_int("42", 0) == 42

    def test_none_returns_default(self):
        assert LLMConfig._parse_int(None, 10) == 10

    def test_empty_returns_default(self):
        assert LLMConfig._parse_int("", 10) == 10

    def test_invalid_returns_default(self):
        assert LLMConfig._parse_int("abc", 10) == 10


class TestLLMConfigGetDefaultBackend:
    @patch.object(LLMConfig, "_get_system_config", return_value="")
    @patch.object(LLMConfig, "_get_config_service")
    def test_default(self, mock_cs, mock_sc):
        mock_cs.return_value = None
        result = LLMConfig.get_default_backend()
        assert result in ("ollama", "openai_compatible")

    @patch.object(LLMConfig, "_get_system_config", return_value="ollama")
    def test_from_config(self, mock_sc):
        result = LLMConfig.get_default_backend()
        assert result == "ollama"

    @patch.object(LLMConfig, "_get_system_config", return_value="invalid")
    def test_invalid_returns_openai_compatible(self, mock_sc):
        result = LLMConfig.get_default_backend()
        assert result == "openai_compatible"


class TestLLMConfigMisc:
    @patch.object(LLMConfig, "_get_system_config", return_value="bad_int")
    def test_get_timeout_invalid(self, mock_sc):
        assert LLMConfig.get_timeout() == LLMConfig.DEFAULT_TIMEOUT

    @patch.object(LLMConfig, "_get_system_config", return_value="300")
    def test_get_timeout_valid(self, mock_sc):
        assert LLMConfig.get_timeout() == 300

    @patch.object(LLMConfig, "_get_system_config", return_value="bad_float")
    def test_get_temperature_invalid(self, mock_sc):
        assert LLMConfig.get_temperature() == 0.3

    @patch.object(LLMConfig, "_get_system_config", return_value="0.5")
    def test_get_temperature_valid(self, mock_sc):
        assert LLMConfig.get_temperature() == 0.5

    @patch.object(LLMConfig, "_get_system_config", return_value="bad")
    def test_get_max_tokens_invalid(self, mock_sc):
        assert LLMConfig.get_max_tokens() == 2000

    @patch.object(LLMConfig, "_get_system_config", return_value="4000")
    def test_get_max_tokens_valid(self, mock_sc):
        assert LLMConfig.get_max_tokens() == 4000

    @patch.object(LLMConfig, "_get_system_config", return_value="")
    def test_get_default_model_fallback(self, mock_sc):
        assert LLMConfig.get_default_model() == LLMConfig.DEFAULT_MODEL

    @patch.object(LLMConfig, "_get_system_config", return_value="custom-model")
    def test_get_default_model_custom(self, mock_sc):
        assert LLMConfig.get_default_model() == "custom-model"


# ===========================================================================
# CourtApiClient tests
# ===========================================================================
class TestCourtApiClientIsValidResponse:
    def _get_client(self):
        return CourtApiClient.__new__(CourtApiClient)

    def test_valid_int_code(self):
        client = self._get_client()
        assert client._is_valid_response({"code": 200}) is True

    def test_valid_str_code(self):
        client = self._get_client()
        assert client._is_valid_response({"code": "200"}) is True

    def test_invalid_code(self):
        client = self._get_client()
        assert client._is_valid_response({"code": 400}) is False

    def test_not_dict(self):
        client = self._get_client()
        assert client._is_valid_response("not a dict") is False  # type: ignore[arg-type]

    def test_no_code(self):
        client = self._get_client()
        assert client._is_valid_response({}) is False


class TestParseCauseResponse:
    def _get_client(self):
        return CourtApiClient.__new__(CourtApiClient)

    def test_civil_causes(self):
        client = self._get_client()
        response = {
            "code": 200,
            "data": {
                "data": {
                    "0300": [
                        {
                            "name": "民事案由",
                            "children": [
                                {"id": "1", "name": "人格权纠纷", "children": [
                                    {"id": "1-1", "name": "生命权纠纷", "children": []},
                                ]},
                                {"id": "2", "name": "婚姻家庭纠纷", "children": []},
                            ],
                        }
                    ]
                }
            },
        }
        result = client.parse_cause_response(response, "0300", "civil")
        assert len(result) == 2
        assert result[0].name == "人格权纠纷"
        assert len(result[0].children) == 1

    def test_empty_response(self):
        client = self._get_client()
        response = {"code": 200, "data": {"data": {"0300": []}}}
        result = client.parse_cause_response(response, "0300", "civil")
        assert result == []

    def test_missing_lbs_key(self):
        client = self._get_client()
        response = {"code": 200, "data": {"data": {}}}
        result = client.parse_cause_response(response, "0300", "civil")
        assert result == []

    def test_administrative_excludes(self):
        client = self._get_client()
        response = {
            "code": 200,
            "data": {
                "data": {
                    "0400": [
                        {
                            "name": "行政行为",
                            "children": [
                                {"id": "1", "name": "行政管理类型", "children": []},
                                {"id": "2", "name": "行政许可", "children": []},
                            ],
                        }
                    ]
                }
            },
        }
        result = client.parse_cause_response(response, "0400", "administrative")
        assert len(result) == 1
        assert result[0].name == "行政许可"


class TestParseCauseItems:
    def _get_client(self):
        return CourtApiClient.__new__(CourtApiClient)

    def test_simple_items(self):
        client = self._get_client()
        items = [
            {"id": "1", "name": "Test1", "children": []},
            {"id": "2", "name": "Test2"},
        ]
        result = client._parse_cause_items(items, "civil")
        assert len(result) == 2
        assert result[0].code == "1"
        assert result[0].case_type == "civil"

    def test_skip_empty(self):
        client = self._get_client()
        items = [{"id": "", "name": "Test"}, {"id": "1", "name": ""}]
        result = client._parse_cause_items(items, "civil")
        assert len(result) == 0

    def test_nested(self):
        client = self._get_client()
        items = [
            {"id": "1", "name": "Parent", "children": [
                {"id": "1-1", "name": "Child", "children": []},
            ]},
        ]
        result = client._parse_cause_items(items, "civil")
        assert len(result[0].children) == 1


class TestParseCourtResponse:
    def _get_client(self):
        return CourtApiClient.__new__(CourtApiClient)

    def test_simple_courts(self):
        client = self._get_client()
        response = {
            "data": [
                {"cGbm": "G1000", "name": "广东省", "children": [
                    {"cGbm": "G1001", "name": "广州市中级人民法院"},
                ]},
            ]
        }
        result = client.parse_court_response(response)
        assert len(result) == 1
        assert result[0].name == "广东省"
        assert result[0].province == "广东省"

    def test_empty_response(self):
        client = self._get_client()
        response = {"data": []}
        result = client.parse_court_response(response)
        assert result == []

    def test_missing_data(self):
        client = self._get_client()
        result = client.parse_court_response({})
        assert result == []


class TestParseCourtItems:
    def _get_client(self):
        return CourtApiClient.__new__(CourtApiClient)

    def test_level1_province(self):
        client = self._get_client()
        items = [{"cGbm": "G1000", "name": "广东省"}]
        result = client._parse_court_items(items, level=1)
        assert result[0].province == "广东省"

    def test_skip_empty(self):
        client = self._get_client()
        items = [{"cGbm": "", "name": ""}]
        result = client._parse_court_items(items)
        assert len(result) == 0

    def test_uses_id_fallback(self):
        client = self._get_client()
        items = [{"id": "C001", "name": "Test Court"}]
        result = client._parse_court_items(items)
        assert result[0].code == "C001"


# ===========================================================================
# CauseItem / CourtItem dataclass tests
# ===========================================================================
class TestDataclasses:
    def test_cause_item_defaults(self):
        item = CauseItem(code="1", name="Test", case_type="civil")
        assert item.level == 1
        assert item.parent_code is None
        assert item.children == []

    def test_court_item_defaults(self):
        item = CourtItem(code="G1", name="Test Court")
        assert item.level == 1
        assert item.province == ""
        assert item.children == []
