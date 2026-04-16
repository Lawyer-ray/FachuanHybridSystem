from __future__ import annotations

import logging
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.core.dependencies.core import build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.story_viz.models import StoryAnimation, StoryAnimationStage, StoryAnimationStatus

logger = logging.getLogger("apps.story_viz")


class StoryAnimationJobService:
    @transaction.atomic
    def create_from_admin(
        self,
        *,
        source_title: str,
        source_text: str,
        viz_type: str,
        created_by: object | None = None,
    ) -> StoryAnimation:
        if not source_title.strip():
            raise ValidationException(message="标题不能为空", errors={"source_title": "请输入文书标题"})
        if not source_text.strip():
            raise ValidationException(message="正文不能为空", errors={"source_text": "请输入判决书正文"})

        animation = StoryAnimation.objects.create(
            source_title=source_title.strip(),
            source_text=source_text.strip(),
            viz_type=viz_type,
            status=StoryAnimationStatus.PENDING,
            current_stage=StoryAnimationStage.QUEUED,
            progress_percent=0,
            created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
        )
        task_id = self.submit_generation(animation=animation)
        StoryAnimation.objects.filter(id=animation.id).update(task_id=task_id, started_at=timezone.now())
        animation.refresh_from_db()
        return animation

    def submit_generation(self, *, animation: StoryAnimation) -> str:
        return str(
            build_task_submission_service().submit(
                "apps.story_viz.tasks.generate_story_animation",
                args=[str(animation.id)],
                task_name=f"story_viz_{animation.id}",
            )
        )

    def get_animation(self, *, animation_id: UUID | str) -> StoryAnimation:
        try:
            return StoryAnimation.objects.get(id=UUID(str(animation_id)))
        except StoryAnimation.DoesNotExist:
            raise NotFoundError(message="故事可视化任务不存在", code="STORY_VIZ_NOT_FOUND", errors={}) from None

    def build_status_payload(self, *, animation: StoryAnimation) -> dict[str, object]:
        preview_url = ""
        if animation.status == StoryAnimationStatus.COMPLETED:
            preview_url = f"/api/v1/story-viz/animations/{animation.id}/preview"

        return {
            "id": str(animation.id),
            "title": animation.source_title,
            "viz_type": animation.viz_type,
            "status": animation.status,
            "stage": animation.current_stage,
            "progress": int(animation.progress_percent or 0),
            "error_message": animation.error_message or "",
            "preview_url": preview_url,
            "task_id": animation.task_id or "",
            "cancel_requested": bool(animation.cancel_requested),
            "updated_at": animation.updated_at.isoformat() if animation.updated_at else "",
        }

    @transaction.atomic
    def request_cancel(self, *, animation_id: UUID | str) -> StoryAnimation:
        animation = self.get_animation(animation_id=animation_id)
        if animation.status in {
            StoryAnimationStatus.COMPLETED,
            StoryAnimationStatus.FAILED,
            StoryAnimationStatus.CANCELLED,
        }:
            return animation

        cancel_info: dict[str, object] = {}
        if animation.task_id:
            try:
                cancel_info = build_task_submission_service().cancel(animation.task_id)
            except Exception:
                logger.exception("story_viz_cancel_failed", extra={"animation_id": str(animation.id)})

        can_mark_cancelled = animation.status == StoryAnimationStatus.PENDING and (
            not animation.task_id
            or bool(cancel_info.get("queue_deleted"))
            or not bool(cancel_info.get("running"))
        )
        updates: dict[str, object] = {"cancel_requested": True}
        if can_mark_cancelled:
            updates.update(
                status=StoryAnimationStatus.CANCELLED,
                current_stage=StoryAnimationStage.CANCELLED,
                finished_at=timezone.now(),
                progress_percent=100,
                error_message="任务已取消",
            )
        StoryAnimation.objects.filter(id=animation.id).update(**updates)
        animation.refresh_from_db()
        return animation

    @transaction.atomic
    def retry(self, *, animation_id: UUID | str) -> StoryAnimation:
        animation = self.get_animation(animation_id=animation_id)
        if animation.status not in {StoryAnimationStatus.FAILED, StoryAnimationStatus.CANCELLED}:
            raise ValidationException(message="当前状态不允许重试", errors={"status": animation.status})

        task_id = self.submit_generation(animation=animation)
        StoryAnimation.objects.filter(id=animation.id).update(
            status=StoryAnimationStatus.PENDING,
            current_stage=StoryAnimationStage.QUEUED,
            progress_percent=0,
            task_id=task_id,
            cancel_requested=False,
            error_message="",
            animation_html="",
            finished_at=None,
            started_at=timezone.now(),
        )
        animation.refresh_from_db()
        return animation
