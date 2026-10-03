"""Business logic services."""

from __future__ import annotations

import io
import logging
import uuid
import zipfile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.image_rotation.services import storage

logger = logging.getLogger("apps.image_rotation")


def generate_zip(*, processed_images: list[tuple[str, bytes, str]]) -> str:  # pragma: no cover
    zip_filename = storage.build_zip_filename()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        used_names: dict[str, int] = {}
        for filename, image_bytes, _img_format in processed_images:
            unique_filename = _get_unique_filename(filename, used_names)
            zf.writestr(unique_filename, image_bytes)

    rel_path = storage.export_rel_path(zip_filename)
    default_storage.save(rel_path, ContentFile(buffer.getvalue()))

    logger.info(
        "ZIP 文件生成成功",
        extra={
            "rel_path": rel_path,
            "file_count": len(processed_images),
        },
    )
    return storage.to_media_url(zip_filename)


def _get_unique_filename(filename: str, used_names: dict[str, int]) -> str:
    if not filename:
        filename = f"image_{uuid.uuid4().hex[:8]}.jpg"

    if filename not in used_names:
        used_names[filename] = 1
        return filename

    name_parts = filename.rsplit(".", 1)
    if len(name_parts) == 2:
        base_name, ext = name_parts
    else:
        base_name = filename
        ext = ""

    count = used_names[filename]
    used_names[filename] = count + 1

    if ext:
        return f"{base_name}_{count}.{ext}"
    return f"{base_name}_{count}"
