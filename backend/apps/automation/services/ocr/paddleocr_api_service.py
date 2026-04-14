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
import logging
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
        return self._config_service.get_value("PADDLEOCR_API_MODEL", "pp_ocrv5")

    @property
    def api_url(self) -> str:
        """获取当前模型对应的 API URL"""
        url_key = _MODEL_URL_KEY_MAP.get(self.model, "PADDLEOCR_OCR_API_URL")
        return self._config_service.get_value(url_key, "")

    @property
    def api_token(self) -> str:
        """获取 API Token"""
        return self._config_service.get_value("PADDLEOCR_API_TOKEN", "")

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

            return self._parse_response(response.json(), model)

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

    def _parse_ocr_response(self, result: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """解析 OCR 端点响应（PP-OCRv5 / PP-StructureV3）"""
        ocr_results = result.get("ocrResults", [])
        all_texts: list[str] = []

        for item in ocr_results:
            pruned = item.get("prunedResult", "")
            if pruned:
                all_texts.append(pruned)

        merged = "\n".join(all_texts)
        logger.info("PaddleOCR API (OCR) 识别完成: model=%s, text_len=%d", model, len(merged))
        return PaddleOCRApiResult(text=merged, raw_texts=all_texts, model=model)

    def _parse_layout_response(self, result: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """解析版面分析端点响应（PaddleOCR-VL / VL-1.5）"""
        layout_results = result.get("layoutParsingResults", [])
        all_texts: list[str] = []

        for item in layout_results:
            markdown_data = item.get("markdown", {})
            text = markdown_data.get("text", "")
            if text:
                all_texts.append(text)

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
