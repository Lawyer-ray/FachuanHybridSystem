"""API endpoints."""
from __future__ import annotations


from typing import Any

import mimetypes

from apps.core.api.schema_utils import schema_to_update_dict
from apps.core.auth import JWTOrSessionAuth
from apps.core.http import build_range_file_response
from apps.core.infrastructure.throttling import rate_limit_from_settings
from ninja import File, Form, Router
from ninja.files import UploadedFile

from apps.chat_records.schemas import (
    ExportCreateIn,
    ExportTaskOut,
    ProjectIn,
    ProjectOut,
    RecordingOut,
    RecordingUpdate,
    ScreenshotOut,
    ScreenshotReorderIn,
    ScreenshotUpdate,
    list_export_statuses,
    list_export_types,
)
from apps.chat_records.services import ExportTaskService, ProjectService, RecordingService, ScreenshotService

# 支持 JWT 和 Session 认证
router = Router(auth=JWTOrSessionAuth())


def _get_project_service() -> ProjectService:
    return ProjectService()


def _get_screenshot_service() -> ScreenshotService:
    return ScreenshotService()


def _get_export_task_service() -> ExportTaskService:
    from apps.core.dependencies.core import build_task_submission_service

    return ExportTaskService(task_submission_service=build_task_submission_service())


def _get_recording_service() -> RecordingService:
    return RecordingService()


@router.get("/export-types")
@rate_limit_from_settings("EXPORT", by_user=True)
def get_export_types(request: Any) -> Any:
    return list_export_types()


@router.get("/export-statuses")
@rate_limit_from_settings("EXPORT", by_user=True)
def get_export_statuses(request: Any) -> Any:
    return list_export_statuses()


