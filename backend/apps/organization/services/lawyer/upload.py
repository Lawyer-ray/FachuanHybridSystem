"""Business logic services."""

from __future__ import annotations

from typing import Any

from ninja.files import UploadedFile


class LawyerUploadService:
    def attach_license_pdf(self, lawyer: Any, license_pdf: UploadedFile | None) -> None:
        if license_pdf is None:
            return
        lawyer.license_pdf.save(license_pdf.name, license_pdf, save=False)
