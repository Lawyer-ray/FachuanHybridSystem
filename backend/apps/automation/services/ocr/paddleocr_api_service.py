"""
PaddleOCR API 云端引擎

调用百度 AI 开放平台的 PaddleOCR API，支持：
- PP-OCRv5：纯文字 OCR，适合证件/快递单号/简单文字提取
- PP-StructureV3：文档结构化分析，适合表格/版面分析
- PaddleOCR-VL：版面分析 + OCR（输出 Markdown），适合复杂文档/合同
- PaddleOCR-VL-1.5：VL 升级版，更高精度版面分析，适合法律文书/密集排版文档

API_URL / Token 通过 SystemConfig 管理。
"""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from apps.core.services.system_config_service import SystemConfigService

logger = logging.getLogger(__name__)

# 模型 → API 端点类型映射
_OCR_ENDPOINT_MODELS = {"pp_ocrv5", "pp_structure_v3"}
_LAYOUT_ENDPOINT_MODELS = {"paddleocr_vl", "paddleocr_vl_1_5"}

# 模型 → 对应的 SystemConfig URL Key 映射
_MODEL_URL_KEY_MAP: dict[str, str] = {
    "pp_ocrv5": "PADDLEOCR_OCR_API_URL",
    "pp_structure_v3": "PADDLEOCR_OCR_API_URL",
    "paddleocr_vl": "PADDLEOCR_VL_API_URL",
    "paddleocr_vl_1_5": "PADDLEOCR_VL15_API_URL",
}

# 文件类型：0=PDF, 1=图片
_FILE_TYPE_PDF = 0
_FILE_TYPE_IMAGE = 1

# 请求超时（秒）
_REQUEST_TIMEOUT = 120.0


@dataclass(frozen=True)
class PaddleOCRApiResult:
    """PaddleOCR API 识别结果"""

    text: str  # 合并后的文本
    raw_texts: list[str]  # 原始文本列表
    model: str  # 使用的模型名称


