"""Business logic services."""

from __future__ import annotations

import io
import logging
from typing import Any, cast

from PIL import Image, ImageEnhance, ImageOps

logger = logging.getLogger(__name__)

_LANCZOS: Any = getattr(Image, "Resampling", Image).LANCZOS


class FrameSelectionService:
    def calc_dhash_hex(self, image_bytes: bytes, *, hash_size: int = 8) -> str:
        if not image_bytes:
            return ""
        if hash_size <= 0:
            return ""

        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("L")
        img = img.resize((hash_size + 1, hash_size), _LANCZOS)
        pixels = list(img.getdata())

        bits = 0
        for row in range(hash_size):
            row_start = row * (hash_size + 1)
            for col in range(hash_size):
                left = pixels[row_start + col]
                right = pixels[row_start + col + 1]
                if left > right:
                    bits |= 1 << (row * hash_size + col)

        hex_len = (hash_size * hash_size) // 4
        return f"{bits:0{hex_len}x}"

    def hamming_distance_hex(self, a: str, b: str) -> int | None:
        if not a or not b:
            return None
        try:
            x = int(a, 16)
            y = int(b, 16)
        except Exception:
            logger.exception(
                "dHash 汉明距离计算失败",
                extra={"hash_a": a, "hash_b": b},
            )
            return None
        return (x ^ y).bit_count()

    def calc_thumb_bytes(
        self,
        image_bytes: bytes,
        *,
        size: int = 48,
        crop_top_ratio: float = 0.12,
        crop_bottom_ratio: float = 0.12,
    ) -> bytes:
        if not image_bytes:
            return b""
        if size <= 0:
            return b""

        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("L")
        w, h = img.size
        if w <= 0 or h <= 0:
            return b""

        top = int(max(0, min(h - 1, round(h * float(crop_top_ratio)))))
        bottom_cut = int(max(0, min(h - 1, round(h * float(crop_bottom_ratio)))))
        bottom = max(top + 1, h - bottom_cut)
        img = img.crop((0, top, w, bottom))

        img = img.resize((size, size), _LANCZOS)
        return img.tobytes()

    def mean_abs_diff(self, a: bytes, b: bytes) -> float | None:
        if not a or not b:
            return None
        if len(a) != len(b):
            return None
        total = 0
        for x, y in zip(a, b, strict=False):
            total += x - y if x >= y else y - x
        return total / float(len(a))

    def crop_for_ocr_bytes(
        self,
        image_bytes: bytes,
        *,
        crop_top_ratio: float = 0.16,
        crop_bottom_ratio: float = 0.14,
        crop_left_ratio: float = 0.06,
        crop_right_ratio: float = 0.06,
        max_width: int = 720,
    ) -> bytes:
        cropped_bytes, _ = self.crop_for_ocr_bytes_with_range(
            image_bytes,
            crop_top_ratio=crop_top_ratio,
            crop_bottom_ratio=crop_bottom_ratio,
            crop_left_ratio=crop_left_ratio,
            crop_right_ratio=crop_right_ratio,
            max_width=max_width,
        )
        return cropped_bytes

    def crop_for_ocr_bytes_with_range(
        self,
        image_bytes: bytes,
        *,
        crop_top_ratio: float = 0.16,
        crop_bottom_ratio: float = 0.14,
        crop_left_ratio: float = 0.06,
        crop_right_ratio: float = 0.06,
        max_width: int = 720,
    ) -> tuple[bytes, int]:
        if not image_bytes:
            return (b"", 0)
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if w <= 0 or h <= 0:
            return (b"", 0)

        top = int(max(0, min(h - 1, round(h * float(crop_top_ratio)))))
        bottom_cut = int(max(0, min(h - 1, round(h * float(crop_bottom_ratio)))))
        bottom = max(top + 1, h - bottom_cut)
        left = int(max(0, min(w - 1, round(w * float(crop_left_ratio)))))
        right_cut = int(max(0, min(w - 1, round(w * float(crop_right_ratio)))))
        right = max(left + 1, w - right_cut)
        img = img.crop((left, top, right, bottom))

        if max_width and img.size[0] > max_width:
            new_w = int(max_width)
            new_h = round(img.size[1] * (new_w / float(img.size[0])))
            img = img.resize((new_w, max(1, new_h)), _LANCZOS)

        img = img.convert("L")
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(1.35)
        img = ImageEnhance.Sharpness(img).enhance(1.15)
        try:
            extrema = img.getextrema()
            if isinstance(extrema, tuple) and len(extrema) == 2:
                lo_val, hi_val = extrema
                if isinstance(lo_val, (int, float)) and isinstance(hi_val, (int, float)):
                    dynamic_range = int(hi_val) - int(lo_val)
                else:
                    dynamic_range = 0
            else:
                dynamic_range = 0
        except Exception:
            logger.exception("OCR 预处理图片动态范围计算失败")

            dynamic_range = 0

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return (buf.getvalue(), max(0, dynamic_range))
