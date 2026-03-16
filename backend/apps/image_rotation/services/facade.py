"""Business logic services."""

from __future__ import annotations

import logging
import uuid
from typing import Any, ClassVar

from apps.core.exceptions import ValidationException

from . import storage, validation
from .export import generate_pdf, generate_zip
from .transform import clean_image, resize_to_paper_size

logger = logging.getLogger("apps.image_rotation")


class ImageRotationService:
    SUPPORTED_FORMATS: ClassVar = {"jpeg", "jpg", "png"}
    MAX_FILE_SIZE = 20 * 1024 * 1024

    EXIF_ORIENTATION_TAG = 0x0112

    PAPER_SIZES: ClassVar = {
        "original": None,
        "a4": (210, 297),
        "a3": (297, 420),
        "letter": (216, 279),
    }

    DEFAULT_DPI = 150

    def export_images(
        self,
        images: list[dict[str, Any]],
        paper_size: str = "original",
        rename_map: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not images:
            return {"success": False, "message": "没有图片需要导出"}

        processed_images, errors = self._process_all_images(images, paper_size, rename_map)

        if not processed_images:
            return {"success": False, "message": "所有图片处理失败", "errors": errors}

        try:
            output_dir = self._get_output_dir()
            zip_url = generate_zip(processed_images=processed_images, output_dir=output_dir)
            result: dict[str, Any] = {"success": True, "zip_url": zip_url}
            if errors:
                result["warnings"] = errors
            return result
        except Exception as e:
            logger.error(f"ZIP 生成失败: {e}", exc_info=True)
            return {"success": False, "message": f"ZIP 生成失败: {e!s}"}

    def _process_all_images(
        self,
        images: list[dict[str, Any]],
        paper_size: str,
        rename_map: dict[str, str] | None,
    ) -> tuple[list[tuple[str, bytes, str]], list[str]]:
        """处理所有图片,返回 (processed_images, errors)"""
        processed_images: list[tuple[str, bytes, str]] = []
        errors: list[str] = []

        for idx, image_item in enumerate(images):
            try:
                result = self._process_single_image(image_item, paper_size)
                if result:
                    filename, image_bytes, img_format = result
                    if rename_map and filename in rename_map and rename_map[filename]:
                        filename = rename_map[filename]
                    processed_images.append((filename, image_bytes, img_format))
            except ValidationException as e:
                errors.append(f"{image_item.get('filename', f'图片{idx + 1}')}: {e.message}")
            except Exception as e:
                logger.error(f"处理图片失败: {e}", extra={"filename": image_item.get("filename")}, exc_info=True)
                errors.append(f"{image_item.get('filename', f'图片{idx + 1}')}: 处理失败")

        return processed_images, errors

    def export_as_pdf(self, pages: list[dict[str, Any]], paper_size: str = "original") -> dict[str, Any]:
        if not pages:
            return {"success": False, "message": "没有页面需要导出"}

        processed_images: list[tuple[bytes, int]] = []
        errors: list[str] = []

        for idx, page_item in enumerate(pages):
            try:
                page_result = self._process_page_for_pdf(page_item, paper_size)
                if page_result:
                    processed_images.append(page_result)
            except ValidationException as e:
                errors.append(f"{page_item.get('filename', f'页面{idx + 1}')}: {e.message}")
            except Exception as e:
                logger.error(
                    f"处理页面失败: {e}",
                    extra={},
                    exc_info=True,
                )
                errors.append(f"{page_item.get('filename', f'页面{idx + 1}')}: 处理失败")

        if not processed_images:
            return {"success": False, "message": "所有页面处理失败", "errors": errors}

        try:
            output_dir = self._get_output_dir()
            pdf_url = generate_pdf(processed_images=processed_images, output_dir=output_dir)
            result = {"success": True, "pdf_url": pdf_url}
            if errors:
                result["warnings"] = errors
            return result
        except Exception as e:
            logger.error(f"PDF 生成失败: {e}", exc_info=True)
            return {"success": False, "message": f"PDF 生成失败: {e!s}"}

    def _process_single_image(
        self, image_item: dict[str, Any], paper_size: str = "original"
    ) -> tuple[str, bytes, str] | None:
        filename = image_item.get("filename", "")
        data = image_item.get("data", "")
        img_format = image_item.get("format", "jpeg")

        normalized_format = validation.validate_image_format(
            img_format=img_format,
            supported_formats=self.SUPPORTED_FORMATS,
        )

        image_bytes = validation.decode_base64_payload(data)
        validation.validate_file_size(image_bytes=image_bytes, max_file_size=self.MAX_FILE_SIZE)

        processed_bytes = clean_image(
            image_bytes,
            img_format=normalized_format,
            exif_orientation_tag=self.EXIF_ORIENTATION_TAG,
        )

        if paper_size != "original":
            processed_bytes = resize_to_paper_size(
                processed_bytes,
                paper_size=paper_size,
                paper_sizes=self.PAPER_SIZES,
                dpi=self.DEFAULT_DPI,
            )

        output_format = "jpeg" if normalized_format in ("jpg", "jpeg") else normalized_format
        return filename, processed_bytes, output_format

    def _process_page_for_pdf(
        self, page_item: dict[str, Any], paper_size: str = "original"
    ) -> tuple[bytes, int] | None:
        data = page_item.get("data", "")
        rotation = page_item.get("rotation", 0)

        image_bytes = validation.decode_base64_payload(data)

        if rotation not in (0, 90, 180, 270):
            rotation = 0

        if paper_size != "original":
            image_bytes = resize_to_paper_size(
                image_bytes,
                paper_size=paper_size,
                paper_sizes=self.PAPER_SIZES,
                dpi=self.DEFAULT_DPI,
            )

        return image_bytes, rotation

    def _get_output_dir(self) -> Any:
        return storage.ensure_output_dir()

    def _get_unique_filename(self, filename: str, used_names: dict[str, int]) -> str:
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