class PaddleOCRApiEngine:
    """PaddleOCR API 云端引擎"""

    def _looks_like_json_noise(self, text: str) -> bool:
        """判断是否为结构化 JSON/调试噪声文本。"""
        candidate = text.strip()
        if len(candidate) < 10:
            return False

        if (candidate.startswith("{") and candidate.endswith("}")) or (
            candidate.startswith("[") and candidate.endswith("]")
        ):
            return True

        if re.search(r'"[A-Za-z_][\w-]*"\s*:', candidate):
            return True

        json_chars = sum(1 for c in candidate if c in '{}[]":,')
        if len(candidate) >= 30 and (json_chars / len(candidate)) > 0.30:
            return True

        return False

    def __init__(self, model: str | None = None) -> None:
        """
        初始化 PaddleOCR API 引擎

        Args:
            model: 模型名称，None 时从 SystemConfig 读取
        """
        self._model = model
        self._config_service = SystemConfigService()

    @property
    def model(self) -> str:
        """获取当前使用的模型名称"""
        if self._model:
            return self._model
        return str(self._config_service.get_value("PADDLEOCR_API_MODEL", "pp_ocrv5") or "pp_ocrv5")

    @property
    def api_url(self) -> str:
        """获取当前模型对应的 API URL"""
        url_key = _MODEL_URL_KEY_MAP.get(self.model, "PADDLEOCR_OCR_API_URL")
        return str(self._config_service.get_value(url_key, "") or "")

    @property
    def api_token(self) -> str:
        """获取 API Token"""
        return str(self._config_service.get_value("PADDLEOCR_API_TOKEN", "") or "")

    def _is_configured(self) -> bool:
        """检查是否已配置必要的 API 参数"""
        return bool(self.api_url and self.api_token)

    def recognize_bytes(self, image_bytes: bytes, is_pdf: bool = False) -> PaddleOCRApiResult:
        """
        识别图片/PDF字节数据中的文字

        Args:
            image_bytes: 图片或 PDF 字节数据
            is_pdf: 是否为 PDF 文件

        Returns:
            PaddleOCRApiResult: 识别结果
        """
        if not self._is_configured():
            raise RuntimeError("PaddleOCR API 未配置：请先在系统配置中设置 API URL 和 Token")

        model = self.model
        file_data = base64.b64encode(image_bytes).decode("ascii")
        file_type = _FILE_TYPE_PDF if is_pdf else _FILE_TYPE_IMAGE

        payload: dict[str, Any] = {
            "file": file_data,
            "fileType": file_type,
        }

        # 根据模型类型添加可选参数
        if model in _OCR_ENDPOINT_MODELS:
            payload.update({
                "useDocOrientationClassify": False,
                "useDocUnwarping": False,
                "useTextlineOrientation": False,
            })
        elif model in _LAYOUT_ENDPOINT_MODELS:
            payload.update({
                "useDocOrientationClassify": False,
                "useDocUnwarping": False,
                "useChartRecognition": False,
            })

        headers = {
            "Authorization": f"token {self.api_token}",
            "Content-Type": "application/json",
        }

        logger.info("PaddleOCR API 调用: model=%s, file_type=%s, data_size=%d", model, file_type, len(image_bytes))

        try:
            with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
                response = client.post(self.api_url, json=payload, headers=headers)

            if response.status_code != 200:
                logger.warning(
                    "PaddleOCR API 调用失败: status=%d, body=%s",
                    response.status_code,
                    response.text[:500],
                )
                raise RuntimeError(f"PaddleOCR API 返回错误: HTTP {response.status_code}")

            response_data = response.json()
            logger.info("PaddleOCR API 原始响应长度: %d", len(response.text))
            logger.info("PaddleOCR API 原始响应数据: %s", json.dumps(response_data, ensure_ascii=False, default=str))
            return self._parse_response(response_data, model)

        except httpx.TimeoutException as e:
            logger.warning("PaddleOCR API 超时: %s", e)
            raise RuntimeError(f"PaddleOCR API 超时: {e}") from e
        except httpx.HTTPError as e:
            logger.warning("PaddleOCR API 网络错误: %s", e)
            raise RuntimeError(f"PaddleOCR API 网络错误: {e}") from e

    def _parse_response(self, data: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """
        解析 API 响应

        PP-OCRv5 / PP-StructureV3: result.ocrResults[].prunedResult
        PaddleOCR-VL / VL-1.5: result.layoutParsingResults[].markdown.text
        """
        result = data.get("result", {})

        if model in _OCR_ENDPOINT_MODELS:
            return self._parse_ocr_response(result, model)
        elif model in _LAYOUT_ENDPOINT_MODELS:
            return self._parse_layout_response(result, model)
        else:
            raise RuntimeError(f"不支持的 PaddleOCR 模型: {model}")

    def _collect_text_fragments(self, value: Any) -> list[str]:
        """从任意嵌套结构中提取可读文本片段。"""
        fragments: list[str] = []

        if value is None:
            return fragments

        if isinstance(value, str):
            text = value.strip()
            if text and not self._looks_like_json_noise(text):
                fragments.append(text)
            return fragments

        if isinstance(value, list):
            for item in value:
                fragments.extend(self._collect_text_fragments(item))
            return fragments

        if isinstance(value, dict):
            # 常见文本键优先，随后再遍历其余键，避免漏掉嵌套文本
            priority_keys = ("text", "value", "content", "prunedResult", "markdown")
            visited_keys: set[str] = set()

            for key in priority_keys:
                if key in value:
                    visited_keys.add(key)
                    fragments.extend(self._collect_text_fragments(value[key]))

            for key, item in value.items():
                if key in visited_keys:
                    continue
                fragments.extend(self._collect_text_fragments(item))

            return fragments

        text = str(value).strip()
        if text:
            fragments.append(text)

        return fragments

    def _collect_rec_texts(self, value: Any) -> list[str]:
        """仅提取 rec_texts 字段值（支持嵌套与 JSON 字符串）。"""
        texts: list[str] = []

        if value is None:
            return texts

        if isinstance(value, str):
            candidate = value.strip()
            if candidate.startswith("{") or candidate.startswith("["):
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    return texts
                return self._collect_rec_texts(parsed)
            return texts

        if isinstance(value, list):
            for item in value:
                texts.extend(self._collect_rec_texts(item))
            return texts

        if isinstance(value, dict):
            rec_values = value.get("rec_texts")
            if isinstance(rec_values, list):
                for rec in rec_values:
                    if isinstance(rec, str):
                        rec_text = rec.strip()
                        if rec_text:
                            texts.append(rec_text)

            for nested in value.values():
                texts.extend(self._collect_rec_texts(nested))

            if texts:
                # 去重并保持顺序
                deduplicated = list(dict.fromkeys(texts))
                return deduplicated

        return texts

    def _parse_ocr_response(self, result: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """解析 OCR 端点响应（PP-OCRv5 / PP-StructureV3）"""
        ocr_results = result.get("ocrResults", [])
        all_texts: list[str] = []
        rec_texts_hit = 0

        for item in ocr_results:
            pruned = item.get("prunedResult", "")
            rec_texts = self._collect_rec_texts(pruned)
            if rec_texts:
                rec_texts_hit += 1
                all_texts.extend(rec_texts)
                continue

            # 兼容兜底：当 rec_texts 缺失时，退回通用提取
            all_texts.extend(self._collect_text_fragments(pruned))

        merged = "\n".join(all_texts)
        logger.info(
            "PaddleOCR API (OCR) 识别完成: model=%s, text_len=%d, rec_texts_hit=%d/%d",
            model,
            len(merged),
            rec_texts_hit,
            len(ocr_results),
        )
        return PaddleOCRApiResult(text=merged, raw_texts=all_texts, model=model)

    def _parse_layout_response(self, result: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """解析版面分析端点响应（PaddleOCR-VL / VL-1.5）"""
        layout_results = result.get("layoutParsingResults", [])
        all_texts: list[str] = []

        for item in layout_results:
            markdown_data = item.get("markdown", {})
            all_texts.extend(self._collect_text_fragments(markdown_data))

        merged = "\n".join(all_texts)
        logger.info("PaddleOCR API (Layout) 识别完成: model=%s, text_len=%d", model, len(merged))
        return PaddleOCRApiResult(text=merged, raw_texts=all_texts, model=model)

    def extract_text(self, image_bytes: bytes) -> PaddleOCRApiResult:
        """
        提取图片中的文字（兼容 OCRService 接口）

        Args:
            image_bytes: 图片字节数据

        Returns:
            PaddleOCRApiResult: 识别结果
        """
        return self.recognize_bytes(image_bytes, is_pdf=False)

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> PaddleOCRApiResult:
        """
        提取 PDF 中的文字

        Args:
            pdf_bytes: PDF 字节数据

        Returns:
            PaddleOCRApiResult: 识别结果
        """
        return self.recognize_bytes(pdf_bytes, is_pdf=True)
