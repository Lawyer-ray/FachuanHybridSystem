"""Business logic services."""

import base64
import io
import logging
from typing import Any

from PIL import Image

logger = logging.getLogger("apps.automation.image_rotation")


class OrientationDetectionService:
    """
    图片方向检测服务

    使用四方向 OCR 投票法检测图片方向:
    对图片分别做 0°/90°/180°/270° 旋转,用 RapidOCR 识别,
    哪个方向识别出的文字置信度最高就是正确方向.
    """

    def __init__(self) -> None:
        self._ocr = None

    @property
    def ocr(self) -> None:
        if self._ocr is None:
            try:
                from rapidocr import ModelType, OCRVersion, RapidOCR

                self._ocr = RapidOCR(
                    params={
                        "Det.ocr_version": OCRVersion.PPOCRV5,
                        "Det.model_type": ModelType.MOBILE,
                        "Rec.model_type": ModelType.MOBILE,
                    }
                )
            except ImportError:
                logger.warning("rapidocr 未安装")
                return None
        return self._ocr

    def detect_orientation(self, image_data: bytes) -> dict[str, Any]:
        if not self.ocr:
            return {
                "rotation": 0,
                "confidence": 0,
                "method": "none",
                "error": "OCR 引擎未初始化",
            }

        try:
            img = Image.open(io.BytesIO(image_data))

            scores: dict[int, float] = {}
            rotations: list[Any] = [0, 90, 180, 270]

            for rotation in rotations:
                if rotation == 0:
                    rotated_img = img
                else:
                    pillow_angle = (360 - rotation) % 360
                    rotated_img = img.rotate(pillow_angle, expand=True)

                img_bytes = io.BytesIO()
                rotated_img.save(img_bytes, format="JPEG", quality=85)
                img_bytes_data = img_bytes.getvalue()

                result = self.ocr(img_bytes_data)

                if result and result.txts and result.scores:
                    text_count = len(result.txts)
                    avg_confidence = sum(result.scores) / len(result.scores)
                    score = text_count * avg_confidence
                else:
                    score = 0

                scores[rotation] = score
                logger.debug(f"方向 {rotation}°: 得分={score:.2f}")

            best_rotation = max(scores, key=scores.get)
            best_score = scores[best_rotation]
            total_score = sum(scores.values())

            confidence = best_score / total_score if total_score > 0 else 0

            MIN_SCORE_THRESHOLD = 10.0
            if best_score < MIN_SCORE_THRESHOLD:
                logger.info(f"方向检测完成: 得分过低 ({best_score:.2f} < {MIN_SCORE_THRESHOLD}),保持原方向", extra={})
                return {
                    "rotation": 0,
                    "confidence": 0,
                    "method": "ocr_voting_low_score",
                    "scores": scores,
                    "reason": f"最高得分 {best_score:.2f} 低于阈值 {MIN_SCORE_THRESHOLD}",
                }

            logger.info(f"方向检测完成: 最佳方向={best_rotation}°, 置信度={confidence:.2f}", extra={})

            return {
                "rotation": best_rotation,
                "confidence": round(confidence, 2),
                "method": "ocr_voting",
                "scores": scores,
            }
        except Exception as e:
            logger.warning(f"图片方向检测失败: {e}")
            return {
                "rotation": 0,
                "confidence": 0,
                "method": "none",
                "error": str(e),
            }

    def detect_orientation_with_text(self, image_data: bytes) -> dict[str, Any]:
        if not self.ocr:
            return {
                "rotation": 0,
                "confidence": 0,
                "method": "none",
                "error": "OCR 引擎未初始化",
                "ocr_text": "",
            }

        try:
            img = Image.open(io.BytesIO(image_data))

            scores: dict[int, float] = {}
            texts: dict[int, str] = {}
            rotations: list[Any] = [0, 90, 180, 270]

            for rotation in rotations:
                if rotation == 0:
                    rotated_img = img
                else:
                    pillow_angle = (360 - rotation) % 360
                    rotated_img = img.rotate(pillow_angle, expand=True)

                img_bytes = io.BytesIO()
                rotated_img.save(img_bytes, format="JPEG", quality=85)
                img_bytes_data = img_bytes.getvalue()

                result = self.ocr(img_bytes_data)

                if result and result.txts and result.scores:
                    text_count = len(result.txts)
                    avg_confidence = sum(result.scores) / len(result.scores)
                    score = text_count * avg_confidence
                    texts[rotation] = "\n".join(result.txts)
                else:
                    score = 0
                    texts[rotation] = ""

                scores[rotation] = score
                logger.debug(f"方向 {rotation}°: 得分={score:.2f}")

            best_rotation = max(scores, key=scores.get)
            best_score = scores[best_rotation]
            total_score = sum(scores.values())
            confidence = best_score / total_score if total_score > 0 else 0
            ocr_text = texts.get(best_rotation, "")

            MIN_SCORE_THRESHOLD = 10.0
            if best_score < MIN_SCORE_THRESHOLD:
                logger.info(f"方向检测完成: 得分过低 ({best_score:.2f} < {MIN_SCORE_THRESHOLD}),保持原方向", extra={})
                return {
                    "rotation": 0,
                    "confidence": 0,
                    "method": "ocr_voting_low_score",
                    "scores": scores,
                    "reason": f"最高得分 {best_score:.2f} 低于阈值 {MIN_SCORE_THRESHOLD}",
                    "ocr_text": texts.get(0, ""),
                }

            logger.info(f"方向检测完成: 最佳方向={best_rotation}°, 置信度={confidence:.2f}", extra={})

            return {
                "rotation": best_rotation,
                "confidence": round(confidence, 2),
                "method": "ocr_voting",
                "scores": scores,
                "ocr_text": ocr_text,
            }
        except Exception as e:
            logger.warning(f"图片方向检测失败: {e}")
            return {
                "rotation": 0,
                "confidence": 0,
                "method": "none",
                "error": str(e),
                "ocr_text": "",
            }

    def detect_batch(self, images: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[Any] = []
        for img_item in images:
            try:
                data = img_item.get("data", "")
                if "," in data:
                    data = data.split(",", 1)[1]
                image_bytes = base64.b64decode(data)

                result = self.detect_orientation_with_text(image_bytes)
                result["filename"] = img_item.get("filename", "")
                results.append(result)
            except Exception as e:
                logger.exception("操作失败")
                results.append(
                    {
                        "filename": img_item.get("filename", ""),
                        "rotation": 0,
                        "confidence": 0,
                        "error": str(e),
                        "ocr_text": "",
                    }
                )
        return results
