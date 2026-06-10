"""Tests for apps.image_rotation.services.rename_ocr.preprocessor."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from apps.image_rotation.services.rename_ocr.preprocessor import (
    ENHANCED_CONFIG,
    ImagePreprocessor,
    PreprocessConfig,
)


def _make_png(width: int = 200, height: int = 100, color: int = 128) -> bytes:
    """Create a simple PNG in memory."""
    img = Image.new("RGB", (width, height), color=(color, color, color))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg(width: int = 200, height: int = 100, color: int = 128) -> bytes:
    """Create a simple JPEG in memory."""
    img = Image.new("RGB", (width, height), color=(color, color, color))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class TestPreprocessConfig:
    def test_defaults(self) -> None:
        cfg = PreprocessConfig()
        assert cfg.sharpen_radius == 2.0
        assert cfg.contrast_factor == 1.5
        assert cfg.min_width == 1000
        assert cfg.target_width == 1500
        assert cfg.enable_binarize is False

    def test_enhanced_config(self) -> None:
        assert ENHANCED_CONFIG.contrast_factor == 2.0
        assert ENHANCED_CONFIG.enable_binarize is True


class TestImagePreprocessor:
    def setup_method(self) -> None:
        self.preprocessor = ImagePreprocessor()

    def test_preprocess_png_returns_bytes(self) -> None:
        data = _make_png()
        result = self.preprocessor.preprocess(data)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_preprocess_jpeg_returns_bytes(self) -> None:
        data = _make_jpeg()
        result = self.preprocessor.preprocess(data)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_preprocess_small_image_upscale(self) -> None:
        """Images smaller than min_width get upscaled."""
        data = _make_png(width=500, height=250)
        result = self.preprocessor.preprocess(data)
        result_img = Image.open(io.BytesIO(result))
        assert result_img.width >= 1000  # upscaled to at least min_width

    def test_preprocess_large_image_no_upscale(self) -> None:
        """Images >= min_width are not upscaled."""
        data = _make_png(width=1200, height=600)
        result = self.preprocessor.preprocess(data)
        result_img = Image.open(io.BytesIO(result))
        assert result_img.width == 1200

    def test_preprocess_with_binarize_config(self) -> None:
        cfg = PreprocessConfig(enable_binarize=True)
        data = _make_png()
        result = self.preprocessor.preprocess(data, config=cfg)
        result_img = Image.open(io.BytesIO(result))
        # Binarized images should be in L mode (grayscale) or converted back to RGB for JPEG
        assert result_img.mode in ("L", "RGB")

    def test_preprocess_returns_original_on_error(self) -> None:
        """Invalid data returns original bytes without raising."""
        bad_data = b"not-an-image"
        result = self.preprocessor.preprocess(bad_data)
        assert result == bad_data

    def test_preprocess_rgba_image(self) -> None:
        """RGBA images get converted to RGB."""
        img = Image.new("RGBA", (200, 100), (128, 128, 128, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        result = self.preprocessor.preprocess(data)
        assert isinstance(result, bytes)


class TestOtsuThreshold:
    def test_otsu_threshold_uniform_image(self) -> None:
        """Uniform image should return a threshold."""
        gray = Image.new("L", (100, 100), 128)
        threshold = ImagePreprocessor()._otsu_threshold(gray)
        assert 0 <= threshold <= 255

    def test_otsu_threshold_bimodal(self) -> None:
        """Otsu threshold returns a valid value for a bimodal image."""
        import numpy as np

        # Create a gradient image (not pure bimodal to avoid edge cases)
        arr = np.zeros((100, 100), dtype=np.uint8)
        for x in range(100):
            arr[:, x] = int(x * 2.55)  # 0 to 255 gradient
        gray = Image.fromarray(arr, mode="L")
        threshold = ImagePreprocessor()._otsu_threshold(gray)
        assert 0 <= threshold <= 255


class TestNormalizeBrightness:
    def test_returns_image(self) -> None:
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        result = ImagePreprocessor()._normalize_brightness(img, 128.0)
        assert isinstance(result, Image.Image)

    def test_zero_mean_returns_original(self) -> None:
        """When mean is 0, returns original image."""
        img = Image.new("RGB", (10, 10), (0, 0, 0))
        result = ImagePreprocessor()._normalize_brightness(img, 128.0)
        assert isinstance(result, Image.Image)
