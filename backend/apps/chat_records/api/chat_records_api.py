"""API endpoints."""

import mimetypes
from typing import Any

from asgiref.sync import sync_to_async
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
from apps.chat_records.services.extraction.recording_extract_facade import (
    RecordingExtractFacade,
    RecordingExtractParams,
)
from apps.core.api.schema_utils import schema_to_update_dict
from apps.core.http import build_range_file_response
from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.auth import JWTOrSessionAuth

# 支持 JWT 和 Session 认证
router = Router(auth=JWTOrSessionAuth())


def _get_project_service() -> ProjectService:
    return ProjectService()


def _get_screenshot_service() -> ScreenshotService:
    return ScreenshotService(project_service=_get_project_service())


def _get_export_task_service() -> ExportTaskService:
    from apps.core.dependencies.core import build_task_submission_service

    return ExportTaskService(
        task_submission_service=build_task_submission_service(),
        project_service=_get_project_service(),
    )


def _get_recording_service() -> RecordingService:
    return RecordingService(project_service=_get_project_service())


def _get_recording_extract_facade() -> RecordingExtractFacade:
    from apps.core.dependencies.core import build_task_submission_service

    return RecordingExtractFacade(task_submission_service=build_task_submission_service())


@router.get("/export-types")
@rate_limit_from_settings("EXPORT", by_user=True)
async def get_export_types(request: Any) -> Any:  # pragma: no cover
    return list_export_types()


@router.get("/export-statuses")
@rate_limit_from_settings("EXPORT", by_user=True)
async def get_export_statuses(request: Any) -> Any:  # pragma: no cover
    return list_export_statuses()


