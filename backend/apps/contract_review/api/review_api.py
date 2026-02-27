from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from django.http import FileResponse, HttpRequest
from ninja import File, Form, Router, UploadedFile

from apps.contract_review.schemas.review_schemas import (
    ConfirmPartyIn,
    TaskCreatedOut,
    TaskStatusOut,
)

logger = logging.getLogger(__name__)
router = Router()


def _get_review_service() -> Any:
    from apps.contract_review.services.review_service import ReviewService

    return ReviewService()


def _get_model_list_service() -> Any:
    from apps.core.llm.model_list_service import ModelListService

    return ModelListService()


@router.post("/upload", response=TaskCreatedOut)
def upload_contract(
    request: HttpRequest,
    file: UploadedFile = File(...),
    model_name: str = Form(""),
) -> dict[str, Any]:
    svc = _get_review_service()
    task = svc.upload_contract(file, request.user, model_name=model_name)
    parties: dict[str, str] = {}
    for key in ("party_a", "party_b", "party_c", "party_d"):
        val = getattr(task, key, "")
        if val:
            parties[key] = val
    return {
        "task_id": task.id,
        "status": task.status,
        "contract_title": task.contract_title or None,
        "parties": parties,
    }


@router.post("/{task_id}/confirm-party", response=TaskStatusOut)
def confirm_party(
    request: HttpRequest,
    task_id: UUID,
    payload: ConfirmPartyIn,
) -> dict[str, Any]:
    svc = _get_review_service()
    task = svc.confirm_party(task_id, payload.represented_party, request.user, payload.reviewer_name, payload.selected_steps)
    return {
        "task_id": task.id,
        "status": task.status,
        "current_step": task.current_step or None,
        "error_message": task.error_message or None,
        "output_filename": None,
    }


@router.get("/{task_id}/status", response=TaskStatusOut)
def get_task_status(request: HttpRequest, task_id: UUID) -> dict[str, Any]:
    svc = _get_review_service()
    task = svc.get_task_status(task_id)
    output_filename = Path(task.output_file).name if task.output_file else None
    return {
        "task_id": task.id,
        "status": task.status,
        "current_step": task.current_step or None,
        "error_message": task.error_message or None,
        "output_filename": output_filename,
    }


@router.get("/{task_id}/download")
def download_result(request: HttpRequest, task_id: UUID) -> FileResponse:
    svc = _get_review_service()
    path = svc.get_result_file(task_id)
    return FileResponse(
        open(path, "rb"),  # noqa: SIM115
        as_attachment=True,
        filename=path.name,
    )


@router.get("/{task_id}/download-original")
def download_original(request: HttpRequest, task_id: UUID) -> FileResponse:
    svc = _get_review_service()
    path = svc.get_original_file(task_id)
    return FileResponse(
        open(path, "rb"),  # noqa: SIM115
        as_attachment=True,
        filename=path.name,
    )


@router.get("/models")
def get_models(request: HttpRequest) -> list[dict[str, str]]:
    svc = _get_model_list_service()
    return svc.get_models()