@router.post("/projects", response=ProjectOut)
def create_project(request: Any, payload: ProjectIn) -> Any:
    user = getattr(request, "user", None)
    service = _get_project_service()
    project = service.create_project(
        name=payload.name,
        description=payload.description or "",
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    return project


@router.get("/projects", response=list[ProjectOut])
def list_projects(request: Any) -> Any:
    user = getattr(request, "user", None)
    service = _get_project_service()
    return service.list_projects(user=user)


@router.get("/projects/{project_id}/recordings", response=list[RecordingOut])
def list_recordings(request: Any, project_id: int) -> Any:
    user = getattr(request, "user", None)
    service = _get_recording_service()
    return service.list_recordings(user=user, project_id=project_id)


@router.post("/projects/{project_id}/recordings", response=RecordingOut)
@rate_limit_from_settings("UPLOAD", by_user=True)
def upload_recording(request: Any, project_id: int, file: UploadedFile = File(...)) -> Any:
    user = getattr(request, "user", None)
    service = _get_recording_service()
    return service.upload_recording(user=user, project_id=project_id, file=file)


@router.get("/recordings/{recording_id}", response=RecordingOut)
def get_recording(request: Any, recording_id: str) -> Any:
    user = getattr(request, "user", None)
    service = _get_recording_service()
    return service.get_recording(user=user, recording_id=recording_id)


@router.api_operation(["GET", "HEAD"], "/recordings/{recording_id}/stream")
def stream_recording(request: Any, recording_id: str) -> Any:
    from django.http import HttpResponse

    service = _get_recording_service()
    user = getattr(request, "user", None)
    recording = service.get_recording(user=user, recording_id=recording_id)
    if not getattr(recording, "video", None):
        return HttpResponse(status=404)

    video_path = recording.video.path
    content_type, _ = mimetypes.guess_type(video_path)
    return build_range_file_response(request, video_path, content_type=content_type)


@router.patch("/recordings/{recording_id}", response=RecordingOut)
def update_recording(request: Any, recording_id: str, payload: RecordingUpdate) -> Any:
    service = _get_recording_service()
    user = getattr(request, "user", None)
    data = schema_to_update_dict(payload)
    return service.update_duration(user=user, recording_id=recording_id, duration_seconds=data.get("duration_seconds"))


@router.delete("/recordings/{recording_id}")
def delete_recording(request: Any, recording_id: str) -> Any:
    service = _get_recording_service()
    user = getattr(request, "user", None)
    return service.delete_recording(user=user, recording_id=recording_id)


@router.post("/recordings/{recording_id}/extract", response=RecordingOut)
@rate_limit_from_settings("TASK", by_user=True)
def extract_recording(
    request: Any,
    recording_id: str,
    interval_seconds: float = Form(1.0),
    strategy: str = Form("interval"),
    dedup_threshold: int | None = Form(None),
    ocr_similarity_threshold: float | None = Form(None),
    ocr_min_new_chars: int | None = Form(None),
) -> Any:
    from apps.chat_records.services.recording_extract_facade import RecordingExtractFacade, RecordingExtractParams

    facade = RecordingExtractFacade()
    return facade.submit(
        user=getattr(request, "user", None),
        recording_id=recording_id,
        params=RecordingExtractParams(
            interval_seconds=float(interval_seconds or 1.0),
            strategy=str(strategy or "interval"),
            dedup_threshold=dedup_threshold,
            ocr_similarity_threshold=ocr_similarity_threshold,
            ocr_min_new_chars=ocr_min_new_chars,
        ),
    )


@router.post("/recordings/{recording_id}/extract/cancel", response=RecordingOut)
@rate_limit_from_settings("TASK", by_user=True)
def cancel_extract_recording(request: Any, recording_id: str) -> Any:
    from apps.chat_records.services.recording_extract_facade import RecordingExtractFacade

    return RecordingExtractFacade().request_cancel(user=getattr(request, "user", None), recording_id=recording_id)


@router.post("/recordings/{recording_id}/extract/reset", response=RecordingOut)
@rate_limit_from_settings("TASK", by_user=True)
def reset_extract_recording(request: Any, recording_id: str) -> Any:
    from apps.chat_records.services.recording_extract_facade import RecordingExtractFacade

    return RecordingExtractFacade().reset(user=getattr(request, "user", None), recording_id=recording_id)


@router.get("/projects/{project_id}/screenshots", response=list[ScreenshotOut])
def list_screenshots(request: Any, project_id: int) -> Any:
    user = getattr(request, "user", None)
    service = _get_screenshot_service()
    return service.list_screenshots(user=user, project_id=project_id)


@router.post("/projects/{project_id}/screenshots", response=list[ScreenshotOut])
@rate_limit_from_settings("UPLOAD", by_user=True)
def upload_screenshots(
    request: Any,
    project_id: int,
    files: list[UploadedFile] = File(...),
    deduplicate: bool = Form(True),
    capture_time_seconds: float | None = Form(None),
) -> Any:
    service = _get_screenshot_service()
    return service.upload_screenshots(
        user=getattr(request, "user", None),
        project_id=project_id,
        files=files,
        deduplicate=deduplicate,
        capture_time_seconds=capture_time_seconds,
    )


@router.patch("/screenshots/{screenshot_id}", response=ScreenshotOut)
def update_screenshot(request: Any, screenshot_id: str, payload: ScreenshotUpdate) -> Any:
    service = _get_screenshot_service()
    user = getattr(request, "user", None)
    data = schema_to_update_dict(payload)
    return service.update_screenshot(
        user=user, screenshot_id=screenshot_id, title=data.get("title"), note=data.get("note")
    )


@router.delete("/screenshots/{screenshot_id}")
def delete_screenshot(request: Any, screenshot_id: str) -> Any:
    service = _get_screenshot_service()
    return service.delete_screenshot(user=getattr(request, "user", None), screenshot_id=screenshot_id)


@router.post("/projects/{project_id}/screenshots/reorder")
def reorder_screenshots(request: Any, project_id: int, payload: ScreenshotReorderIn) -> Any:
    service = _get_screenshot_service()
    return service.reorder_screenshots(
        user=getattr(request, "user", None), project_id=project_id, screenshot_ids=payload.screenshot_ids
    )


@router.post("/projects/{project_id}/exports", response=ExportTaskOut)
@rate_limit_from_settings("TASK", by_user=True)
def create_export(request: Any, project_id: int, payload: ExportCreateIn) -> Any:
    service = _get_export_task_service()
    user = getattr(request, "user", None)
    task = service.create_export_task(
        user=user, project_id=project_id, export_type=payload.export_type, layout=payload.layout
    )
    service.submit_task(user=user, task_id=str(task.id))
    task.refresh_from_db()
    return task


@router.get("/exports/{task_id}", response=ExportTaskOut)
@rate_limit_from_settings("EXPORT", by_user=True)
def get_export_task(request: Any, task_id: str) -> Any:
    service = _get_export_task_service()
    return service.get_task(user=getattr(request, "user", None), task_id=task_id)


@router.get("/exports/{task_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_export(request: Any, task_id: str) -> Any:
    from django.http import FileResponse, Http404

    service = _get_export_task_service()
    task = service.get_task(user=getattr(request, "user", None), task_id=task_id)
    if not task.output_file:
        raise Http404("导出文件尚未生成")

    filename = task.output_file.name.split("/")[-1]
    return FileResponse(task.output_file.open("rb"), as_attachment=True, filename=filename)
