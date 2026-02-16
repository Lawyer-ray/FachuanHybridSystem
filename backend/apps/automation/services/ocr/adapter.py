"""Business logic services."""

from __future__ import annotations

from typing import Any

from apps.core.protocols import IOcrService

from .ocr_service import OCRService


class OCRServiceAdapter(IOcrService):
    def __init__(self, service: OCRService | None = None) -> None:
        self._service = service

    @property
    def service(self) -> OCRService:
        if self._service is None:
            self._service = OCRService()
        return self._service

    def extract_text(self, image_bytes: bytes) -> Any:
        return self.service.extract_text(image_bytes)
