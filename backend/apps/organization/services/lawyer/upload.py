"""Business logic services."""

from __future__ import annotations

from pathlib import Path

from ninja.files import UploadedFile

from apps.core.exceptions import ValidationException
from apps.organization.models import Lawyer

# 头像仅允许位图格式：svg 等可执行脚本的矢量格式会被 /media/ 直链渲染，禁止入库
AVATAR_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


def _validate_image_extension(uploaded: UploadedFile, *, allowed: frozenset[str], field: str) -> None:
    name = str(getattr(uploaded, "name", "") or "")
    ext = Path(name).suffix.lower()
    if ext not in allowed:
        raise ValidationException(
            f"不支持的图片格式: {ext or '(无扩展名)'}",
            code="INVALID_IMAGE_TYPE",
            errors={field: f"允许的格式: {', '.join(sorted(allowed))}"},
        )


class LawyerUploadService:
    def attach_license_pdf(self, lawyer: Lawyer, license_pdf: UploadedFile | None) -> None:
        if license_pdf is None:
            return
        lawyer.license_pdf.save(license_pdf.name or "license.pdf", license_pdf, save=False)

    def attach_avatar(self, lawyer: Lawyer, avatar: UploadedFile | None) -> None:
        if avatar is None:
            return
        _validate_image_extension(avatar, allowed=AVATAR_ALLOWED_EXTENSIONS, field="avatar")
        lawyer.avatar.save(avatar.name or "avatar.jpg", avatar, save=False)
