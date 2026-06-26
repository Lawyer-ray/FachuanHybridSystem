"""Business logic services."""

from __future__ import annotations

from typing import Any

from apps.core.protocols import IOcrService
from apps.core.protocols.ocr_types import OCRTextResult

from .ocr_service import OCRService


class OCRServiceAdapter(IOcrService):
    def __init__(self, service: OCRService | None = None) -> None:
        self._service = service

    @property
    def service(self) -> OCRService:
        if self._service is None:
            self._service = OCRService()
        return self._service

    def recognize(self, image_path: str) -> str:
        return self.service.recognize(image_path)

    def recognize_bytes(self, image_bytes: bytes) -> str:
        return self.service.recognize_bytes(image_bytes)

    def extract_text(self, image_bytes: bytes) -> OCRTextResult:
        return self.service.extract_text(image_bytes)

    def recognize_raw(self, image_bytes: bytes) -> Any:
        return self.service.recognize_raw(image_bytes)
