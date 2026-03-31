"""Business logic services."""

import logging
import uuid
import zipfile

from apps.core.utils.path import Path
from apps.image_rotation.services import storage

logger = logging.getLogger("apps.image_rotation")


def generate_zip(*, processed_images: list[tuple[str, bytes, str]], output_dir: Path) -> str:
    zip_filename = storage.build_zip_filename()
    zip_path = output_dir / zip_filename

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            used_names: dict[str, int] = {}
            for filename, image_bytes, _img_format in processed_images:
                unique_filename = _get_unique_filename(filename, used_names)
                zf.writestr(unique_filename, image_bytes)

        logger.info(
            "ZIP 文件生成成功",
            extra={
                "zip_path": str(zip_path),
                "file_count": len(processed_images),
            },
        )
        return storage.to_media_url(zip_filename)
    except Exception:
        if zip_path.exists():
            zip_path.unlink()
        raise


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
