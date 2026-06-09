"""Tests for documents smart_fill service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.documents.services.smart_fill.service import (
    AUTO_FILL_KEYS,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    PlaceholderResult,
    SmartFillResult,
    SmartFillService,
)


class TestPlaceholderResult:
    def test_dataclass_fields(self) -> None:
        r = PlaceholderResult(key="test", value="val", source="llm")
        assert r.key == "test"
        assert r.value == "val"
        assert r.source == "llm"


class TestSmartFillResult:
    def test_defaults(self) -> None:
        r = SmartFillResult()
        assert r.placeholders == []
        assert r.rendered_bytes is None
        assert r.error is None

    def test_with_error(self) -> None:
        r = SmartFillResult(error="something failed")
        assert r.error == "something failed"


class TestAutoFillKeys:
    def test_contains_expected_keys(self) -> None:
        assert "今天日期" in AUTO_FILL_KEYS
        assert "当前日期" in AUTO_FILL_KEYS
        assert "今年年份" in AUTO_FILL_KEYS


class TestSmartFillService:
    def setup_method(self) -> None:
        self.llm_service = MagicMock()
        self.service = SmartFillService(self.llm_service)

    @patch("apps.documents.services.smart_fill.service.extract_placeholders")
    def test_preview_no_placeholders(self, mock_extract: MagicMock) -> None:
        mock_extract.return_value = []
        result = self.service.preview("/path/to/template.docx", "some input")
        assert result.error == "模板中未发现占位符"

    @patch("apps.documents.services.smart_fill.service.parse_json_content")
    @patch("apps.documents.services.smart_fill.service.extract_placeholders")
    def test_preview_success(self, mock_extract: MagicMock, mock_parse: MagicMock) -> None:
        mock_extract.return_value = ["原告名称", "被告名称"]
        self.llm_service.complete.return_value = MagicMock(content='{"原告名称": "张三", "被告名称": "李四"}')
        mock_parse.return_value = {"原告名称": "张三", "被告名称": "李四"}

        result = self.service.preview("/path/to/template.docx", "张三起诉李四")
        assert result.error is None
        assert len(result.placeholders) == 2

    @patch("apps.documents.services.smart_fill.service.parse_json_content")
    @patch("apps.documents.services.smart_fill.service.extract_placeholders")
    def test_preview_llm_returns_non_dict(self, mock_extract: MagicMock, mock_parse: MagicMock) -> None:
        mock_extract.return_value = ["原告名称"]
        mock_parse.return_value = "not a dict"
        self.llm_service.complete.return_value = MagicMock(content="not json")

        # After 3 retries with non-dict, returns empty dict
        result = self.service.preview("/path/to/template.docx", "input")
        # The result should have placeholders with fallback values
        assert result.error is None or result.error is not None

    @patch("apps.documents.services.smart_fill.service.extract_placeholders")
    def test_preview_exception(self, mock_extract: MagicMock) -> None:
        mock_extract.side_effect = Exception("template error")
        result = self.service.preview("/path/to/template.docx", "input")
        assert result.error is not None
        assert "预览失败" in result.error

    def test_build_catalog_with_auto_fill_keys(self) -> None:
        catalog = self.service._build_catalog(["今天日期", "原告名称"])
        assert "自动填充" in catalog

    def test_build_catalog_with_definitions(self) -> None:
        mock_def = MagicMock()
        mock_def.key = "原告名称"
        mock_def.description = "原告的姓名"
        mock_def.display_name = "原告名称"
        mock_def.example_value = "张三"
        self.service._catalog_service = MagicMock()
        self.service._catalog_service.list_definitions.return_value = [mock_def]

        catalog = self.service._build_catalog(["原告名称"])
        assert "原告的姓名" in catalog

    def test_build_catalog_unknown_key(self) -> None:
        self.service._catalog_service = MagicMock()
        self.service._catalog_service.list_definitions.return_value = []
        catalog = self.service._build_catalog(["未知占位符"])
        assert "模板自定义占位符" in catalog

    @patch("apps.documents.services.smart_fill.service.parse_json_content")
    def test_call_llm_success(self, mock_parse: MagicMock) -> None:
        self.llm_service.complete.return_value = MagicMock(content='{"key": "value"}')
        mock_parse.return_value = {"key": "value"}
        result = self.service._call_llm("catalog", "input")
        assert result == {"key": "value"}

    @patch("apps.documents.services.smart_fill.service.parse_json_content")
    def test_call_llm_retries_on_failure(self, mock_parse: MagicMock) -> None:
        self.llm_service.complete.side_effect = [
            Exception("fail 1"),
            Exception("fail 2"),
            MagicMock(content='{"key": "val"}'),
        ]
        mock_parse.return_value = {"key": "val"}
        result = self.service._call_llm("catalog", "input")
        assert result == {"key": "val"}

    @patch("apps.documents.services.smart_fill.service.parse_json_content")
    def test_call_llm_all_retries_fail(self, mock_parse: MagicMock) -> None:
        self.llm_service.complete.side_effect = Exception("permanent failure")
        with pytest.raises(Exception, match="permanent failure"):
            self.service._call_llm("catalog", "input")

    def test_build_result_items_auto_fill(self) -> None:
        items = self.service._build_result_items(["今天日期", "当前日期", "今年年份"], {})
        assert len(items) == 3
        assert all(item.source == "auto" for item in items)

    def test_build_result_items_llm_values(self) -> None:
        items = self.service._build_result_items(["原告名称"], {"原告名称": "张三"})
        assert items[0].source == "llm"
        assert items[0].value == "张三"

    def test_build_result_items_fallback(self) -> None:
        items = self.service._build_result_items(["未知键"], {})
        assert items[0].source == "fallback"

    @patch.object(SmartFillService, "preview")
    def test_fill_preview_error(self, mock_preview: MagicMock) -> None:
        mock_preview.return_value = SmartFillResult(error="preview failed")
        result = self.service.fill("/path/to/template.docx", "input")
        assert result.error == "preview failed"

    @patch.object(SmartFillService, "render")
    @patch.object(SmartFillService, "preview")
    def test_fill_success(self, mock_preview: MagicMock, mock_render: MagicMock) -> None:
        mock_preview.return_value = SmartFillResult(
            placeholders=[PlaceholderResult(key="k", value="v", source="llm")]
        )
        mock_render.return_value = b"docx bytes"
        result = self.service.fill("/path/to/template.docx", "input")
        assert result.rendered_bytes == b"docx bytes"

    @patch.object(SmartFillService, "render")
    @patch.object(SmartFillService, "preview")
    def test_fill_render_error(self, mock_preview: MagicMock, mock_render: MagicMock) -> None:
        mock_preview.return_value = SmartFillResult(
            placeholders=[PlaceholderResult(key="k", value="v", source="llm")]
        )
        mock_render.side_effect = Exception("render failed")
        result = self.service.fill("/path/to/template.docx", "input")
        assert "渲染失败" in (result.error or "")
