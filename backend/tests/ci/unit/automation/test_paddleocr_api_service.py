"""Tests for paddleocr_api_service uncovered branches."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestLooksLikeJsonNoise:
    """Cover _looks_like_json_noise branches."""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        return PaddleOCRApiEngine(model="pp_ocrv5")

    def test_short_text_not_noise(self):
        assert self._engine()._looks_like_json_noise("hello") is False

    def test_json_object_is_noise(self):
        assert self._engine()._looks_like_json_noise('{"key": "value"}') is True

    def test_json_array_is_noise(self):
        assert self._engine()._looks_like_json_noise('[{"a": 1}]') is True

    def test_text_with_json_key_pattern_is_noise(self):
        text = 'some text with "key_name": value embedded'
        assert self._engine()._looks_like_json_noise(text) is True

    def test_high_json_char_ratio_is_noise(self):
        # 30+ chars, >30% are json chars
        text = '{"a":"b","c":"d","e":"f","g":"h"}'
        assert self._engine()._looks_like_json_noise(text) is True

    def test_normal_text_not_noise(self):
        assert self._engine()._looks_like_json_noise("这是一个普通的文本内容，没有JSON特征") is False


class TestEngineProperties:
    """Cover model, api_url, api_token, _is_configured properties."""

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_model_from_config(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = "paddleocr_vl"
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine.model == "paddleocr_vl"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_model_default_pp_ocrv5(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = None
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine.model == "pp_ocrv5"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_api_url_ocr_endpoint(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = lambda k, d="": "http://ocr-api.test" if k == "PADDLEOCR_OCR_API_URL" else "pp_ocrv5"
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine.api_url == "http://ocr-api.test"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_api_url_vl_endpoint(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = lambda k, d="": (
            "paddleocr_vl" if k == "PADDLEOCR_API_MODEL"
            else "http://vl-api.test" if k == "PADDLEOCR_VL_API_URL"
            else ""
        )
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine.api_url == "http://vl-api.test"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_api_url_vl15_endpoint(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = lambda k, d="": (
            "paddleocr_vl_1_5" if k == "PADDLEOCR_API_MODEL"
            else "http://vl15.test" if k == "PADDLEOCR_VL15_API_URL"
            else ""
        )
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine.api_url == "http://vl15.test"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_api_token(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = lambda k, d="": "my-token" if k == "PADDLEOCR_API_TOKEN" else ""
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine.api_token == "my-token"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_is_configured_true(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = lambda k, d="": (
            "http://api" if "URL" in k else "token" if "TOKEN" in k else "pp_ocrv5"
        )
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine._is_configured() is True

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_is_configured_false_no_url(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = lambda k, d="": "token" if "TOKEN" in k else ""
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine._is_configured() is False

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_is_configured_false_no_token(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = lambda k, d="": "http://api" if "URL" in k else ""
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine._is_configured() is False


class TestCollectTextFragments:
    """Cover _collect_text_fragments branches."""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        return PaddleOCRApiEngine(model="pp_ocrv5")

    def test_none_returns_empty(self):
        assert self._engine()._collect_text_fragments(None) == []

    def test_string_returns_list(self):
        assert self._engine()._collect_text_fragments("hello") == ["hello"]

    def test_string_whitespace_only_returns_empty(self):
        assert self._engine()._collect_text_fragments("   ") == []

    def test_json_noise_string_filtered(self):
        engine = self._engine()
        assert engine._collect_text_fragments('{"key": "value"}') == []

    def test_list_recurses(self):
        engine = self._engine()
        result = engine._collect_text_fragments(["a", "b", ""])
        assert result == ["a", "b"]

    def test_dict_priority_keys(self):
        engine = self._engine()
        result = engine._collect_text_fragments({"text": "hello", "other": "world"})
        assert "hello" in result
        assert "world" in result

    def test_dict_markdown_priority(self):
        engine = self._engine()
        result = engine._collect_text_fragments({"markdown": "content"})
        assert "content" in result

    def test_numeric_value(self):
        engine = self._engine()
        result = engine._collect_text_fragments(42)
        assert result == ["42"]

    def test_boolean_value(self):
        engine = self._engine()
        result = engine._collect_text_fragments(True)
        assert result == ["True"]


class TestCollectRecTexts:
    """Cover _collect_rec_texts branches."""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        return PaddleOCRApiEngine(model="pp_ocrv5")

    def test_none_returns_empty(self):
        assert self._engine()._collect_rec_texts(None) == []

    def test_string_not_json_returns_empty(self):
        assert self._engine()._collect_rec_texts("just text") == []

    def test_string_json_object_recurses(self):
        engine = self._engine()
        data = json.dumps({"rec_texts": ["hello", "world"]})
        result = engine._collect_rec_texts(data)
        assert result == ["hello", "world"]

    def test_string_json_array_recurses(self):
        engine = self._engine()
        data = json.dumps([{"rec_texts": ["line1"]}])
        result = engine._collect_rec_texts(data)
        assert result == ["line1"]

    def test_string_invalid_json_returns_empty(self):
        assert self._engine()._collect_rec_texts("{not valid json") == []

    def test_list_recurses(self):
        engine = self._engine()
        data = [{"rec_texts": ["a"]}, {"rec_texts": ["b"]}]
        result = engine._collect_rec_texts(data)
        assert result == ["a", "b"]

    def test_dict_with_rec_texts(self):
        engine = self._engine()
        result = engine._collect_rec_texts({"rec_texts": ["x", "y"]})
        assert result == ["x", "y"]

    def test_dict_nested_dedup(self):
        engine = self._engine()
        result = engine._collect_rec_texts({"rec_texts": ["dup"], "nested": {"rec_texts": ["dup", "unique"]}})
        # dedup keeps order
        assert result == ["dup", "unique"]

    def test_dict_with_non_string_in_rec_texts(self):
        engine = self._engine()
        result = engine._collect_rec_texts({"rec_texts": ["ok", 123, None, ""]})
        assert result == ["ok"]


class TestParseJsonlResponse:
    """Cover _parse_jsonl_response branches."""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        return PaddleOCRApiEngine(model="pp_ocrv5")

    def test_rec_texts_extraction(self):
        engine = self._engine()
        jsonl = '{"rec_texts": ["hello", "world"]}\n'
        result = engine._parse_jsonl_response(jsonl, "pp_ocrv5")
        assert result.text == "hello\nworld"
        assert result.raw_texts == ["hello", "world"]
        assert result.model == "pp_ocrv5"

    def test_markdown_fallback_when_rec_texts_not_list(self):
        engine = self._engine()
        # When rec_texts is present but not a list, it falls through to markdown/text/content
        jsonl = '{"rec_texts": "not_a_list", "markdown": "some markdown content"}\n'
        result = engine._parse_jsonl_response(jsonl, "paddleocr_vl")
        assert "some markdown content" in result.text

    def test_text_key_fallback_when_rec_texts_not_list(self):
        engine = self._engine()
        jsonl = '{"rec_texts": null, "text": "plain text"}\n'
        result = engine._parse_jsonl_response(jsonl, "paddleocr_vl")
        assert "plain text" in result.text

    def test_content_key_fallback_when_rec_texts_not_list(self):
        engine = self._engine()
        jsonl = '{"rec_texts": 123, "content": "content value"}\n'
        result = engine._parse_jsonl_response(jsonl, "paddleocr_vl")
        assert "content value" in result.text

    def test_empty_line_skipped(self):
        engine = self._engine()
        jsonl = '{"rec_texts": ["a"]}\n\n{"rec_texts": ["b"]}\n'
        result = engine._parse_jsonl_response(jsonl, "pp_ocrv5")
        assert result.raw_texts == ["a", "b"]

    def test_invalid_json_line_skipped(self):
        engine = self._engine()
        jsonl = '{"rec_texts": ["a"]}\nnot json\n{"rec_texts": ["b"]}\n'
        result = engine._parse_jsonl_response(jsonl, "pp_ocrv5")
        assert result.raw_texts == ["a", "b"]

    def test_non_string_rec_text_filtered(self):
        engine = self._engine()
        jsonl = '{"rec_texts": ["ok", 123, null, ""]}\n'
        result = engine._parse_jsonl_response(jsonl, "pp_ocrv5")
        assert result.raw_texts == ["ok"]

    def test_empty_jsonl(self):
        engine = self._engine()
        result = engine._parse_jsonl_response("", "pp_ocrv5")
        assert result.text == ""
        assert result.raw_texts == []


class TestParseOcrResponse:
    """Cover _parse_ocr_response branches."""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        return PaddleOCRApiEngine(model="pp_ocrv5")

    def test_with_rec_texts(self):
        engine = self._engine()
        result_data = {"ocrResults": [{"prunedResult": {"rec_texts": ["line1", "line2"]}}]}
        result = engine._parse_ocr_response(result_data, "pp_ocrv5")
        assert result.raw_texts == ["line1", "line2"]
        assert "line1" in result.text

    def test_fallback_to_text_fragments(self):
        engine = self._engine()
        result_data = {"ocrResults": [{"prunedResult": "just text content"}]}
        result = engine._parse_ocr_response(result_data, "pp_ocrv5")
        assert "just text content" in result.text

    def test_empty_ocr_results(self):
        engine = self._engine()
        result = engine._parse_ocr_response({"ocrResults": []}, "pp_ocrv5")
        assert result.text == ""
        assert result.raw_texts == []


class TestParseLayoutResponse:
    """Cover _parse_layout_response branches."""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        return PaddleOCRApiEngine(model="paddleocr_vl")

    def test_markdown_extraction(self):
        engine = self._engine()
        result_data = {"layoutParsingResults": [{"markdown": {"text": "layout content"}}]}
        result = engine._parse_layout_response(result_data, "paddleocr_vl")
        assert "layout content" in result.text

    def test_empty_layout(self):
        engine = self._engine()
        result = engine._parse_layout_response({"layoutParsingResults": []}, "paddleocr_vl")
        assert result.text == ""


class TestParseResponse:
    """Cover _parse_response branches."""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        return PaddleOCRApiEngine(model="pp_ocrv5")

    def test_ocr_model(self):
        engine = self._engine()
        data = {"result": {"ocrResults": [{"prunedResult": {"rec_texts": ["t"]}}]}}
        result = engine._parse_response(data, "pp_ocrv5")
        assert "t" in result.text

    def test_layout_model(self):
        engine = self._engine()
        data = {"result": {"layoutParsingResults": [{"markdown": {"text": "m"}}]}}
        result = engine._parse_response(data, "paddleocr_vl")
        assert "m" in result.text

    def test_unsupported_model_raises(self):
        engine = self._engine()
        with pytest.raises(RuntimeError, match="不支持"):
            engine._parse_response({}, "unknown_model")


class TestRecognizeBytesNotConfigured:
    """Cover the not-configured branch of recognize_bytes."""

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_raises_when_not_configured(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = ""
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        with pytest.raises(RuntimeError, match="未配置"):
            engine.recognize_bytes(b"image_data")


class TestExtractTextDelegates:
    """Cover extract_text and extract_text_from_pdf."""

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_extract_text_delegates(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_cls.return_value = MagicMock()
        engine = PaddleOCRApiEngine(model="pp_ocrv5")
        with patch.object(engine, "recognize_bytes", return_value="result") as mock_rec:
            result = engine.extract_text(b"img")
            mock_rec.assert_called_once_with(b"img", is_pdf=False)
            assert result == "result"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_extract_text_from_pdf_delegates(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_cls.return_value = MagicMock()
        engine = PaddleOCRApiEngine(model="pp_ocrv5")
        with patch.object(engine, "recognize_bytes", return_value="result") as mock_rec:
            result = engine.extract_text_from_pdf(b"pdf")
            mock_rec.assert_called_once_with(b"pdf", is_pdf=True)
            assert result == "result"


class TestModelInit:
    """Cover __init__ with explicit model."""

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_explicit_model(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_cls.return_value = MagicMock()
        engine = PaddleOCRApiEngine(model="paddleocr_vl_1_5")
        assert engine._model == "paddleocr_vl_1_5"
        assert engine.model == "paddleocr_vl_1_5"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_none_model_reads_from_config(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = "pp_structure_v3"
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine.model == "pp_structure_v3"
