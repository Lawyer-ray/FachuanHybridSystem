"""Business logic services."""

import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)


def remove_exif_orientation(image: Image.Image, *, exif_orientation_tag: int) -> Image.Image:
    try:
        exif = image.getexif()
        if not exif:
            return image

        orientation = exif.get(exif_orientation_tag)
        if not orientation or orientation == 1:
            return image

        if image.mode == "RGBA":
            new_image = Image.new("RGBA", image.size)
        else:
            new_image = Image.new("RGB", image.size)
        new_image.paste(image)
        return new_image
    except Exception as e:
        logger.warning(f"移除 EXIF 方向标签失败: {e}")
        return image


def clean_image(image_data: bytes, *, img_format: str, exif_orientation_tag: int) -> bytes:
    img = Image.open(io.BytesIO(image_data))
    img = remove_exif_orientation(img, exif_orientation_tag=exif_orientation_tag)

    output = io.BytesIO()
    fmt = (img_format or "jpeg").upper()

    if fmt == "JPEG":
        if img.mode in ("RGBA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(output, format="JPEG", quality=95, optimize=True)
    else:
        img.save(output, format=fmt)

    return output.getvalue()


def resize_to_paper_size(
    image_bytes: bytes,
    *,
    paper_size: str,
    paper_sizes: dict[str, tuple[int, int]],
    dpi: int = 300,
) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    width, height = img.size

    target_width_mm, target_height_mm = paper_sizes[paper_size]
    target_width = int(target_width_mm * dpi / 25.4)
    target_height = int(target_height_mm * dpi / 25.4)

    target_ratio = target_width / target_height
    img_ratio = width / height

    if img_ratio > target_ratio:
        new_width = target_width
        new_height = int(target_width / img_ratio)
    else:
        new_height = target_height
        new_width = int(target_height * img_ratio)

    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    background = Image.new("RGB", (target_width, target_height), (255, 255, 255))
    x = (target_width - new_width) // 2
    y = (target_height - new_height) // 2
    background.paste(img, (x, y))

    output = io.BytesIO()
    background.save(output, format="JPEG", quality=95)
    return output.getvalue()


def rotate_image_for_output(image_data: bytes, *, rotation: int, img_format: str) -> bytes:
    if rotation not in (0, 90, 180, 270):
        rotation = 0

    img = Image.open(io.BytesIO(image_data))
    pillow_angle = (360 - rotation) % 360
    if pillow_angle != 0:
        img = img.rotate(pillow_angle, expand=True)

    output = io.BytesIO()
    fmt = (img_format or "jpeg").upper()

    if fmt == "JPEG":
        if img.mode in ("RGBA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(output, format="JPEG", quality=95, optimize=True)
    else:
        img.save(output, format=fmt)

    return output.getvalue()
