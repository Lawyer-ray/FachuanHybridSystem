"""
图片预处理器

在 OCR 识别前对图片进行增强处理（锐化、对比度、亮度、二值化、放大）。

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 4.1, 6.1
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger("apps.image_rotation")


@dataclass
class PreprocessConfig:
    """预处理配置参数"""

    sharpen_radius: float = 2.0
    sharpen_percent: int = 150
    sharpen_threshold: int = 3
    contrast_factor: float = 1.5
    brightness_target: float = 128.0
    min_width: int = 1000
    target_width: int = 1500
    enable_binarize: bool = False


ENHANCED_CONFIG = PreprocessConfig(
    contrast_factor=2.0,
    enable_binarize=True,
)


class ImagePreprocessor:
    """图片预处理器 - OCR 前的图片增强"""

    def preprocess(
        self,
        image_data: bytes,
        config: PreprocessConfig | None = None,
    ) -> bytes:
        """
        对图片执行预处理增强，返回增强后的图片字节数据。

        处理流程：锐化 → 对比度增强 → 亮度归一化 → 条件放大 → 可选二值化
        异常时记录警告日志并返回原始数据。
        """
        cfg = config or PreprocessConfig()
        steps: list[str] = []

        try:
            img = Image.open(io.BytesIO(image_data))
            original_format = img.format or "PNG"
            original_size = img.size

            # 转为 RGB 处理
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")  # type: ignore[assignment]

            # 1. 自适应锐化 (UnsharpMask)
            img = img.filter(  # type: ignore[assignment]
                ImageFilter.UnsharpMask(
                    radius=cfg.sharpen_radius,
                    percent=cfg.sharpen_percent,
                    threshold=cfg.sharpen_threshold,
                )
            )
            steps.append("sharpen")

            # 2. 对比度增强
            img = ImageEnhance.Contrast(img).enhance(cfg.contrast_factor)  # type: ignore[assignment]
            steps.append("contrast")

            # 3. 亮度归一化
            img = self._normalize_brightness(img, cfg.brightness_target)  # type: ignore[assignment]
            steps.append("brightness")

            # 4. 条件放大
            width, height = img.size
            if width < cfg.min_width:
                ratio = cfg.target_width / width
                new_height = int(height * ratio)
                img = img.resize(  # type: ignore[assignment]
                    (cfg.target_width, new_height),
                    Image.Resampling.LANCZOS,
                )
                steps.append("upscale")

            # 5. 可选二值化
            if cfg.enable_binarize:
                img = self._binarize(img)  # type: ignore[assignment]
                steps.append("binarize")

            # 输出为原始格式
            buf = io.BytesIO()
            save_format = original_format.upper()
            if save_format == "JPEG" or save_format == "JPG":
                # 二值化后的图片可能是 L 模式，JPEG 不支持 RGBA
                if img.mode == "L":
                    img = img.convert("RGB")  # type: ignore[assignment]
                img.save(buf, format="JPEG", quality=95)
            else:
                img.save(buf, format=save_format)

            logger.info(
                "图片预处理完成: %s -> %s, 步骤: %s",
                original_size,
                img.size,
                ", ".join(steps),
            )

            return buf.getvalue()

        except Exception:
            logger.warning("图片预处理异常, 返回原始数据", exc_info=True)
            return image_data

    def _normalize_brightness(
        self,
        img: Image.Image,
        target: float,
    ) -> Image.Image:
        """亮度归一化"""
        import numpy as np

        arr = np.array(img, dtype=np.float64)
        current_mean = float(arr.mean())
        if current_mean == 0:
            return img
        factor = target / current_mean
        return ImageEnhance.Brightness(img).enhance(factor)

    def _binarize(self, img: Image.Image) -> Image.Image:
        """自适应二值化"""
        gray = img.convert("L")
        threshold = self._otsu_threshold(gray)
        return gray.point(lambda x: 255 if x > threshold else 0, "L")

    def _otsu_threshold(self, gray_img: Image.Image) -> int:
        """Otsu 自适应阈值"""
        import numpy as np

        arr = np.array(gray_img, dtype=np.uint8)
        hist = np.bincount(arr.ravel(), minlength=256).astype(np.float64)
        total = arr.size
        hist_norm = hist / total

        cumsum = np.cumsum(hist_norm)
        cum_mean = np.cumsum(hist_norm * np.arange(256))
        global_mean = cum_mean[-1]

        best_threshold = 0
        best_variance = 0.0

        for t in range(256):
            w0 = cumsum[t]
            w1 = 1.0 - w0
            if w0 == 0 or w1 == 0:
                continue
            mean0 = cum_mean[t] / w0
            mean1 = (global_mean - cum_mean[t]) / w1
            variance = w0 * w1 * (mean0 - mean1) ** 2
            if variance > best_variance:
                best_variance = variance
                best_threshold = t

        return best_threshold
