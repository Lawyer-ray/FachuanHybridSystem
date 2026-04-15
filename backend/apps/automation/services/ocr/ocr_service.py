"""Business logic services."""

from __future__ import annotations

"""
OCR 服务 - 统一路由层

根据 SystemConfig 中的 OCR_PROVIDER 配置，自动路由到：
- local: 本地 RapidOCR 引擎（默认）
- paddleocr_api: 百度 PaddleOCR API 云端引擎

同时支持 PP-OCRv5 Server 模型，提供高精度的文字识别能力。
"""

import io
import logging
import re
from dataclasses import dataclass
from typing import Any

from PIL import Image


@dataclass(frozen=True)
class OCRTextResult:
    """OCR 文本识别结果"""

    text: str  # 合并后的文本(用 | 分隔)
    raw_texts: list[str]  # 原始文本列表


logger = logging.getLogger(__name__)

# 全局 OCR 引擎实例缓存(按模型档位区分,避免 fast/accurate 串用同一引擎)
_ocr_engine_cache: dict[bool, Any] = {}


def get_ocr_engine(use_v5: bool = True) -> Any:
    """
    获取本地 OCR 引擎实例(单例模式)

    Args:
        use_v5: 是否使用 PP-OCRv5 模型(默认 True)

    Returns:
        RapidOCR 实例
    """
    global _ocr_engine_cache

    # 第三方 OCR 库日志较多（模型路径/加载细节），统一压到 WARNING 并关闭传播
    for logger_name in ("RapidOCR", "rapidocr", "onnxruntime"):
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.setLevel(logging.WARNING)
        third_party_logger.propagate = False

    if use_v5 in _ocr_engine_cache:
        return _ocr_engine_cache[use_v5]

    from rapidocr import ModelType, OCRVersion, RapidOCR

    if use_v5:
        # 使用 PP-OCRv5 server 模型(精度更高)
        logger.info("初始化 RapidOCR 引擎 (PP-OCRv5 server)")
        _ocr_engine_cache[use_v5] = RapidOCR(
            params={
                "Det.ocr_version": OCRVersion.PPOCRV5,
                "Det.model_type": ModelType.SERVER,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_type": ModelType.SERVER,
            }
        )
    else:
        # 使用默认 PP-OCRv4 模型
        logger.info("初始化 RapidOCR 引擎 (PP-OCRv4)")
        _ocr_engine_cache[use_v5] = RapidOCR()

    return _ocr_engine_cache[use_v5]


def _get_ocr_provider() -> str:
    """从 SystemConfig 获取 OCR 提供者"""
    from apps.core.services.system_config_service import SystemConfigService

    return str(SystemConfigService().get_value("OCR_PROVIDER", "local") or "local")


