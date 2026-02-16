"""Business logic services."""

import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)


def apply_rotation_for_pdf(image_bytes: bytes, rotation: int) -> bytes:
    if rotation not in (0, 90, 180, 270):
        rotation = 0

    if rotation == 0:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            if img.format == "JPEG":
                return image_bytes
            output = io.BytesIO()
            img = _ensure_rgb(img)  # type: ignore[assignment]
            img.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue()
        except Exception:
            logger.exception("操作失败")

            return image_bytes

    try:
        img = Image.open(io.BytesIO(image_bytes))
        pillow_angle = (360 - rotation) % 360
        if pillow_angle != 0:
            img = img.rotate(pillow_angle, expand=True)  # type: ignore[assignment]

        output = io.BytesIO()
        img = _ensure_rgb(img)  # type: ignore[assignment]
        img.save(output, format="JPEG", quality=85, optimize=True)
        return output.getvalue()
    except Exception as e:
        logger.warning(f"图片旋转失败,使用原始图片: {e}")
        return image_bytes


def _ensure_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "RGBA":
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img)
        return background
    if img.mode != "RGB":
        return img.convert("RGB")
    return img
