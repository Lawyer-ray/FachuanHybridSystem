"""Business logic services."""

from __future__ import annotations

from ninja.files import UploadedFile

from apps.organization.models import Lawyer

class LawyerUploadService:
    def attach_license_pdf(self, lawyer: Lawyer, license_pdf: UploadedFile | None) -> None:
        if license_pdf is None:
            return
        lawyer.license_pdf.save(license_pdf.name or "license.pdf", license_pdf, save=False)

    def attach_avatar(self, lawyer: Lawyer, avatar: UploadedFile | None) -> None:
        if avatar is None:
            return
        lawyer.avatar.save(avatar.name or "avatar.jpg", avatar, save=False)
