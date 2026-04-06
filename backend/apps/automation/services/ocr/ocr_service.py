"""Business logic services."""

from __future__ import annotations

"""
OCR 服务 - 基于 PP-OCRv5 Server 模型

提供高精度的文字识别能力,支持:
- 简体中文、繁体中文、英文、日文、拼音
- 手写体、竖排文字、生僻字

使用 rapidocr>=3.4.5,模型会自动下载.
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
    获取 OCR 引擎实例(单例模式)

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


class OCRService:
    """OCR 服务类"""

    def __init__(self, use_v5: bool = True) -> None:
        """
        初始化 OCR 服务

        Args:
            use_v5: 是否使用 PP-OCRv5 模型(默认 True)
        """
        self.use_v5 = use_v5
        self._ocr = None

    @property
    def ocr(self) -> Any:
        """懒加载 OCR 引擎"""
        if self._ocr is None:
            self._ocr = get_ocr_engine(self.use_v5)
        return self._ocr

    def recognize(self, image_path: str) -> str:
        """
        识别图片中的文字

        Args:
            image_path: 图片路径

        Returns:
            识别出的文字内容
        """
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
        result = self.ocr(image_path)
        if result and result.boxes is not None:
            # 转换为旧格式兼容
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
