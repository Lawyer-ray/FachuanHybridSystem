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
    def test_api_url_is_unified_job_endpoint_for_ocr_models(self, mock_cls):
        """OCR 类模型也走统一的 v2 Job API 端点。

        历史机制是「每模型一个 URL」（PADDLEOCR_OCR_API_URL / VL_API_URL / VL15_API_URL），
        那批 aistudio 体验域名已全部下线（500），现改为单一 JOB_API_URL + model 参数。
        """
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = lambda k, d="": (
            "http://job-api.test" if k == "PADDLEOCR_JOB_API_URL" else "pp_ocrv5"
        )
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine.api_url == "http://job-api.test"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_api_url_is_unified_job_endpoint_for_vl_model(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = lambda k, d="": (
            "paddleocr_vl"
            if k == "PADDLEOCR_API_MODEL"
            else "http://job-api.test"
            if k == "PADDLEOCR_JOB_API_URL"
            else ""
        )
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine.api_url == "http://job-api.test"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_api_url_is_unified_job_endpoint_for_vl15_model(self, mock_cls):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = lambda k, d="": (
            "paddleocr_vl_1_5"
            if k == "PADDLEOCR_API_MODEL"
            else "http://job-api.test"
            if k == "PADDLEOCR_JOB_API_URL"
            else ""
        )
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine.api_url == "http://job-api.test"

    @patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService")
    def test_dead_legacy_urls_are_never_read(self, mock_cls):
        """即使库里还残留旧的每模型 URL，也不会被读——防止回滚又把失效地址带回来。"""
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        dead = {
            "PADDLEOCR_OCR_API_URL": "http://dead-ocr.test",
            "PADDLEOCR_VL_API_URL": "http://dead-vl.test",
            "PADDLEOCR_VL15_API_URL": "http://dead-vl15.test",
        }
        mock_svc = MagicMock()
        mock_svc.get_value.side_effect = lambda k, d="": (
            "paddleocr_vl_1_5" if k == "PADDLEOCR_API_MODEL" else dead.get(k, "http://job-api.test")
        )
        mock_cls.return_value = mock_svc
        engine = PaddleOCRApiEngine()
        assert engine.api_url == "http://job-api.test"

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


class TestLayoutRawTextsNotPollutedByImageUrls:
    """layout 路径的 raw_texts 只能来自 markdown["text"]。

    实测污染：markdown["images"] 的 value 是 bcebos 绝对 URL，早期实现递归整个
    markdown dict，把图片地址当正文收进 raw_texts。这些链接一旦进入正文，下游会
    当成条款文本使用。
    """

    _IMAGE_KEY = "imgs/img_in_seal_box_762_886_977_1115.jpg"
    _IMAGE_URL = "https://pplines-online.bj.bcebos.com/example/img_in_seal_box.jpg"

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        return PaddleOCRApiEngine(model="paddleocr_vl_1_6")

    def _layout_result(self, text: str, images: dict[str, str] | None = None):
        markdown: dict[str, Any] = {"text": text}
        if images is not None:
            markdown["images"] = images
        return {"layoutParsingResults": [{"markdown": markdown}]}

    def test_image_urls_not_in_raw_texts_or_text(self):
        engine = self._engine()
        result = engine._parse_layout_response(
            self._layout_result("合同正文第一行", {self._IMAGE_KEY: self._IMAGE_URL}), "paddleocr_vl_1_6"
        )
        assert result.raw_texts == ["合同正文第一行"]
        assert self._IMAGE_URL not in result.text

    def test_raw_texts_split_by_non_empty_line(self):
        engine = self._engine()
        result = engine._parse_layout_response(self._layout_result("第一行\n\n第二行\n   \n第三行"), "paddleocr_vl_1_6")
        assert result.raw_texts == ["第一行", "第二行", "第三行"]

    def test_collect_text_fragments_unchanged_for_ocr_fallback(self):
        """_collect_text_fragments 仍保留原递归行为（_parse_ocr_response 兜底路径在用）。"""
        engine = self._engine()
        assert engine._collect_text_fragments({"images": {"a.jpg": "http://example.test/a.jpg"}}) == [
            "http://example.test/a.jpg"
        ]


class TestLayoutImagesCollection:
    """markdown["images"] → PaddleOCRApiImage 列表。"""

    _IMAGE_KEY = "imgs/img_in_seal_box_762_886_977_1115.jpg"
    _IMAGE_URL = "https://pplines-online.bj.bcebos.com/example/img_in_seal_box.jpg"

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        return PaddleOCRApiEngine(model="paddleocr_vl_1_6")

    def test_images_collected_with_key_and_url(self):
        engine = self._engine()
        result = engine._parse_layout_response(
            {"layoutParsingResults": [{"markdown": {"text": "正文", "images": {self._IMAGE_KEY: self._IMAGE_URL}}}]},
            "paddleocr_vl_1_6",
        )
        assert len(result.images) == 1
        image = result.images[0]
        assert image.key == self._IMAGE_KEY
        assert image.url == self._IMAGE_URL
        # 解析阶段不下载：data 必须留空,交给图片落地环节处理
        assert image.data is None
        assert image.content_type == "image/jpeg"

    def test_images_from_multiple_layout_results_are_merged(self):
        engine = self._engine()
        result = engine._parse_layout_response(
            {
                "layoutParsingResults": [
                    {"markdown": {"text": "第1页", "images": {"imgs/a.jpg": "https://cdn.test/a.jpg"}}},
                    {"markdown": {"text": "第2页", "images": {"imgs/b.jpg": "https://cdn.test/b.jpg"}}},
                ]
            },
            "paddleocr_vl_1_6",
        )
        assert [image.key for image in result.images] == ["imgs/a.jpg", "imgs/b.jpg"]
        assert result.raw_texts == ["第1页", "第2页"]

    def test_missing_or_dirty_images_yield_empty_list(self):
        engine = self._engine()
        result = engine._parse_layout_response(
            {
                "layoutParsingResults": [
                    {"markdown": {"text": "无图"}},
                    {"markdown": {"text": "脏数据", "images": {"imgs/c.jpg": ""}}},
                    {"markdown": {"text": "非字典", "images": ["imgs/d.jpg"]}},
                ]
            },
            "paddleocr_vl_1_6",
        )
        assert result.images == []

    def test_result_default_images_is_empty_list(self):
        """向后兼容：OCR 端点的结果不带 images 字段也应可用。"""
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiResult

        assert PaddleOCRApiResult(text="t", raw_texts=["t"], model="pp_ocrv5").images == []

    def test_ocr_response_has_no_images(self):
        engine = self._engine()
        result = engine._parse_ocr_response({"ocrResults": [{"prunedResult": {"rec_texts": ["t"]}}]}, "pp_ocrv5")
        assert result.images == []


class TestHtmlTableToMarkdown:
    """markdown["text"] 里的 HTML 表格 → GFM。"""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        return PaddleOCRApiEngine(model="paddleocr_vl_1_6")

    def _convert(self, text: str) -> str:
        from apps.automation.services.ocr.paddleocr_api_service import _convert_html_tables_to_markdown

        return _convert_html_tables_to_markdown(text)

    def test_table_converted_to_gfm(self):
        html = (
            "<table border=1 style='border-collapse:collapse;'><tr>"
            "<td style='padding:2px;'>序号</td><td style='padding:2px;'>项目</td></tr>"
            "<tr><td>1</td><td>违约金</td></tr></table>"
        )
        converted = self._convert(html)
        # 转换结果两侧补了换行,所以首尾各有一个空行（splitlines 保留首行空串）
        assert [line for line in converted.splitlines() if line] == [
            "| 序号 | 项目 |",
            "| --- | --- |",
            "| 1 | 违约金 |",
        ]

    def test_br_becomes_space(self):
        html = "<table><tr><td>名称<br>说明</td></tr></table>"
        assert "| 名称 说明 |" in self._convert(html)

    def test_html_entities_unescaped(self):
        html = "<table><tr><td>张三&nbsp;示例机构 &amp; 附件 &lt;甲&gt;</td></tr></table>"
        converted = self._convert(html)
        assert "张三 示例机构 & 附件 <甲>" in converted
        assert "&nbsp;" not in converted and "&amp;" not in converted

    def test_pipe_in_cell_escaped(self):
        html = "<table><tr><td>a|b</td><td>c</td></tr></table>"
        lines = [line for line in self._convert(html).splitlines() if line]
        assert lines[0] == "| a\\|b | c |"

    def test_uneven_rows_padded_to_same_width(self):
        html = "<table><tr><td>a</td><td>b</td><td>c</td></tr><tr><td>1</td></tr></table>"
        lines = [line for line in self._convert(html).splitlines() if line]
        assert lines[2] == "| 1 |  |  |"

    def test_colspan_pads_columns(self):
        html = "<table><tr><td colspan=2>合并</td><td>x</td></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>"
        lines = [line for line in self._convert(html).splitlines() if line]
        assert lines[0] == "| 合并 |  | x |"

    def test_multiple_tables_all_converted(self):
        text = "<table><tr><td>a</td></tr></table>中间文字<table><tr><td>b</td><td>c</td></tr></table>"
        converted = self._convert(text)
        assert "<table" not in converted
        assert converted.count("| --- |") == 2

    def test_table_kept_on_own_line(self):
        """表格两侧必须独占一行,否则「后文」会被 GFM 当成单元格内容。"""
        converted = self._convert("前文<table><tr><td>a</td></tr></table>后文")
        assert converted.splitlines() == ["前文", "| a |", "| --- |", "后文"]

    def test_no_table_returns_text_unchanged(self):
        assert self._convert("普通正文,无表格") == "普通正文,无表格"

    def test_conversion_failure_keeps_original_html(self):
        """转换抛异常时必须原样保留 HTML——不能因解析失败丢掉条款内容。"""
        original = "<table><tr><td>z</td></tr></table>"
        with patch(
            "apps.automation.services.ocr.paddleocr_api_service._html_table_to_markdown",
            side_effect=ValueError("boom"),
        ):
            assert self._convert(original) == original

    def test_table_without_rows_keeps_original_html(self):
        original = "<table><tr></tr></table>"
        assert self._convert(original) == original

    def test_layout_response_converts_embedded_table(self):
        engine = self._engine()
        text = "<table><tr><td>序号</td><td>金额</td></tr><tr><td>1</td><td>100元</td></tr></table>"
        result = engine._parse_layout_response(
            {"layoutParsingResults": [{"markdown": {"text": text}}]}, "paddleocr_vl_1_6"
        )
        assert "<table" not in result.text
        assert result.raw_texts[:1] == ["| 序号 | 金额 |"]


class TestJobTimeoutPolicy:
    """轮询总超时：单页给足 300s 下限，已知页数按页扩展。"""

    def _engine(self, timeout: float | None = None):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        with patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService"):
            return PaddleOCRApiEngine(model="paddleocr_vl_1_6", timeout=timeout)

    def test_unknown_page_count_uses_floor(self):
        assert self._engine()._resolve_job_timeout(None) == 300.0

    def test_zero_page_count_uses_floor(self):
        assert self._engine()._resolve_job_timeout(0) == 300.0

    def test_single_page_not_below_floor(self):
        # 单页实测 29s；1 页 × 50s = 50s 低于下限，必须被下限兜住
        assert self._engine()._resolve_job_timeout(1) == 300.0

    def test_many_pages_scale_by_page_budget(self):
        assert self._engine()._resolve_job_timeout(20) == 1000.0

    def test_explicit_timeout_overrides_policy(self):
        assert self._engine(timeout=42.0)._resolve_job_timeout(20) == 42.0

    def test_poll_attempts_follow_interval(self):
        engine = self._engine()
        assert engine._poll_max_attempts(300.0) == 100


class TestHttpxClientWiring:
    """一个 Client 贯穿提交/轮询/下载，且带分级超时与连接级重试。"""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        with patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService"):
            engine = PaddleOCRApiEngine(model="pp_ocrv5")
        engine._config_service = MagicMock()
        engine._config_service.get_value.side_effect = lambda key, default="": (
            "https://job.example/api" if key == "PADDLEOCR_JOB_API_URL" else "tok"
        )
        # 隔离凭证池：全局注册表按 pool_key 共享，测试间必须用唯一键，
        # 否则一处 token 进冷却会把后续用例全带挂。
        engine._pool_key = f"test-{id(engine)}"
        return engine

    @staticmethod
    def _response(status_code: int, payload: dict[str, Any] | None = None, text: str = "") -> Any:
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        resp.json.return_value = payload or {}
        return resp

    def test_single_client_reused_for_submit_poll_and_download(self):
        engine = self._engine()
        created: list[Any] = []

        def _factory(**kwargs: Any) -> Any:
            client = MagicMock()
            client.__enter__.return_value = client
            client.__exit__.return_value = False
            client.kwargs = kwargs
            client.post.return_value = self._response(200, {"data": {"jobId": "job-1"}})
            client.get.side_effect = [
                self._response(200, {"data": {"state": "done", "resultUrl": {"jsonUrl": "https://r.test/x"}}}),
                self._response(200, text='{"result": {"ocrResults": [{"prunedResult": {"rec_texts": ["ok"]}}]}}'),
            ]
            created.append(client)
            return client

        with (
            patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", side_effect=_factory),
            patch("time.sleep"),
        ):
            result = engine.recognize_bytes(b"img")

        assert result.text == "ok"
        assert len(created) == 1, "提交/轮询/下载必须复用同一个 Client"
        # 分级超时：连接/池短，读/写长
        timeout = created[0].kwargs["timeout"]
        assert isinstance(timeout, __import__("httpx").Timeout)
        assert timeout.connect == 10.0
        assert timeout.pool == 10.0
        assert timeout.read >= 60.0
        assert isinstance(created[0].kwargs["transport"], __import__("httpx").HTTPTransport)

    def test_poll_tolerates_transient_5xx_then_succeeds(self):
        engine = self._engine()
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.post.return_value = self._response(200, {"data": {"jobId": "job-1"}})
        client.get.side_effect = [
            self._response(502),
            self._response(200, {"data": {"state": "done", "resultUrl": {"jsonUrl": "https://r.test/x"}}}),
            self._response(200, text='{"result": {"ocrResults": [{"prunedResult": {"rec_texts": ["ok"]}}]}}'),
        ]

        with (
            patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", return_value=client),
            patch("time.sleep"),
        ):
            assert engine.recognize_bytes(b"img").text == "ok"

    def test_poll_gives_up_after_consecutive_failures(self):
        from apps.automation.services.ocr.paddleocr_api_service import _MAX_CONSECUTIVE_POLL_FAILURES

        engine = self._engine()
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.post.return_value = self._response(200, {"data": {"jobId": "job-1"}})
        client.get.return_value = self._response(503)

        with (
            patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", return_value=client),
            patch("time.sleep"),
        ):
            with pytest.raises(RuntimeError, match="轮询连续失败"):
                engine.recognize_bytes(b"img")

        assert client.get.call_count == _MAX_CONSECUTIVE_POLL_FAILURES

    def test_poll_client_error_fails_immediately(self):
        """401/404 这类重试也没用，必须立刻抛。"""
        engine = self._engine()
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.post.return_value = self._response(200, {"data": {"jobId": "job-1"}})
        client.get.return_value = self._response(401)

        with (
            patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", return_value=client),
            patch("time.sleep"),
        ):
            with pytest.raises(RuntimeError, match="HTTP 401"):
                engine.recognize_bytes(b"img")

        assert client.get.call_count == 1


def _read_extract_progress(*a, **k):
    """转发到模块级纯函数（原类方法已下沉，便于复用与测试）。"""
    from apps.automation.services.ocr.paddleocr_api_service import _read_extract_progress as fn

    return fn(*a, **k)


def _is_pollable_failure(*a, **k):
    from apps.automation.services.ocr.paddleocr_api_service import _is_pollable_failure as fn

    return fn(*a, **k)


def _safe_report_progress(*a, **k):
    from apps.automation.services.ocr.paddleocr_api_service import _safe_report_progress as fn

    return fn(*a, **k)


class TestExtractProgress:
    """extractProgress 通过 on_progress 透出。"""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        with patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService"):
            engine = PaddleOCRApiEngine(model="pp_ocrv5")
        engine._config_service = MagicMock()
        engine._config_service.get_value.side_effect = lambda key, default="": (
            "https://job.example/api" if key == "PADDLEOCR_JOB_API_URL" else "tok"
        )
        # 隔离凭证池：全局注册表按 pool_key 共享，测试间必须用唯一键，
        # 否则一处 token 进冷却会把后续用例全带挂。
        engine._pool_key = f"test-{id(engine)}"
        return engine

    def test_read_extract_progress(self):
        engine = self._engine()
        payload = {"data": {"extractProgress": {"startTime": 1, "endTime": 2, "totalPages": 5, "extractedPages": 2}}}
        assert _read_extract_progress(payload) == (2, 5)

    def test_read_extract_progress_without_total(self):
        engine = self._engine()
        payload = {"data": {"extractProgress": {"extractedPages": 3}}}
        assert _read_extract_progress(payload) == (3, None)

    def test_read_extract_progress_missing(self):
        engine = self._engine()
        assert _read_extract_progress({"data": {"state": "running"}}) is None
        assert _read_extract_progress({}) is None

    def test_read_extract_progress_garbage(self):
        engine = self._engine()
        assert _read_extract_progress({"data": {"extractProgress": {"extractedPages": "x"}}}) is None

    def test_on_progress_called_with_progress(self):
        engine = self._engine()
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.post.return_value = MagicMock(status_code=200, json=lambda: {"data": {"jobId": "job-1"}})
        client.get.side_effect = [
            MagicMock(
                status_code=200,
                json=lambda: {"data": {"state": "running", "extractProgress": {"totalPages": 4, "extractedPages": 1}}},
            ),
            MagicMock(
                status_code=200,
                json=lambda: {"data": {"state": "done", "resultUrl": {"jsonUrl": "https://r.test/x"}}},
            ),
            MagicMock(status_code=200, text='{"result": {"ocrResults": [{"prunedResult": {"rec_texts": ["ok"]}}]}}'),
        ]
        seen: list[tuple[int, int | None]] = []

        with (
            patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", return_value=client),
            patch("time.sleep"),
        ):
            engine.recognize_bytes(b"img", on_progress=lambda extracted, total: seen.append((extracted, total)))

        assert seen == [(1, 4)]

    def test_on_progress_exception_is_swallowed(self):
        engine = self._engine()
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.post.return_value = MagicMock(status_code=200, json=lambda: {"data": {"jobId": "job-1"}})
        client.get.side_effect = [
            MagicMock(
                status_code=200,
                json=lambda: {"data": {"state": "running", "extractProgress": {"totalPages": 4, "extractedPages": 1}}},
            ),
            MagicMock(
                status_code=200,
                json=lambda: {"data": {"state": "done", "resultUrl": {"jsonUrl": "https://r.test/x"}}},
            ),
            MagicMock(status_code=200, text='{"result": {"ocrResults": [{"prunedResult": {"rec_texts": ["ok"]}}]}}'),
        ]

        def _boom(extracted: int, total: int | None) -> None:
            raise ValueError("callback failed")

        with (
            patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", return_value=client),
            patch("time.sleep"),
        ):
            assert engine.recognize_bytes(b"img", on_progress=_boom).text == "ok"


class TestAsyncTransportWiring:
    """异步版同样：单 client 贯穿、分级超时、连续失败容忍、进度回调。"""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        with patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService"):
            engine = PaddleOCRApiEngine(model="pp_ocrv5")
        engine._config_service = MagicMock()
        engine._config_service.get_value.side_effect = lambda key, default="": (
            "https://job.example/api" if key == "PADDLEOCR_JOB_API_URL" else "tok"
        )
        # 隔离凭证池：全局注册表按 pool_key 共享，测试间必须用唯一键，
        # 否则一处 token 进冷却会把后续用例全带挂。
        engine._pool_key = f"test-{id(engine)}"
        return engine

    def test_async_client_reused_and_transport_configured(self):
        import asyncio

        engine = self._engine()
        created: list[Any] = []

        def _factory(**kwargs: Any) -> Any:
            client = MagicMock()
            client.__aenter__ = _async_return(client)
            client.__aexit__ = _async_return(False)
            client.kwargs = kwargs

            async def _post(*a: Any, **kw: Any) -> Any:
                return MagicMock(status_code=200, json=lambda: {"data": {"jobId": "job-1"}})

            async def _get(*a: Any, **kw: Any) -> Any:
                if _get.calls == 0:
                    _get.calls += 1
                    return MagicMock(
                        status_code=200,
                        json=lambda: {"data": {"state": "done", "resultUrl": {"jsonUrl": "https://r.test/x"}}},
                    )
                return MagicMock(
                    status_code=200, text='{"result": {"ocrResults": [{"prunedResult": {"rec_texts": ["ok"]}}]}}'
                )

            _get.calls = 0
            client.post = _post
            client.get = _get
            created.append(client)
            return client

        with (
            patch("apps.automation.services.ocr.paddleocr_api_service.httpx.AsyncClient", side_effect=_factory),
            patch("asyncio.sleep", _async_return(None)),
        ):
            result = asyncio.run(engine.arecognize_bytes(b"img"))

        assert result.text == "ok"
        assert len(created) == 1
        timeout = created[0].kwargs["timeout"]
        assert timeout.connect == 10.0
        assert timeout.read >= 60.0
        assert isinstance(created[0].kwargs["transport"], __import__("httpx").AsyncHTTPTransport)


def _async_return(value: Any):
    """构造一个「await 后返回 value」的异步函数，供 AsyncClient mock 使用。"""

    async def _inner(*args: Any, **kwargs: Any) -> Any:
        return value

    return _inner


class TestDownloadImages:
    """印章/照片下载：失败容忍、并发、已有字节不重下。"""

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        return PaddleOCRApiEngine(model="paddleocr_vl_1_6")

    def _image(self, key: str, url: str = "https://cdn.test/a.jpg", data: bytes | None = None):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiImage

        return PaddleOCRApiImage(key=key, url=url, data=data)

    def test_empty_list_returns_empty(self):
        assert self._engine().download_images([]) == []

    def test_already_downloaded_not_refetched(self):
        """已有 data 的图不该再打一次网络——上层重试第二次时省掉重复流量。"""
        engine = self._engine()
        img = self._image("imgs/a.jpg", data=b"cached")
        with patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client") as client_cls:
            out = engine.download_images([img])
        client_cls.assert_not_called()
        assert out[0].data == b"cached"

    def test_download_success_fills_data(self):
        engine = self._engine()
        img = self._image("imgs/seal.jpg")

        class _Resp:
            status_code = 200
            content = b"seal-bytes"

        class _Client:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def get(self, url):
                return _Resp()

        with patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", _Client):
            out = engine.download_images([img])
        assert out[0].data == b"seal-bytes"

    def test_http_error_keeps_url_but_no_data(self):
        """单张 404 不能让整页识别作废：保留 url（可后补），data 为 None。"""
        engine = self._engine()
        img = self._image("imgs/gone.jpg")

        class _Resp:
            status_code = 404
            content = b""

        class _Client:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def get(self, url):
                return _Resp()

        with patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", _Client):
            out = engine.download_images([img])
        assert out[0].data is None
        assert out[0].url == "https://cdn.test/a.jpg"

    def test_network_exception_is_swallowed(self):
        import httpx as _httpx

        engine = self._engine()
        img = self._image("imgs/boom.jpg")

        class _Client:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def get(self, url):
                raise _httpx.ConnectError("boom")

        with patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", _Client):
            out = engine.download_images([img])
        assert out[0].data is None

    def test_multiple_images_concurrent_path(self):
        """两张以上会走线程池分支，返回值顺序必须与入参一致。"""
        engine = self._engine()
        imgs = [self._image("imgs/1.jpg"), self._image("imgs/2.jpg")]

        class _Resp:
            status_code = 200

            def __init__(self, body):
                self.content = body

        class _Client:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def get(self, url):
                return _Resp(url.encode())

        with patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", _Client):
            out = engine.download_images(imgs)
        assert [i.key for i in out] == ["imgs/1.jpg", "imgs/2.jpg"]
        assert out[0].data == b"https://cdn.test/a.jpg"


def persist_images(*args, **kwargs):
    """转发到模块级 persist_images（该类方法已下沉为纯函数，便于复用与测试）。"""
    from apps.automation.services.ocr.paddleocr_api_service import persist_images as _fn

    return _fn(*args, **kwargs)


class TestPersistImages:
    """图片落盘：storage 注入、同名覆盖、单张失败不阻断。"""

    def _image(self, key: str, data: bytes | None = b"bytes"):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiImage

        return PaddleOCRApiImage(key=key, url="https://cdn.test/" + key, data=data)

    def _engine(self):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        return PaddleOCRApiEngine(model="paddleocr_vl_1_6")

    def test_no_prefix_returns_empty(self):
        assert persist_images([self._image("imgs/a.jpg")], storage=MagicMock(), prefix="") == {}

    def test_skips_images_without_data(self):
        storage = MagicMock()
        out = persist_images([self._image("imgs/a.jpg", data=None)], storage=storage, prefix="p")
        storage.save.assert_not_called()
        assert out == {}

    def test_saves_with_prefix_and_filename(self):
        storage = MagicMock()
        storage.exists.return_value = False
        storage.save.side_effect = lambda name, content: name
        out = persist_images(
            [self._image("imgs/img_in_seal_box_1_2.jpg")],
            storage=storage,
            prefix="pdf_splitting/ocr_images/abc/p031",
        )
        assert out == {"imgs/img_in_seal_box_1_2.jpg": "pdf_splitting/ocr_images/abc/p031/img_in_seal_box_1_2.jpg"}
        saved_name = storage.save.call_args[0][0]
        # 目录部分被丢弃，只保留文件名拼在前缀下
        assert saved_name == "pdf_splitting/ocr_images/abc/p031/img_in_seal_box_1_2.jpg"

    def test_overwrites_existing_file(self):
        """重跑同一页时先删旧文件，避免 default_storage 同名改名留下残档。"""
        storage = MagicMock()
        storage.exists.return_value = True
        storage.save.side_effect = lambda name, content: name
        persist_images([self._image("imgs/a.jpg")], storage=storage, prefix="p")
        storage.delete.assert_called_once_with("p/a.jpg")

    def test_save_failure_does_not_raise(self):
        storage = MagicMock()
        storage.exists.return_value = False
        storage.save.side_effect = OSError("disk full")
        out = persist_images([self._image("imgs/a.jpg")], storage=storage, prefix="p")
        assert out == {}


class TestMultiTokenPool:
    """多 Key 并发：解析、轮询分配、整个任务周期绑定同一 Key、归还进冷却。"""

    def _engine(self, tokens: list[str]):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        engine = PaddleOCRApiEngine(model="paddleocr_vl_1_6")
        engine._config_service = MagicMock()
        engine._config_service.get_value.side_effect = lambda k, d="": {
            "PADDLEOCR_JOB_API_URL": "https://job.test/api/v2/ocr/jobs",
            "PADDLEOCR_API_TOKEN": "\n".join(tokens),
        }.get(k, d)
        # 隔离凭证池：全局注册表按 pool_key 共享，测试间必须用唯一键，
        # 否则一处 token 进冷却会把后续用例全带挂。
        engine._pool_key = f"test-{id(engine)}"
        return engine

    def test_parses_newline_separated_tokens(self):
        engine = self._engine(["tok-a", "tok-b", "tok-c"])
        assert engine.api_tokens == ["tok-a", "tok-b", "tok-c"]

    def test_parses_comma_and_semicolon_separators(self):
        """用户在 textarea 里习惯不一：换行/逗号/分号都认。"""
        engine = self._engine(["tok-a,tok-b;tok-c"])
        assert engine.api_tokens == ["tok-a", "tok-b", "tok-c"]

    def test_blank_lines_are_dropped(self):
        """空行不能变成空 token，否则会拿 'bearer ' 去打接口。"""
        engine = self._engine(["tok-a", "", "   ", "tok-b"])
        assert engine.api_tokens == ["tok-a", "tok-b"]

    def test_single_token_backward_compatible(self):
        engine = self._engine(["only-one"])
        assert engine.api_token == "only-one"
        assert engine.api_tokens == ["only-one"]

    def test_api_token_returns_first_when_many(self):
        engine = self._engine(["first", "second"])
        assert engine.api_token == "first"

    def test_is_configured_requires_token(self):
        engine = self._engine([])
        assert engine._is_configured() is False

    def test_pool_round_robins_across_keys(self):
        engine = self._engine(["k0", "k1", "k2"])
        pool = engine._credential_pool()
        picked = []
        for _ in range(6):
            idx = pool.acquire()
            picked.append(idx)
            pool.release(idx, success=True)
        # 3 个 Key 轮询，6 次应各命中 2 次
        assert picked == [0, 1, 2, 0, 1, 2]

    def test_pool_limit_one_per_key(self):
        """同一 Key 同时只跑一单，多 Key 才能真正并行。"""
        engine = self._engine(["k0", "k1"])
        assert engine._credential_pool().limit == 1


class TestMultiTokenRequestBinding:
    """一个任务周期内必须绑定同一个 Key（提交用 A、轮询用 B 会 404）。"""

    def _engine(self, tokens: list[str]):
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        engine = PaddleOCRApiEngine(model="paddleocr_vl_1_6", timeout=30.0)
        engine._config_service = MagicMock()
        engine._config_service.get_value.side_effect = lambda k, d="": {
            "PADDLEOCR_JOB_API_URL": "https://job.test/api/v2/ocr/jobs",
            "PADDLEOCR_API_TOKEN": "\n".join(tokens),
        }.get(k, d)
        # 隔离凭证池：全局注册表按 pool_key 共享，测试间必须用唯一键，
        # 否则一处 token 进冷却会把后续用例全带挂。
        engine._pool_key = f"test-{id(engine)}"
        return engine

    def test_submit_and_poll_use_same_token(self):
        engine = self._engine(["tok-a", "tok-b"])
        seen_auth: list[str] = []

        class _Resp:
            def __init__(self, payload, status=200):
                self.status_code = status
                self._payload = payload
                self.text = json.dumps(payload)

            def json(self):
                return self._payload

        class _Client:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def post(self, url, **kw):
                seen_auth.append(kw["headers"]["Authorization"])
                return _Resp({"code": 0, "data": {"jobId": "job-1"}})

            def get(self, url, **kw):
                # 下载结果走 bcebos 直链、不带 Authorization，所以要取可选
                auth = (kw.get("headers") or {}).get("Authorization")
                if auth:
                    seen_auth.append(auth)
                if url.endswith("job-1"):
                    return _Resp({"data": {"state": "done", "resultUrl": {"jsonUrl": "https://cdn.test/r.json"}}})
                return _Resp(
                    {"logId": "x", "result": {"layoutParsingResults": [{"markdown": {"text": "正文", "images": {}}}]}}
                )

        with (
            patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", _Client),
            patch("apps.automation.services.ocr.paddleocr_api_service.time.sleep", lambda *a: None),
        ):
            out = engine.recognize_bytes(b"img")

        assert "正文" in out.text
        # 提交与轮询的 Authorization 必须是同一个 Key
        auth_values = [a for a in seen_auth if a.startswith("bearer")]
        assert len(set(auth_values)) == 1, auth_values

    def test_token_released_after_success(self):
        engine = self._engine(["tok-a"])
        pool = engine._credential_pool()

        class _Resp:
            def __init__(self, payload, status=200):
                self.status_code = status
                self._payload = payload
                self.text = json.dumps(payload)

            def json(self):
                return self._payload

        class _Client:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def post(self, url, **kw):
                return _Resp({"code": 0, "data": {"jobId": "j"}})

            def get(self, url, **kw):
                if url.endswith("/j"):
                    return _Resp({"data": {"state": "done", "resultUrl": {"jsonUrl": "https://cdn.test/r.json"}}})
                return _Resp(
                    {"logId": "x", "result": {"layoutParsingResults": [{"markdown": {"text": "ok", "images": {}}}]}}
                )

        with (
            patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", _Client),
            patch("apps.automation.services.ocr.paddleocr_api_service.time.sleep", lambda *a: None),
        ):
            engine.recognize_bytes(b"img")

        # 归还后槽位应空出来：再 acquire 能立刻拿到，说明没被永久占用
        idx = pool.acquire()
        assert idx is not None
        pool.release(idx, success=True)

    def test_all_tokens_cooling_raises(self):
        engine = self._engine(["tok-a"])
        pool = engine._credential_pool()
        idx = pool.acquire()
        pool.release(idx, success=False)  # 打进冷却

        with pytest.raises(RuntimeError, match="冷却"):
            engine.recognize_bytes(b"img")


class TestPageOrientation:
    """整页方向分类：开哪些模型、angle 怎么解析、脏值怎么降级。

    坐标反变换（转正帧 → 原页帧）不在本模块做，本模块只负责把 angle **透出**且不因为
    一个脏字段把整次识别作废；反变换的公式与标定见
    ``tests/ci/unit/pdf_splitting/test_page_rotation.py``。
    """

    def _engine(self, model: str = "paddleocr_vl") -> Any:
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        with patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService"):
            return PaddleOCRApiEngine(model=model)

    def _configured_engine(self, model: str) -> Any:
        from apps.automation.services.ocr import paddleocr_api_service as svc

        with patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService"):
            engine = svc.PaddleOCRApiEngine(model=model)
        engine._config_service = MagicMock()
        engine._config_service.get_value.side_effect = lambda key, default="": (
            "https://job.example/api" if key == svc._UNIFIED_JOB_API_URL_KEY else "tok"
        )
        # 隔离凭证池：全局注册表按 pool_key 共享，测试间必须用唯一键
        engine._pool_key = f"test-orient-{id(engine)}"
        return engine

    @staticmethod
    def _response(status_code: int, payload: dict[str, Any] | None = None, text: str = "") -> Any:
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        resp.json.return_value = payload or {}
        return resp

    def test_开关只对版面类与_pp_structure_生效(self) -> None:
        """PP-OCRv5/v6 是纯文字场景：不为罕见躺倒页给每一页都加一次分类模型前向。"""
        from apps.automation.services.ocr.paddleocr_api_service import _DOC_ORIENTATION_MODELS

        for model in ("pp_structure_v3", "paddleocr_vl", "paddleocr_vl_1_5", "paddleocr_vl_1_6"):
            assert model in _DOC_ORIENTATION_MODELS, model
        for model in ("pp_ocrv5", "pp_ocrv6"):
            assert model not in _DOC_ORIENTATION_MODELS, model

    @pytest.mark.parametrize(
        ("model", "expected"), [("pp_structure_v3", True), ("paddleocr_vl", True), ("pp_ocrv5", False)]
    )
    def test_同步提交的_optionalPayload_按模型带方向开关(self, model: str, expected: bool) -> None:
        engine = self._configured_engine(model)
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.post.return_value = self._response(200, {"data": {"jobId": "job-1"}})
        # 只看提交参数：轮询立刻 failed 结束，不必造完整结果
        client.get.return_value = self._response(200, {"data": {"state": "failed", "errorMsg": "stop"}})

        with (
            patch("apps.automation.services.ocr.paddleocr_api_service.httpx.Client", return_value=client),
            patch("time.sleep"),
        ):
            with pytest.raises(RuntimeError, match="Job 失败"):
                engine.recognize_bytes(b"img")

        payload = json.loads(client.post.call_args.kwargs["data"]["optionalPayload"])
        assert payload["useDocOrientationClassify"] is expected

    def test_异步提交的_optionalPayload_同样带方向开关(self) -> None:
        """同步/异步两份 optionalPayload 是手抄的，必须各测一次（漂了就是「只在后台队列里生效」）。"""
        import asyncio

        engine = self._configured_engine("paddleocr_vl")
        captured: dict[str, Any] = {}

        def _factory(**kwargs: Any) -> Any:
            client = MagicMock()
            client.__aenter__ = _async_return(client)
            client.__aexit__ = _async_return(False)

            async def _post(*args: Any, **kw: Any) -> Any:
                captured.update(kw)
                return MagicMock(status_code=200, json=lambda: {"data": {"jobId": "job-1"}})

            async def _get(*args: Any, **kw: Any) -> Any:
                return MagicMock(status_code=200, json=lambda: {"data": {"state": "failed", "errorMsg": "stop"}})

            client.post = _post
            client.get = _get
            return client

        with (
            patch("apps.automation.services.ocr.paddleocr_api_service.httpx.AsyncClient", side_effect=_factory),
            patch("asyncio.sleep", _async_return(None)),
        ):
            with pytest.raises(RuntimeError, match="Job 失败"):
                asyncio.run(engine.arecognize_bytes(b"img"))

        payload = json.loads(captured["data"]["optionalPayload"])
        assert payload["useDocOrientationClassify"] is True

    def test_解析透出逐页方向与转正帧尺寸(self) -> None:
        engine = self._engine()
        data = {
            "result": {
                "layoutParsingResults": [
                    {
                        "markdown": {"text": "甲医院 疾病诊断证明书"},
                        "prunedResult": {
                            "width": 1753,
                            "height": 1240,
                            "doc_preprocessor_res": {"angle": 270},
                        },
                    }
                ]
            }
        }

        parsed = engine._parse_response(data, "paddleocr_vl")

        assert [(o.angle, o.width, o.height) for o in parsed.page_orientations] == [(270, 1753, 1240)]

    def test_没有方向字段时按零处理(self) -> None:
        """关闭方向分类时响应里没有这个字段 —— 这是正常路径，不许告警刷屏。"""
        engine = self._engine()
        data = {
            "result": {
                "layoutParsingResults": [{"markdown": {"text": "m"}, "prunedResult": {"width": 100, "height": 200}}]
            }
        }

        parsed = engine._parse_response(data, "paddleocr_vl")

        assert [(o.angle, o.width, o.height) for o in parsed.page_orientations] == [(0, 100, 200)]

    @pytest.mark.parametrize("raw_angle", [45, "abc", -30])
    def test_脏角度归零且告警(self, raw_angle: Any, caplog: pytest.LogCaptureFixture) -> None:
        engine = self._engine()
        data = {
            "result": {
                "layoutParsingResults": [
                    {
                        "markdown": {"text": "m"},
                        "prunedResult": {"width": 100, "height": 200, "doc_preprocessor_res": {"angle": raw_angle}},
                    }
                ]
            }
        }

        with caplog.at_level("WARNING"):
            parsed = engine._parse_response(data, "paddleocr_vl")

        assert parsed.page_orientations[0].angle == 0, "脏值按「没转」处理，不编一个角度"
        assert "方向解析" in caplog.text

    def test_jsonl_多页逐页累加且裸片段不补位(self) -> None:
        """裸片段行不能占一个页位——占了就会把 A 页的 angle 用到 B 页上。"""
        engine = self._engine()
        first = json.dumps(
            {
                "result": {
                    "layoutParsingResults": [{"markdown": {"text": "a"}, "prunedResult": {"width": 100, "height": 200}}]
                }
            },
            ensure_ascii=False,
        )
        fragment = json.dumps({"result": {"rec_texts": ["裸片段"]}}, ensure_ascii=False)
        second = json.dumps(
            {
                "result": {
                    "layoutParsingResults": [
                        {
                            "markdown": {"text": "b"},
                            "prunedResult": {"width": 200, "height": 100, "doc_preprocessor_res": {"angle": 90}},
                        }
                    ]
                }
            },
            ensure_ascii=False,
        )

        parsed = engine._parse_jsonl_response("\n".join([first, fragment, second]), "paddleocr_vl")

        assert [o.angle for o in parsed.page_orientations] == [0, 90]

    def test_表格带上本页转正角度(self) -> None:
        """表格的像素框在转正帧，消费方要靠这个字段反变换 —— 丢了就等于没透出。"""
        engine = self._engine("pp_structure_v3")
        table = {"cell_box_list": [[420, 486, 887, 650]], "pred_html": "<table><tr><td>甲</td></tr></table>"}
        data = {
            "result": {
                "layoutParsingResults": [
                    {
                        "prunedResult": {
                            "width": 1753,
                            "height": 1240,
                            "doc_preprocessor_res": {"angle": 270},
                            "table_res_list": [table],
                        }
                    }
                ]
            }
        }

        parsed = engine._parse_response(data, "pp_structure_v3")

        assert parsed.tables and parsed.tables[0].page_angle == 270
        assert parsed.tables[0].image_size == (1753, 1240), "image_size 是**转正帧**尺寸，反变换的两个基准之一"

    def test_表格没有方向字段时角度为零(self) -> None:
        engine = self._engine("pp_structure_v3")
        table = {"cell_box_list": [[420, 486, 887, 650]], "pred_html": "<table><tr><td>甲</td></tr></table>"}
        data = {
            "result": {
                "layoutParsingResults": [{"prunedResult": {"width": 1753, "height": 1240, "table_res_list": [table]}}]
            }
        }

        parsed = engine._parse_response(data, "pp_structure_v3")

        assert parsed.tables and parsed.tables[0].page_angle == 0
