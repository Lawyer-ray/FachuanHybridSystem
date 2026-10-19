"""Business logic services."""

from __future__ import annotations

from ninja.files import UploadedFile

from apps.core.services.storage_service import validate_upload
from apps.organization.models import Lawyer

# 头像仅允许位图格式：svg 等可执行脚本的矢量格式会被 /media/ 直链渲染，禁止入库
AVATAR_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


def _validate_image_extension(uploaded: UploadedFile, *, allowed: frozenset[str], field: str) -> None:
    """校验头像扩展名。

    解耦（2026-10-19）：委托 ``storage_service.validate_upload``（无大小上限；
    错误码统一为 ``INVALID_FILE_TYPE``）。
    """
    validate_upload(uploaded, allowed_extensions=allowed, max_size_bytes=None, field=field)


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
