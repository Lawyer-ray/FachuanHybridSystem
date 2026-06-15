"""Tests for _response_parser_mixin, judgment_pdf_extractor, invoice_recognition_service, and other core services."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.document_recognition.services._response_parser_mixin import ResponseParserMixin
from apps.core.api.schemas import TimestampMixin, DisplayLabelMixin, FileFieldMixin, SchemaMixin
from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry


# ---------------------------------------------------------------------------
# ResponseParserMixin
# ---------------------------------------------------------------------------


class ConcreteParser(ResponseParserMixin):
    def _normalize_case_number(self, case_number: str) -> str:
        return case_number.replace(" ", "")


class TestResponseParserMixin:
    def setup_method(self):
        self.parser = ConcreteParser()

    def test_parse_summons_response_valid(self):
        response = {"message": {"content": json.dumps({"case_number": "(2024)粤0605号", "court_time": "2024-12-01 09:00"})}}
        result = self.parser._parse_summons_response(response)
        assert result["case_number"] == "(2024)粤0605号"
        assert result["court_time"] == datetime(2024, 12, 1, 9, 0)

    def test_parse_summons_response_null_case_number(self):
        response = {"message": {"content": json.dumps({"case_number": "null", "court_time": "2024-12-01 09:00"})}}
        result = self.parser._parse_summons_response(response)
        assert result["case_number"] is None

    def test_parse_summons_response_missing_message(self):
        result = self.parser._parse_summons_response({})
        assert result["case_number"] is None
        assert result["court_time"] is None

    def test_parse_summons_response_no_json(self):
        response = {"message": {"content": "no json here"}}
        result = self.parser._parse_summons_response(response)
        assert result["case_number"] is None

    def test_parse_execution_response_valid(self):
        response = {"message": {"content": json.dumps({"case_number": "(2024)粤0605号", "preservation_deadline": "2024-12-31"})}}
        result = self.parser._parse_execution_response(response)
        assert result["case_number"] == "(2024)粤0605号"
        assert result["preservation_deadline"] == datetime(2024, 12, 31)

    def test_parse_execution_response_null_deadline(self):
        response = {"message": {"content": json.dumps({"case_number": "X", "preservation_deadline": "null"})}}
        result = self.parser._parse_execution_response(response)
        assert result["preservation_deadline"] is None

    def test_parse_execution_response_missing_message(self):
        result = self.parser._parse_execution_response({})
        assert result["case_number"] is None

    def test_extract_json_from_response_pure_json(self):
        result = self.parser._extract_json_from_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_json_from_response_embedded_json(self):
        result = self.parser._extract_json_from_response('Some text {"key": "value"} more text')
        assert result == {"key": "value"}

    def test_extract_json_from_response_markdown_json_block(self):
        content = 'Here is some text\n```json\n{"key": "value"}\n```\nAnd more text'
        result = self.parser._extract_json_from_response(content)
        assert result == {"key": "value"}

    def test_extract_json_from_response_plain_code_block(self):
        content = 'Here is some text\n```\n{"key": "value"}\n```\nAnd more text'
        result = self.parser._extract_json_from_response(content)
        assert result == {"key": "value"}

    def test_extract_json_from_response_no_json(self):
        result = self.parser._extract_json_from_response("no json at all")
        assert result is None

    def test_extract_json_from_response_malformed_json(self):
        content = '```json\n{broken\n```'
        result = self.parser._extract_json_from_response(content)
        assert result is None

    def test_parse_datetime_formats(self):
        assert self.parser._parse_datetime("2024-12-01 09:00") == datetime(2024, 12, 1, 9, 0)
        assert self.parser._parse_datetime("2024-12-01 09:00:00") == datetime(2024, 12, 1, 9, 0)
        assert self.parser._parse_datetime("2024年12月01日 09:00") == datetime(2024, 12, 1, 9, 0)
        assert self.parser._parse_datetime("2024年12月01日 09时00分") == datetime(2024, 12, 1, 9, 0)
        assert self.parser._parse_datetime("2024年12月01日09时00分") == datetime(2024, 12, 1, 9, 0)
        assert self.parser._parse_datetime("2024/12/01 09:00") == datetime(2024, 12, 1, 9, 0)
        assert self.parser._parse_datetime("2024.12.01 09:00") == datetime(2024, 12, 1, 9, 0)

    def test_parse_datetime_empty(self):
        assert self.parser._parse_datetime("") is None
        assert self.parser._parse_datetime(None) is None  # type: ignore[arg-type]

    def test_parse_datetime_chinese_regex_fallback(self):
        result = self.parser._parse_datetime("2025年6月5日 14时30分")
        assert result == datetime(2025, 6, 5, 14, 30)

    def test_parse_datetime_std_regex_fallback(self):
        result = self.parser._parse_datetime("2025-06-05 14:30")
        assert result == datetime(2025, 6, 5, 14, 30)

    def test_parse_date_formats(self):
        assert self.parser._parse_date("2024-12-01") == datetime(2024, 12, 1)
        assert self.parser._parse_date("2024年12月01日") == datetime(2024, 12, 1)
        assert self.parser._parse_date("2024/12/01") == datetime(2024, 12, 1)
        assert self.parser._parse_date("2024.12.01") == datetime(2024, 12, 1)

    def test_parse_date_empty(self):
        assert self.parser._parse_date("") is None
        assert self.parser._parse_date(None) is None  # type: ignore[arg-type]

    def test_parse_date_regex_fallback(self):
        result = self.parser._parse_date("2025-06-05")
        assert result == datetime(2025, 6, 5)

    def test_parse_date_regex_chinese_separator(self):
        result = self.parser._parse_date("2025年06月05日")
        assert result == datetime(2025, 6, 5)


# ---------------------------------------------------------------------------
# SchemaMixin (TimestampMixin, DisplayLabelMixin, FileFieldMixin)
# ---------------------------------------------------------------------------


class TestTimestampMixin:
    def test_resolve_datetime_none(self):
        assert TimestampMixin._resolve_datetime(None) is None

    def test_resolve_datetime_valid(self):
        result = TimestampMixin._resolve_datetime(datetime(2024, 1, 1))
        assert result is not None

    def test_resolve_datetime_type_error(self):
        result = TimestampMixin._resolve_datetime("not a datetime")
        assert result == "not a datetime"

    def test_resolve_datetime_iso_none(self):
        assert TimestampMixin._resolve_datetime_iso(None) is None

    def test_resolve_datetime_iso_valid(self):
        result = TimestampMixin._resolve_datetime_iso(datetime(2024, 6, 15, 12, 0))
        assert result is not None
        assert "2024" in result

    def test_resolve_datetime_iso_non_datetime_with_isoformat(self):
        class FakeDT:
            def isoformat(self):
                return "2024-01-01T00:00:00"

        result = TimestampMixin._resolve_datetime_iso(FakeDT())
        assert result == "2024-01-01T00:00:00"


class TestDisplayLabelMixin:
    def test_get_display_with_getter(self):
        class FakeObj:
            def get_status_display(self):
                return "Active"

        result = DisplayLabelMixin._get_display(FakeObj(), "status")
        assert result == "Active"

    def test_get_display_without_getter(self):
        class FakeObj:
            status = "active"

        result = DisplayLabelMixin._get_display(FakeObj(), "status")
        assert result == "active"

    def test_get_display_attribute_error(self):
        class FakeObj:
            pass

        result = DisplayLabelMixin._get_display(FakeObj(), "nonexistent")
        assert result is None


class TestFileFieldMixin:
    def test_get_file_url_none(self):
        assert FileFieldMixin._get_file_url(None) is None

    def test_get_file_url_valid(self):
        field = MagicMock()
        field.url = "/media/test.pdf"
        assert FileFieldMixin._get_file_url(field) == "/media/test.pdf"

    def test_get_file_url_value_error(self):
        class BadField:
            @property
            def url(self):
                raise ValueError("no url")

        assert FileFieldMixin._get_file_url(BadField()) is None

    def test_get_file_path_none(self):
        assert FileFieldMixin._get_file_path(None) is None

    def test_get_file_path_valid(self):
        field = MagicMock()
        field.path = "/tmp/test.pdf"
        assert FileFieldMixin._get_file_path(field) == "/tmp/test.pdf"

    def test_get_file_path_value_error(self):
        class BadField:
            @property
            def path(self):
                raise ValueError("no path")

        assert FileFieldMixin._get_file_path(BadField()) is None


# ---------------------------------------------------------------------------
# EnterpriseProviderRegistry
# ---------------------------------------------------------------------------


class TestEnterpriseProviderRegistry:
    def test_get_cache_ttl(self):
        registry = EnterpriseProviderRegistry(config_service=MagicMock())
        assert registry.get_cache_ttl_seconds() > 0

    def test_get_default_provider_name(self):
        registry = EnterpriseProviderRegistry(config_service=MagicMock())
        assert isinstance(registry.get_default_provider_name(), str)

    def test_get_rate_limit(self):
        registry = EnterpriseProviderRegistry(config_service=MagicMock())
        assert registry.get_rate_limit_requests() == 60
        assert registry.get_rate_limit_window_seconds() == 60

    def test_get_retry_config(self):
        registry = EnterpriseProviderRegistry(config_service=MagicMock())
        assert registry.get_retry_max_attempts() == 2
        assert registry.get_retry_backoff_seconds() == 0.25

    def test_get_metrics_config(self):
        registry = EnterpriseProviderRegistry(config_service=MagicMock())
        assert registry.get_metrics_window_seconds() == 300
        assert registry.get_alert_min_samples() == 20

    def test_get_alert_thresholds(self):
        registry = EnterpriseProviderRegistry(config_service=MagicMock())
        assert registry.get_alert_success_rate_threshold() == 0.9
        assert registry.get_alert_fallback_rate_threshold() == 0.35
        assert registry.get_alert_avg_latency_ms_threshold() == 3000

    def test_split_secret_values_empty(self):
        assert EnterpriseProviderRegistry._split_secret_values("") == ()
        assert EnterpriseProviderRegistry._split_secret_values(None) == ()  # type: ignore[arg-type]

    def test_split_secret_values_single(self):
        result = EnterpriseProviderRegistry._split_secret_values("key123")
        assert result == ("key123",)

    def test_split_secret_values_multi(self):
        result = EnterpriseProviderRegistry._split_secret_values("key1,key2\nkey3")
        assert result == ("key1", "key2", "key3")

    def test_split_secret_values_dedup(self):
        result = EnterpriseProviderRegistry._split_secret_values("key1,key1,key2")
        assert result == ("key1", "key2")

    def test_read_sensitive_str_error(self):
        mock_config = MagicMock()
        mock_config.get_value.side_effect = Exception("db error")
        registry = EnterpriseProviderRegistry(config_service=mock_config)
        result = registry._read_sensitive_str("SOME_KEY")
        assert result == ""

    def test_read_sensitive_values_from_config(self):
        mock_config = MagicMock()
        mock_config.get_value.return_value = "stored_key"
        registry = EnterpriseProviderRegistry(config_service=mock_config)
        result = registry._read_sensitive_values("API_KEY", env_keys=("API_KEY",))
        assert result == ("stored_key",)

    def test_read_sensitive_values_from_env(self, monkeypatch):
        mock_config = MagicMock()
        mock_config.get_value.return_value = ""
        registry = EnterpriseProviderRegistry(config_service=mock_config)
        monkeypatch.setenv("API_KEY", "env_key")
        result = registry._read_sensitive_values("API_KEY", env_keys=("API_KEY",))
        assert result == ("env_key",)

    def test_get_tianyancha_transport_valid(self):
        mock_config = MagicMock()
        mock_config.get_value.return_value = "sse"
        registry = EnterpriseProviderRegistry(config_service=mock_config)
        assert registry.get_tianyancha_transport() == "sse"

    def test_get_tianyancha_transport_invalid(self):
        mock_config = MagicMock()
        mock_config.get_value.return_value = "invalid_transport"
        registry = EnterpriseProviderRegistry(config_service=mock_config)
        result = registry.get_tianyancha_transport()
        assert isinstance(result, str)

    def test_get_provider_unknown_raises(self):
        mock_config = MagicMock()
        mock_config.get_value.return_value = ""
        registry = EnterpriseProviderRegistry(config_service=mock_config)
        with pytest.raises(Exception):
            registry.get_provider("unknown_provider")
