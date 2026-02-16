"""Module for document delivery."""

from __future__ import annotations

from typing import Any

from django.utils.dateparse import parse_datetime


def execute_document_delivery_query(credential_id: int, cutoff_time_iso: str, tab: str | None = None) -> dict[str, Any]:
    from django.utils import timezone

    from apps.automation.services.document_delivery.document_delivery_service import DocumentDeliveryService

    cutoff_time = parse_datetime(cutoff_time_iso)
    if cutoff_time is None:
        cutoff_time = timezone.now()

    service = DocumentDeliveryService()
    result = service.query_and_download(credential_id=credential_id, cutoff_time=cutoff_time, tab=tab or "")
    return {
        "total_found": result.total_found,
        "processed_count": result.processed_count,
        "skipped_count": result.skipped_count,
        "failed_count": result.failed_count,
        "case_log_ids": result.case_log_ids,
        "errors": result.errors,
    }