class OCRService:
    """OCR 服务类 - 统一路由层"""

    def __init__(self, use_v5: bool = True, provider: str | None = None) -> None:
        """
        初始化 OCR 服务

        Args:
            use_v5: 是否使用 PP-OCRv5 模型(默认 True)，仅本地模式生效
            provider: OCR 引擎选择，None 时从 SystemConfig 读取
        """
        self.use_v5 = use_v5
        self._provider = provider
        self._ocr: Any | None = None
        self._paddleocr_engine: Any | None = None

    @property
    def provider(self) -> str:
        """获取当前 OCR 提供者"""
        return self._provider or _get_ocr_provider()

    @property
    def ocr(self) -> Any:
        """懒加载本地 OCR 引擎"""
        if self._ocr is None:
            self._ocr = get_ocr_engine(self.use_v5)
        return self._ocr

    @property
    def paddleocr_engine(self) -> Any:
        """懒加载 PaddleOCR API 引擎"""
        if self._paddleocr_engine is None:
            from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

            self._paddleocr_engine = PaddleOCRApiEngine()
        return self._paddleocr_engine

    def recognize(self, image_path: str) -> str:
        """
        识别图片中的文字

        Args:
            image_path: 图片路径

        Returns:
            识别出的文字内容
        """
        if self.provider == "paddleocr_api":
            return self._recognize_via_paddleocr_path(image_path)

        result = self.ocr(image_path)
        if result and result.txts:
            return "\n".join(result.txts)
        return ""

    def recognize_with_boxes(self, image_path: str) -> tuple[list[list[Any]] | None, list[float] | None]:
        """
        识别图片中的文字,返回带位置信息的结果

        Args:
            image_path: 图片路径

        Returns:
            (结果列表, 置信度列表)
            结果列表格式: [[box, text, score], ...]
        """
        if self.provider == "paddleocr_api":
            logger.warning("PaddleOCR API 模式不支持带位置信息的识别，降级到本地 RapidOCR")
            # 降级到本地引擎
            result = self.ocr(image_path)
        else:
            result = self.ocr(image_path)

        if result and result.boxes is not None:
            boxes_with_text: list[Any] = []
            for _i, (box, txt, score) in enumerate(zip(result.boxes, result.txts, result.scores, strict=False)):
                boxes_with_text.append([box, txt, score])
            return boxes_with_text, list(result.scores)
        return None, None

    def recognize_bytes(self, image_bytes: bytes) -> str:
        """
        识别图片字节数据中的文字

        Args:
            image_bytes: 图片字节数据

        Returns:
            识别出的文字内容
        """
        if self.provider == "paddleocr_api":
            return self._recognize_via_paddleocr_bytes(image_bytes)

        result = self.ocr(image_bytes)
        if result and result.txts:
            return "\n".join(result.txts)
        return ""

    def _recognize_via_paddleocr_path(self, image_path: str) -> str:
        """通过 PaddleOCR API 识别图片文件"""
        try:
            from pathlib import Path

            file_bytes = Path(image_path).read_bytes()
            is_pdf = image_path.lower().endswith(".pdf")
            api_result = self.paddleocr_engine.recognize_bytes(file_bytes, is_pdf=is_pdf)
            return str(api_result.text)
        except Exception as e:
            logger.warning("PaddleOCR API 调用失败，降级到本地 RapidOCR: %s", e)
            # 降级到本地
            result = self.ocr(image_path)
            if result and result.txts:
                return "\n".join(result.txts)
            return ""

    def _recognize_via_paddleocr_bytes(self, image_bytes: bytes) -> str:
        """通过 PaddleOCR API 识别图片字节数据"""
        try:
            api_result = self.paddleocr_engine.recognize_bytes(image_bytes, is_pdf=False)
            return str(api_result.text)
        except Exception as e:
            logger.warning("PaddleOCR API 调用失败，降级到本地 RapidOCR: %s", e)
            # 降级到本地
            result = self.ocr(image_bytes)
            if result and result.txts:
                return "\n".join(result.txts)
            return ""

    def _to_list(self, x: Any) -> list[Any]:
        """将 OCR 结果转换为列表"""
        if x is None:
            return []
        try:
            tolist = getattr(x, "tolist", None)
            if callable(tolist):
                result: list[Any] = tolist()
                return result
        except Exception:
            logger.exception("操作失败")
            pass
        try:
            return list(x)
        except Exception:
            logger.exception("操作失败")
            return [x]

    def _get_position_key(self, box: Any) -> tuple[Any, ...]:
        """
        获取文本框的位置排序键

        按 y 坐标分行(每 12 像素一行),再按 x 坐标排序(每 8 像素一列)
        """
        if not box:
            return (0.0, 0.0)
        ys: list[Any] = []
        xs: list[Any] = []
        y = min(ys) if ys else 0
        x = min(xs) if xs else 0
        return (int(y) // 12, int(x) // 8)

    def _is_timestamp_text(self, text: str) -> bool:
        """
        判断是否为时间戳文本

        过滤以下格式:
        - HH:MM(如 12:30)
        - YYYY-MM-DD 或 YYYY/MM/DD
        - MM月DD日
        """
        if re.match(r"^\d{1,2}:\d{2}$", text):
            return True
        if re.match(r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,2}$", text):
            return True
        if re.match(r"^\d{1,2}月\d{1,2}日$", text):
            return True
        return False

    def extract_text(self, image_bytes: bytes) -> OCRTextResult:
        """
        提取图片中的文字(带清洗和排序)

        从 chat_records 版本移植,包含:
        - 按位置排序(先按 y 坐标分行,再按 x 坐标排序)
        - 过滤低置信度结果(< 0.50)
        - 过滤时间戳文本(如 HH:MM、日期格式)

        Args:
            image_bytes: 图片字节数据

        Returns:
            OCRTextResult: 包含合并文本和原始文本列表
        """
        if not image_bytes:
            return OCRTextResult(text="", raw_texts=[])

        # PaddleOCR API 模式：直接调用 API 获取文本
        if self.provider == "paddleocr_api":
            return self._extract_text_via_paddleocr(image_bytes)

        return self._extract_text_local(image_bytes)

    def _extract_text_local(self, image_bytes: bytes) -> OCRTextResult:
        """本地 RapidOCR 提取文字（带清洗和排序）"""
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            result = self.ocr(img)

            txts = self._to_list(getattr(result, "txts", None))
            boxes = self._to_list(getattr(result, "boxes", None))
            scores = self._to_list(getattr(result, "scores", None))

            # 按位置排序
            indices = list(range(len(txts)))
            if boxes and len(boxes) == len(txts):
                indices.sort(key=lambda i: self._get_position_key(boxes[i]))

            # 清洗文本
            cleaned: list[str] = []
            for i in indices:
                t = (txts[i] or "").strip()
                if not t:
                    continue

                # 过滤低置信度
                if scores and i < len(scores):
                    try:
                        if float(scores[i]) < 0.50:
                            continue
                    except Exception:
                        logger.exception("操作失败")

                        pass

                # 移除空白字符
                t = re.sub(r"\s+", "", t)

                # 过滤时间戳文本
                if self._is_timestamp_text(t):
                    continue

                cleaned.append(t)

            merged = "|".join(cleaned)
            return OCRTextResult(text=merged, raw_texts=cleaned)
        except Exception as e:
            logger.warning("RapidOCR 识别失败", extra={"error": str(e)}, exc_info=True)
            return OCRTextResult(text="", raw_texts=[])

    def _extract_text_via_paddleocr(self, image_bytes: bytes) -> OCRTextResult:
        """通过 PaddleOCR API 提取文字"""
        try:
            api_result = self.paddleocr_engine.recognize_bytes(image_bytes, is_pdf=False)
            # 清洗文本（与本地模式一致）
            cleaned: list[str] = []
            for line in api_result.text.split("\n"):
                t = line.strip()
                if not t:
                    continue
                t = re.sub(r"\s+", "", t)
                if self._is_timestamp_text(t):
                    continue
                cleaned.append(t)

            merged = "|".join(cleaned)
            return OCRTextResult(text=merged, raw_texts=cleaned)
        except Exception as e:
            logger.warning("PaddleOCR API 识别失败，降级到本地 RapidOCR: %s", e)
            return self._extract_text_local(image_bytes)