@router.post("/projects", response=ProjectOut)
async def create_project(request: Any, payload: ProjectIn) -> Any:  # pragma: no cover
    user = getattr(request, "user", None)
    service = _get_project_service()

    @sync_to_async
    def _create() -> dict:
        project = service.create_project(
            name=payload.name,
            description=payload.description or "",
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        return ProjectOut.from_orm(project).model_dump(by_alias=True)

    return await _create()


@router.get("/projects", response=list[ProjectOut])
async def list_projects(request: Any) -> Any:  # pragma: no cover
    user = getattr(request, "user", None)
    service = _get_project_service()

    @sync_to_async
    def _fetch() -> list[dict]:
        qs = service.list_projects(user=user)
        return [ProjectOut.from_orm(p).model_dump(by_alias=True) for p in qs]

    return await _fetch()


@router.get("/projects/{project_id}/recordings", response=list[RecordingOut])
async def list_recordings(request: Any, project_id: int) -> Any:  # pragma: no cover
    user = getattr(request, "user", None)
    service = _get_recording_service()

    @sync_to_async
    def _fetch() -> list[dict]:
        qs = service.list_recordings(user=user, project_id=project_id)
        return [RecordingOut.from_orm(r).model_dump(by_alias=True) for r in qs]

    return await _fetch()


@router.post("/projects/{project_id}/recordings", response=RecordingOut)
@rate_limit_from_settings("UPLOAD", by_user=True)
async def upload_recording(request: Any, project_id: int, file: UploadedFile = File(...)) -> Any:  # pragma: no cover
    user = getattr(request, "user", None)
    service = _get_recording_service()

    @sync_to_async
    def _create() -> dict:
        recording = service.upload_recording(user=user, project_id=project_id, file=file)
        return RecordingOut.from_orm(recording).model_dump(by_alias=True)

    return await _create()


@router.get("/recordings/{recording_id}", response=RecordingOut)
async def get_recording(request: Any, recording_id: str) -> Any:  # pragma: no cover
    user = getattr(request, "user", None)
    service = _get_recording_service()

    @sync_to_async
    def _fetch() -> dict:
        recording = service.get_recording(user=user, recording_id=recording_id)
        return RecordingOut.from_orm(recording).model_dump(by_alias=True)

    return await _fetch()


@router.api_operation(["GET", "HEAD"], "/recordings/{recording_id}/stream")
def stream_recording(request: Any, recording_id: str) -> Any:  # pragma: no cover
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
async def update_recording(request: Any, recording_id: str, payload: RecordingUpdate) -> Any:  # pragma: no cover
    service = _get_recording_service()
    user = getattr(request, "user", None)
    data = schema_to_update_dict(payload)

    @sync_to_async
    def _update() -> dict:
        recording = service.update_duration(user=user, recording_id=recording_id, duration_seconds=data.get("duration_seconds"))
        return RecordingOut.from_orm(recording).model_dump(by_alias=True)

    return await _update()


@router.delete("/recordings/{recording_id}")
async def delete_recording(request: Any, recording_id: str) -> Any:  # pragma: no cover
    service = _get_recording_service()
    user = getattr(request, "user", None)
    return await sync_to_async(service.delete_recording)(user=user, recording_id=recording_id)


@router.post("/recordings/{recording_id}/extract", response=RecordingOut)
@rate_limit_from_settings("TASK", by_user=True)
async def extract_recording(  # pragma: no cover
    request: Any,
    recording_id: str,
    interval_seconds: float = Form(1.0),
    strategy: str = Form("interval"),
    dedup_threshold: int | None = Form(None),
    ocr_similarity_threshold: float | None = Form(None),
    ocr_min_new_chars: int | None = Form(None),
) -> Any:

    facade = _get_recording_extract_facade()

    @sync_to_async
    def _submit() -> dict:
        recording = facade.submit(
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
        return RecordingOut.from_orm(recording).model_dump(by_alias=True)

    return await _submit()


@router.post("/recordings/{recording_id}/extract/cancel", response=RecordingOut)
@rate_limit_from_settings("TASK", by_user=True)
async def cancel_extract_recording(request: Any, recording_id: str) -> Any:  # pragma: no cover

    @sync_to_async
    def _cancel() -> dict:
        recording = _get_recording_extract_facade().request_cancel(
            user=getattr(request, "user", None), recording_id=recording_id,
        )
        return RecordingOut.from_orm(recording).model_dump(by_alias=True)

    return await _cancel()


@router.post("/recordings/{recording_id}/extract/reset", response=RecordingOut)
@rate_limit_from_settings("TASK", by_user=True)
async def reset_extract_recording(request: Any, recording_id: str) -> Any:  # pragma: no cover

    @sync_to_async
    def _reset() -> dict:
        recording = _get_recording_extract_facade().reset(
            user=getattr(request, "user", None), recording_id=recording_id,
        )
        return RecordingOut.from_orm(recording).model_dump(by_alias=True)

    return await _reset()


@router.get("/projects/{project_id}/screenshots", response=list[ScreenshotOut])
async def list_screenshots(request: Any, project_id: int) -> Any:  # pragma: no cover
    user = getattr(request, "user", None)
    service = _get_screenshot_service()

    @sync_to_async
    def _fetch() -> list[dict]:
        qs = service.list_screenshots(user=user, project_id=project_id)
        return [ScreenshotOut.from_orm(s).model_dump(by_alias=True) for s in qs]

    return await _fetch()


@router.post("/projects/{project_id}/screenshots", response=list[ScreenshotOut])
@rate_limit_from_settings("UPLOAD", by_user=True)
async def upload_screenshots(  # pragma: no cover
    request: Any,
    project_id: int,
    files: list[UploadedFile] = File(...),
    deduplicate: bool = Form(True),
    capture_time_seconds: float | None = Form(None),
) -> Any:
    service = _get_screenshot_service()

    @sync_to_async
    def _create() -> list[dict]:
        screenshots = service.upload_screenshots(
            user=getattr(request, "user", None),
            project_id=project_id,
            files=files,
            deduplicate=deduplicate,
            capture_time_seconds=capture_time_seconds,
        )
        return [ScreenshotOut.from_orm(s).model_dump(by_alias=True) for s in screenshots]

    return await _create()


@router.post("/projects/{project_id}/screenshots/reorder")
async def reorder_screenshots(request: Any, project_id: int, payload: ScreenshotReorderIn) -> Any:  # pragma: no cover
    service = _get_screenshot_service()
    user = getattr(request, "user", None)

    @sync_to_async
    def _reorder() -> Any:
        return service.reorder_screenshots(user=user, project_id=project_id, screenshot_ids=payload.screenshot_ids)

    return await _reorder()


@router.patch("/screenshots/{screenshot_id}", response=ScreenshotOut)
async def update_screenshot(request: Any, screenshot_id: str, payload: ScreenshotUpdate) -> Any:  # pragma: no cover
    service = _get_screenshot_service()
    user = getattr(request, "user", None)
    data = schema_to_update_dict(payload)

    @sync_to_async
    def _update() -> dict:
        screenshot = service.update_screenshot(
            user=user, screenshot_id=screenshot_id, title=data.get("title"), note=data.get("note"),
        )
        return ScreenshotOut.from_orm(screenshot).model_dump(by_alias=True)

    return await _update()


@router.post("/projects/{project_id}/exports", response=ExportTaskOut)
@rate_limit_from_settings("TASK", by_user=True)
async def create_export(request: Any, project_id: int, payload: ExportCreateIn) -> Any:  # pragma: no cover
    service = _get_export_task_service()
    user = getattr(request, "user", None)

    @sync_to_async
    def _create() -> dict:
        task = service.create_export_task(
            user=user, project_id=project_id, export_type=payload.export_type, layout=payload.layout,
        )
        service.submit_task(user=user, task_id=str(task.id))
        task.refresh_from_db()
        return ExportTaskOut.from_orm(task).model_dump(by_alias=True)

    return await _create()


@router.get("/exports/{task_id}", response=ExportTaskOut)
@rate_limit_from_settings("EXPORT", by_user=True)
async def get_export_task(request: Any, task_id: str) -> Any:  # pragma: no cover
    service = _get_export_task_service()

    @sync_to_async
    def _fetch() -> dict:
        task = service.get_task(user=getattr(request, "user", None), task_id=task_id)
        return ExportTaskOut.from_orm(task).model_dump(by_alias=True)

    return await _fetch()


@router.get("/exports/{task_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_export(request: Any, task_id: str) -> Any:  # pragma: no cover
    from django.http import FileResponse, Http404

    service = _get_export_task_service()
    task = service.get_task(user=getattr(request, "user", None), task_id=task_id)
    if not task.output_file:
        raise Http404("导出文件尚未生成")

    filename = task.output_file.name.split("/")[-1]
    return FileResponse(task.output_file.open("rb"), as_attachment=True, filename=filename)
