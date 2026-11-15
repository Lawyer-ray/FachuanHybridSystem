"""PaddleOCR v2 Job API 收口与 PaddleOCR-VL-1.6 支持的回归测试。

覆盖三件在真实环境里踩过的坑：

1. 配置里存的是小写下划线键（``paddleocr_vl_1_6``），而服务端只认官方模型名
   （``PaddleOCR-VL-1.6``），发错直接 400「模型传参错误」(code=10007)。
2. 所有模型必须走同一个 Job API 端点；旧的每模型独立 URL（aistudio 体验域名）
   已全部失效返回 500。
3. Job API 的 ``jsonUrl`` 返回**单行完整 JSON**（``{logId, result:{...}}``），
   不是 JSONL；按 JSONL 解析会得到空文本。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.ocr import paddleocr_api_service as svc


def _engine(model: str, *, url: str = "https://job.example/api/v2/ocr/jobs") -> svc.PaddleOCRApiEngine:
    """构造一个绕过 SystemConfig 的引擎实例。"""
    engine = svc.PaddleOCRApiEngine(model=model)
    engine._config_service = MagicMock()
    engine._config_service.get_value.side_effect = lambda key, default="": {
        svc._UNIFIED_JOB_API_URL_KEY: url,
        "PADDLEOCR_API_TOKEN": "tok",
    }.get(key, default)
    return engine


class TestModelNameMapping:
    """配置键 → 官方模型名。"""

    @pytest.mark.parametrize(
        ("config_key", "api_name"),
        [
            ("paddleocr_vl_1_6", "PaddleOCR-VL-1.6"),
            ("paddleocr_vl_1_5", "PaddleOCR-VL-1.5"),
            ("paddleocr_vl", "PaddleOCR-VL"),
            ("pp_structure_v3", "PP-StructureV3"),
            ("pp_ocrv6", "PP-OCRv6"),
            ("pp_ocrv5", "PP-OCRv5"),
        ],
    )
    def test_api_model_name_maps_to_official(self, config_key: str, api_name: str) -> None:
        assert _engine(config_key).api_model_name == api_name

    def test_unknown_model_key_falls_through_unchanged(self) -> None:
        """未登记的键原样透传，便于将来新增模型时无需同步改两处。"""
        assert _engine("some_future_model").api_model_name == "some_future_model"


class TestUnifiedEndpoint:
    """所有模型共用同一个 Job API 端点。"""

    @pytest.mark.parametrize(
        "model",
        ["pp_ocrv5", "pp_ocrv6", "pp_structure_v3", "paddleocr_vl", "paddleocr_vl_1_5", "paddleocr_vl_1_6"],
    )
    def test_all_models_use_job_api_url(self, model: str) -> None:
        assert _engine(model).api_url == "https://job.example/api/v2/ocr/jobs"

    def test_vl16_is_recognised_as_layout_model(self) -> None:
        """VL-1.6 必须归入 layout 端点，否则会走 OCR 解析分支拿到空文本。"""
        assert "paddleocr_vl_1_6" in svc._LAYOUT_ENDPOINT_MODELS

    def test_pp_ocrv6_is_recognised_as_ocr_model(self) -> None:
        assert "pp_ocrv6" in svc._OCR_ENDPOINT_MODELS


class TestParseJobResult:
    """Job API 返回单行完整 JSON，不是 JSONL。"""

    def _layout_payload(self, text: str) -> str:
        return json.dumps(
            {
                "logId": "x",
                "result": {
                    "layoutParsingResults": [{"markdown": {"text": text}, "prunedResult": {}}],
                },
            },
            ensure_ascii=False,
        )

    def test_single_line_json_parsed_as_result(self) -> None:
        payload = self._layout_payload("# 标题\n\n兹证明张三丰老师")
        out = _engine("paddleocr_vl_1_6")._parse_job_result(payload, "paddleocr_vl_1_6")
        assert "张三丰" in out.text

    def test_jsonl_still_supported(self) -> None:
        line1 = self._layout_payload("第一段")
        line2 = self._layout_payload("第二段")
        out = _engine("paddleocr_vl_1_6")._parse_job_result(f"{line1}\n{line2}", "paddleocr_vl_1_6")
        assert "第一段" in out.text
        assert "第二段" in out.text

    def test_ocr_payload_rec_texts(self) -> None:
        payload = json.dumps(
            {"logId": "x", "result": {"ocrResults": [{"prunedResult": {"rec_texts": ["示例机构", "示例字段"]}}]}},
            ensure_ascii=False,
        )
        out = _engine("pp_ocrv6")._parse_job_result(payload, "pp_ocrv6")
        assert "示例机构" in out.text
        assert "示例字段" in out.text

    def test_malformed_payload_does_not_raise(self) -> None:
        """坏数据不能把整个识别任务弄挂。"""
        assert _engine("paddleocr_vl_1_6")._parse_job_result("not json at all", "paddleocr_vl_1_6").text == ""


class TestSubmitSendsOfficialModelName:
    """提交请求体里的 model 字段必须是官方模型名。"""

    def _run(self, model_key: str) -> dict[str, Any]:
        captured: dict[str, Any] = {}

        class _Resp:
            status_code = 500  # 提前返回，只看提交的 data 即可
            text = ""

            def json(self) -> dict[str, Any]:
                return {}

        class _Client:
            def __enter__(self) -> _Client:
                return self

            def __exit__(self, *a: Any) -> None:
                return None

            def post(self, url: str, **kwargs: Any) -> _Resp:
                captured["url"] = url
                captured["data"] = kwargs.get("data")
                return _Resp()

        with patch.object(svc.httpx, "Client", return_value=_Client()):
            with pytest.raises(RuntimeError):
                _engine(model_key).recognize_bytes(b"img", is_pdf=False)
        return captured

    def test_vl16_submits_official_name(self) -> None:
        captured = self._run("paddleocr_vl_1_6")
        assert captured["data"]["model"] == "PaddleOCR-VL-1.6"
        assert captured["url"] == "https://job.example/api/v2/ocr/jobs"
