"""
重命名专用高精度 OCR 通道

使用 SERVER 模型对正确方向的原始图片进行高精度 OCR 识别。

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 4.1, 4.2, 4.3, 4.4, 6.2
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

from PIL import Image

from .confidence_filter import ConfidenceFilter
from .preprocessor import ENHANCED_CONFIG, ImagePreprocessor, PreprocessConfig

logger = logging.getLogger("apps.image_rotation")

RETRY_CONFIDENCE_THRESHOLD = 0.6


@dataclass
class OCRResult:
    """OCR 识别结果"""

    text: str
    text_blocks: list[str]
    scores: list[float]
    overall_confidence: float


class RenameOCRChannel:
    """重命名专用高精度 OCR 通道"""

    def __init__(self) -> None:
        self._ocr: Any | None = None
        self._preprocessor = ImagePreprocessor()
        self._filter = ConfidenceFilter()
        self._init_failed = False

    def _init_ocr(self) -> Any | None:
        """延迟初始化 OCR 服务（通过 OCRService 统一路由）"""
        if self._init_failed:
            return None
        if self._ocr is not None:
            return self._ocr
        try:
            from apps.automation.services.ocr.ocr_service import OCRService

            self._ocr = OCRService(use_v5=True)
            return self._ocr
        except Exception:
            logger.warning("RenameOCRChannel: OCR 服务初始化失败", exc_info=True)
            self._init_failed = True
            return None

    def recognize(
        self,
        image_data: bytes,
        rotation: int = 0,
    ) -> OCRResult | None:
        """
        对原始图片执行高精度 OCR。

        1. 按 rotation 旋转图片到正确方向
        2. 调用 ImagePreprocessor 预处理
        3. 使用 SERVER 模型 OCR
        4. ConfidenceFilter 过滤
        5. 置信度 < 0.6 时用增强参数重试一次
        6. 返回更优结果

        初始化失败时返回 None。
        """
        ocr = self._init_ocr()
        if ocr is None:
            return None

        try:
            # 1. 旋转到正确方向
            rotated_data = self._rotate_image(image_data, rotation)

            # 2. 首次 OCR（默认预处理参数）
            first_result = self._do_ocr(ocr, rotated_data)
            retried = False

            # 3. 低置信度重试
            if first_result.overall_confidence < RETRY_CONFIDENCE_THRESHOLD:
                retry_result = self._do_ocr(
                    ocr,
                    rotated_data,
                    config=ENHANCED_CONFIG,
                )
                retried = True
                # 选择更优结果
                if retry_result.overall_confidence > first_result.overall_confidence:
                    first_result = retry_result

            logger.info(
                "RenameOCR 完成: %d 个文本块, 置信度 %.3f, 重试=%s",
                len(first_result.text_blocks),
                first_result.overall_confidence,
                retried,
            )

            return first_result

        except Exception:
            logger.warning("RenameOCRChannel: OCR 识别异常", exc_info=True)
            return None

    def _rotate_image(self, image_data: bytes, rotation: int) -> bytes:
        """按指定角度旋转图片"""
        if rotation == 0:
            return image_data

        img = Image.open(io.BytesIO(image_data))
        original_format = img.format or "PNG"

        # Pillow rotate 是逆时针，需要取反
        pillow_angle = (360 - rotation) % 360
        if pillow_angle != 0:
            img = img.rotate(pillow_angle, expand=True)  # type: ignore[assignment]

        buf = io.BytesIO()
        save_format = original_format.upper()
        if save_format in ("JPEG", "JPG"):
            if img.mode != "RGB":
                img = img.convert("RGB")  # type: ignore[assignment]
            img.save(buf, format="JPEG", quality=95)
        else:
            img.save(buf, format=save_format)

        return buf.getvalue()

    def _do_ocr(
        self,
        ocr_service: Any,
        image_data: bytes,
        config: PreprocessConfig | None = None,
    ) -> OCRResult:
        """执行一次预处理 + OCR + 过滤"""
        # 预处理
        processed = self._preprocessor.preprocess(image_data, config)

        # 通过 OCR_SERVICE 路由：paddleocr_api 走云端，local 走本地
        if ocr_service.provider == "paddleocr_api":
            return self._do_ocr_via_api(ocr_service, processed)

        # 本地 RapidOCR 引擎
        engine = ocr_service.ocr
        result = engine(processed)

        if not result or not result.txts or not result.scores:
            return OCRResult(
                text="",
                text_blocks=[],
                scores=[],
                overall_confidence=0.0,
            )

        # 置信度过滤
        filter_result = self._filter.filter(
            list(result.txts),
            list(result.scores),
        )

        text = "\n".join(filter_result.texts)

        return OCRResult(
            text=text,
            text_blocks=filter_result.texts,
            scores=filter_result.scores,
            overall_confidence=filter_result.overall_confidence,
        )

    def _do_ocr_via_api(
        self,
        ocr_service: Any,
        image_data: bytes,
    ) -> OCRResult:
        """通过 PaddleOCR API 执行 OCR"""
        try:
            api_result = ocr_service.paddleocr_engine.recognize_bytes(image_data, is_pdf=False)
            texts = api_result.raw_texts
            # API 不提供逐行置信度，默认设为 1.0
            scores = [1.0] * len(texts)

            # 置信度过滤（scores 都是 1.0 不会过滤内容，但保持流程一致）
            filter_result = self._filter.filter(texts, scores)

            text = "\n".join(filter_result.texts)

            return OCRResult(
                text=text,
                text_blocks=filter_result.texts,
                scores=filter_result.scores,
                overall_confidence=filter_result.overall_confidence,
            )
        except Exception as e:
            logger.warning("RenameOCRChannel: PaddleOCR API 失败: %s", e)
            return OCRResult(
                text="",
                text_blocks=[],
                scores=[],
                overall_confidence=0.0,
            )
