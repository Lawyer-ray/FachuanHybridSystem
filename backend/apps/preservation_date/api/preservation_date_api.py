"""Preservation date extraction API."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.http import HttpRequest
from ninja import File, Router
from ninja.files import UploadedFile

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.preservation_date.services import PreservationDateExtractionService
from apps.preservation_date.services.models import PreservationExtractionResult

logger = logging.getLogger("apps.preservation_date")

router = Router(tags=["财产保全日期识别"])


def _format_date(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d")


def _serialize_result(result: PreservationExtractionResult) -> dict[str, Any]:
    return {
        "success": result.success,
        "measures": [
            {
                "measure_type": item.measure_type,
                "property_description": item.property_description,
                "duration": item.duration,
                "start_date": _format_date(item.start_date),
                "end_date": _format_date(item.end_date),
                "is_pending": item.is_pending,
                "pending_note": item.pending_note,
                "raw_text": item.raw_text,
            }
            for item in result.measures
        ],
        "reminders": [
            {
                "reminder_type": item.reminder_type,
                "content": item.content,
                "due_at": _format_date(item.due_at),
                "metadata": item.metadata,
            }
            for item in result.reminders
        ],
        "model_used": result.model_used,
        "extraction_method": result.extraction_method,
        "error": result.error,
        "raw_response": result.raw_response,
    }


@router.post("/extract")
@rate_limit_from_settings("UPLOAD", by_user=True)
def extract_preservation_date(
    request: HttpRequest,
    file: UploadedFile = File(...),  # type: ignore[type-arg]
) -> dict[str, Any]:
    """Extract asset preservation measures and expiration dates from a PDF."""
    service = PreservationDateExtractionService()
    result = service.extract_from_uploaded_file(file.chunks(), file.name)
    return _serialize_result(result)
