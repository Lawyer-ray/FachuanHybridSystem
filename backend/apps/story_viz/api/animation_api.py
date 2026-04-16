from __future__ import annotations

from typing import Any
from uuid import UUID

from django.http import HttpResponse
from ninja import Router
from pydantic import BaseModel

from apps.story_viz.models import StoryAnimationStatus
from apps.story_viz.services.wiring import get_story_animation_job_service

router = Router(tags=["故事可视化"])


class StoryAnimationStatusOut(BaseModel):
    id: str
    title: str
    viz_type: str
    status: str
    stage: str
    progress: int
    error_message: str
    preview_url: str
    task_id: str
    cancel_requested: bool
    updated_at: str


@router.get("/animations/{animation_id}", response=StoryAnimationStatusOut)
def get_story_animation_status(request: Any, animation_id: UUID) -> StoryAnimationStatusOut:
    animation = get_story_animation_job_service().get_animation(animation_id=animation_id)
    payload = get_story_animation_job_service().build_status_payload(animation=animation)
    return StoryAnimationStatusOut(**payload)


@router.post("/animations/{animation_id}/retry", response=StoryAnimationStatusOut)
def retry_story_animation(request: Any, animation_id: UUID) -> StoryAnimationStatusOut:
    animation = get_story_animation_job_service().retry(animation_id=animation_id)
    payload = get_story_animation_job_service().build_status_payload(animation=animation)
    return StoryAnimationStatusOut(**payload)


@router.post("/animations/{animation_id}/cancel", response=StoryAnimationStatusOut)
def cancel_story_animation(request: Any, animation_id: UUID) -> StoryAnimationStatusOut:
    animation = get_story_animation_job_service().request_cancel(animation_id=animation_id)
    payload = get_story_animation_job_service().build_status_payload(animation=animation)
    return StoryAnimationStatusOut(**payload)


@router.get("/animations/{animation_id}/preview")
def preview_story_animation(request: Any, animation_id: UUID) -> HttpResponse:
    animation = get_story_animation_job_service().get_animation(animation_id=animation_id)
    if animation.status != StoryAnimationStatus.COMPLETED:
        return HttpResponse("任务未完成，暂时无法预览。", status=409, content_type="text/plain; charset=utf-8")
    return HttpResponse(animation.animation_html, content_type="text/html; charset=utf-8")
