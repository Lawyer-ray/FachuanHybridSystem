"""身份证合并服务门面。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

import cv2
import numpy as np
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _
from numpy.typing import NDArray

from apps.core.exceptions import ValidationException

from . import detection, image_io, pdf, validation
from .paths import ensure_output_dir, ensure_temp_dir, get_media_root
from .transform import perspective_transform

logger = logging.getLogger("apps.client")


class IdCardMergeService:
    ID_CARD_WIDTH = 85.6
    ID_CARD_HEIGHT = 54.0
    ID_CARD_ASPECT_RATIO = ID_CARD_WIDTH / ID_CARD_HEIGHT
    SUPPORTED_FORMATS: ClassVar = {"image/jpeg", "image/png", "image/jpg"}
    SUPPORTED_EXTENSIONS: ClassVar = {".jpg", ".jpeg", ".png"}
    MIN_IMAGE_SIZE = 200

    def _load_and_validate_images(
        self, front_image: UploadedFile, back_image: UploadedFile
    ) -> dict[str, Any] | tuple[NDArray[np.uint8], NDArray[np.uint8]]:
        """验证并加载正反面图片，失败返回错误 dict，成功返回 (front, back) 元组。"""
        for image, name in [(front_image, "正面"), (back_image, "反面")]:
            validation_error = self._validate_image_format(image)
            if validation_error:
                logger.warning("%s图片格式验证失败", name, extra={"error": validation_error, "file_name": image.name})
                return validation_error
        front_cv_image = self._read_uploaded_image(front_image)
        back_cv_image = self._read_uploaded_image(back_image)
        if front_cv_image is None:
            return {"success": False, "error": "INVALID_IMAGE_FORMAT", "message": _("无法读取正面图片，请确保图片格式正确")}
        if back_cv_image is None:
            return {"success": False, "error": "INVALID_IMAGE_FORMAT", "message": _("无法读取反面图片，请确保图片格式正确")}
        for cv_image, name in [(front_cv_image, "正面"), (back_cv_image, "反面")]:
            size_error = self._validate_image_size(cv_image, name)
            if size_error:
                return size_error
        return (front_cv_image, back_cv_image)

    def _success_result(self, pdf_path: str) -> dict[str, Any]:
        logger.info("身份证合并成功", extra={"pdf_path": pdf_path})
        return {"success": True, "pdf_path": pdf_path, "pdf_url": f"/media/{pdf_path}"}

    def merge_id_card(self, front_image: UploadedFile, back_image: UploadedFile) -> dict[str, Any]:
        loaded = self._load_and_validate_images(front_image, back_image)
        if isinstance(loaded, dict):
            return loaded
        front_cv_image, back_cv_image = loaded
        pdf_path = self._generate_pdf(front_cv_image, back_cv_image)
        return self._success_result(pdf_path)

    def merge_id_card_with_detection(self, front_image: UploadedFile, back_image: UploadedFile) -> dict[str, Any]:
        loaded = self._load_and_validate_images(front_image, back_image)
        if isinstance(loaded, dict):
            return loaded
        front_cv_image, back_cv_image = loaded
        front_corners = self._detect_id_card(front_cv_image)
        back_corners = self._detect_id_card(back_cv_image)
        if front_corners is None or back_corners is None:
            logger.info(
                "自动检测失败,保存临时图片",
                extra={"front_detected": front_corners is not None, "back_detected": back_corners is not None},
            )
            front_temp_path = self._save_temp_image(front_image, "front")
            back_temp_path = self._save_temp_image(back_image, "back")
            return {
                "success": False,
                "error": "AUTO_DETECT_FAILED",
                "message": _("无法自动检测身份证边缘，请手动选取四角"),
                "front_image_url": f"/media/{front_temp_path}",
                "back_image_url": f"/media/{back_temp_path}",
            }
        front_transformed = self._perspective_transform(front_cv_image, front_corners)
        back_transformed = self._perspective_transform(back_cv_image, back_corners)
        pdf_path = self._generate_pdf(front_transformed, back_transformed)
        return self._success_result(pdf_path)

    def merge_id_card_manual(
        self, front_image_path: str, back_image_path: str, front_corners: list[list[int]], back_corners: list[list[int]]
    ) -> dict[str, Any]:
        for label, corners in [("正面", front_corners), ("反面", back_corners)]:
            validation = self._validate_corners(corners)
            if validation is not None:
                logger.warning("%s四角坐标无效", label, extra={"corners": corners, "reason": validation})
                return {"success": False, "error": "INVALID_CORNERS", "message": _("%(label)s四角坐标无效: %(reason)s") % {"label": label, "reason": validation}}
        media_root = get_media_root()
        front_full_path, front_rel_path = self._resolve_image_path(front_image_path, media_root)
        back_full_path, back_rel_path = self._resolve_image_path(back_image_path, media_root)
        for label, full_path in [("正面", front_full_path), ("反面", back_full_path)]:
            if not full_path.exists():
                logger.warning("%s图片不存在", label, extra={"path": str(full_path)})
                return {"success": False, "error": "INVALID_CORNERS", "message": _("%(label)s图片不存在，请重新上传") % {"label": label}}
        front_cv_image = cv2.imread(str(front_full_path))
        back_cv_image = cv2.imread(str(back_full_path))
        for label, img in [("正面", front_cv_image), ("反面", back_cv_image)]:
            if img is None:
                return {
                    "success": False,
                    "error": "INVALID_CORNERS",
                    "message": _("无法读取%(label)s图片，请确保图片格式正确") % {"label": label},
                }
        front_corners_ordered = self._order_corners(np.array(front_corners, dtype=np.float32))
        back_corners_ordered = self._order_corners(np.array(back_corners, dtype=np.float32))
        front_transformed = self._perspective_transform(front_cv_image, front_corners_ordered)  # type: ignore[arg-type]
        back_transformed = self._perspective_transform(back_cv_image, back_corners_ordered)  # type: ignore[arg-type]
        pdf_path = self._generate_pdf(front_transformed, back_transformed)
        self._cleanup_temp_file(front_rel_path, front_full_path)
        self._cleanup_temp_file(back_rel_path, back_full_path)
        logger.info("手动合并身份证成功", extra={"pdf_path": pdf_path})
        return {"success": True, "pdf_path": pdf_path, "pdf_url": f"/media/{pdf_path}"}

    def _resolve_image_path(self, image_path: str, media_root: Path) -> tuple[Path, str]:
        rel_path = image_path.lstrip("/")
        if rel_path.startswith("media/"):
            rel_path = rel_path[6:]
        full_path = (media_root / rel_path).resolve()
        try:
            full_path.relative_to(media_root.resolve())
        except ValueError:
            raise ValidationException(
                message=_("非法的文件路径"),
                code="INVALID_FILE_PATH",
                errors={"path": _("文件路径不在允许的范围内")},
            ) from None
        return (full_path, rel_path)

    def _cleanup_temp_file(self, rel_path: str, full_path: Path) -> None:
        if "temp/" not in rel_path:
            return
        try:
            full_path.unlink(missing_ok=True)
            logger.info("清理临时图片", extra={"path": str(full_path)})
        except OSError as e:
            logger.warning("清理临时图片失败", extra={"path": str(full_path), "error": str(e)})

    def _validate_image_format(self, image: UploadedFile) -> dict[str, Any] | None:
        return validation.validate_image_format(
            image, supported_formats=self.SUPPORTED_FORMATS, supported_extensions=self.SUPPORTED_EXTENSIONS
        )

    def _validate_image_size(self, image: NDArray[np.uint8], name: str) -> dict[str, Any] | None:
        return validation.validate_image_size(image, name, min_image_size=self.MIN_IMAGE_SIZE)

    def _read_uploaded_image(self, image: UploadedFile) -> NDArray[np.uint8] | None:
        return image_io.read_uploaded_image(image, logger=logger)

    def _detect_id_card(self, image: NDArray[np.uint8]) -> NDArray[np.float32] | None:
        return detection.detect_id_card_corners(image, id_card_aspect_ratio=self.ID_CARD_ASPECT_RATIO, logger=logger)

    def _perspective_transform(self, image: NDArray[np.uint8], corners: NDArray[np.float32]) -> NDArray[np.uint8]:
        return perspective_transform(image, corners, id_card_aspect_ratio=self.ID_CARD_ASPECT_RATIO, min_output_width=400, logger=logger)

    def _generate_pdf(self, front_image: NDArray[np.uint8], back_image: NDArray[np.uint8]) -> str:
        media_root = get_media_root()
        output_dir = ensure_output_dir(media_root)
        temp_dir = ensure_temp_dir(media_root)
        return pdf.generate_a4_pdf(
            front_image,
            back_image,
            id_card_aspect_ratio=self.ID_CARD_ASPECT_RATIO,
            output_dir=output_dir,
            temp_dir=temp_dir,
            logger=logger,
        )

    def _order_corners(self, corners: NDArray[np.float32]) -> NDArray[np.float32]:
        return validation.order_corners(corners)

    def _validate_corners(self, corners: list[list[int]]) -> str | None:
        return validation.validate_corners(corners)

    def _save_temp_image(self, image: UploadedFile, prefix: str) -> str:
        media_root = get_media_root()
        temp_dir = ensure_temp_dir(media_root)
        return image_io.save_temp_image(image, prefix=prefix, temp_dir=temp_dir, logger=logger)
