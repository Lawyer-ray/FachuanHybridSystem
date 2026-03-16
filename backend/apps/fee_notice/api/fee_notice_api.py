"""Fee notice recognition API."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.http import HttpRequest
from ninja import File, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.core.infrastructure.throttling import rate_limit_from_settings

logger = logging.getLogger("apps.fee_notice")

router = Router(tags=["交费通知书识别"])


class FeeCompareIn(Schema):
    """Fee comparison request payload."""

    case_id: int
    extracted_acceptance_fee: Decimal | None = None
    extracted_preservation_fee: Decimal | None = None


def _to_number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _serialize_notice(notice: Any, debug: bool) -> dict[str, Any]:
    amounts = notice.amounts
    return {
        "file_name": notice.file_name,
        "file_path": notice.file_path,
        "page_num": notice.page_num,
        "confidence": notice.detection.confidence,
        "matched_keywords": notice.detection.matched_keywords,
        "acceptance_fee": _to_number(amounts.acceptance_fee),
        "application_fee": _to_number(amounts.application_fee),
        "preservation_fee": _to_number(amounts.preservation_fee),
        "execution_fee": _to_number(amounts.execution_fee),
        "other_fee": _to_number(amounts.other_fee),
        "total_fee": _to_number(amounts.total_fee),
        "table_format": amounts.table_format,
        "extraction_method": notice.extraction_method,
        "debug_info": amounts.debug_info if debug else {},
    }


def _normalize_error_file(raw_file: str | None) -> str:
    if not raw_file:
        return "未知文件"
    return Path(raw_file).name or raw_file


@router.post("/extract")
@rate_limit_from_settings("UPLOAD", by_user=True)
def extract_fee_notice(
    request: HttpRequest,
    files: list[UploadedFile] = File(...),  # type: ignore[type-arg]
    debug: bool = False,
) -> dict[str, Any]:
    """Extract fee notice information from uploaded PDF files."""
    if not files:
        raise HttpError(400, "未提供文件")

    from apps.fee_notice.services import FeeNoticeExtractionService

    service = FeeNoticeExtractionService()
    saved_files: list[Path] = []

    try:
        saved_files, upload_errors = service.save_uploaded_files(files)
        extraction = service.extract_from_files([str(path) for path in saved_files], debug=debug)

        errors: list[dict[str, str]] = []
        for item in upload_errors:
            errors.append(
                {
                    "file": _normalize_error_file(item.get("file")),
                    "error": item.get("error", "处理失败"),
                    "code": item.get("code", "UPLOAD_ERROR"),
                }
            )

        for item in extraction.errors:
            raw_file = str(item.get("file") or item.get("path") or "")
            errors.append(
                {
                    "file": _normalize_error_file(raw_file),
                    "error": str(item.get("error") or "处理失败"),
                    "code": str(item.get("code") or "EXTRACTION_ERROR"),
                }
            )

        return {
            "notices": [_serialize_notice(notice, debug=debug) for notice in extraction.notices],
            "errors": errors,
            "debug_logs": extraction.debug_logs if debug else [],
            "total_files": len(files),
            "total_pages": extraction.total_pages,
        }
    except HttpError:
        raise
    except Exception as exc:
        logger.error("交费通知书识别失败: %s", exc, exc_info=True)
        raise HttpError(500, "识别失败")
    finally:
        service.cleanup_temp_files(saved_files)


@router.get("/cases/search")
def search_cases(request: HttpRequest, keyword: str, limit: int = 20) -> dict[str, Any]:
    """Search cases for fee comparison."""
    from apps.fee_notice.services import FeeComparisonService

    safe_limit = max(1, min(limit, 50))
    service = FeeComparisonService()
    cases = service.search_cases(keyword=keyword, limit=safe_limit)

    return {
        "cases": [
            {
                "id": case.id,
                "name": case.name,
                "case_number": case.case_number,
                "cause_of_action": case.cause_of_action,
                "target_amount": _to_number(case.target_amount),
            }
            for case in cases
        ]
    }


@router.post("/compare")
def compare_fee(request: HttpRequest, payload: FeeCompareIn) -> dict[str, Any]:
    """Compare extracted fee values with system-calculated values."""
    from apps.fee_notice.services import FeeComparisonService

    service = FeeComparisonService()

    try:
        result = service.compare_fee(
            case_id=payload.case_id,
            extracted_acceptance_fee=payload.extracted_acceptance_fee,
            extracted_preservation_fee=payload.extracted_preservation_fee,
        )
    except Exception as exc:
        logger.error("费用比对失败: %s", exc, exc_info=True)
        raise HttpError(500, "费用比对失败")

    case_info = result.case_info
    return {
        "case_id": case_info.case_id,
        "case_name": case_info.case_name,
        "case_number": case_info.case_number,
        "cause_of_action": case_info.cause_of_action_name,
        "target_amount": _to_number(case_info.target_amount),
        "preservation_amount": _to_number(case_info.preservation_amount),
        "extracted_acceptance_fee": _to_number(result.extracted_acceptance_fee),
        "extracted_preservation_fee": _to_number(result.extracted_preservation_fee),
        "calculated_acceptance_fee": _to_number(result.calculated_acceptance_fee),
        "calculated_acceptance_fee_half": _to_number(result.calculated_acceptance_fee_half),
        "calculated_preservation_fee": _to_number(result.calculated_preservation_fee),
        "acceptance_fee_match": result.acceptance_fee_match,
        "acceptance_fee_close": result.acceptance_fee_close,
        "acceptance_fee_diff": _to_number(result.acceptance_fee_diff),
        "preservation_fee_match": result.preservation_fee_match,
        "preservation_fee_close": result.preservation_fee_close,
        "preservation_fee_diff": _to_number(result.preservation_fee_diff),
        "can_compare": result.can_compare,
        "message": result.message,
    }
