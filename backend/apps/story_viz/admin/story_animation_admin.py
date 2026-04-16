from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.utils.html import format_html

from apps.story_viz.models import StoryAnimation
from apps.story_viz.services.wiring import get_story_animation_job_service


@admin.register(StoryAnimation)
class StoryAnimationAdmin(admin.ModelAdmin[StoryAnimation]):
    change_form_template = "admin/story_viz/storyanimation/change_form.html"
    list_display = [
        "id",
        "source_title",
        "viz_type",
        "status_badge",
        "current_stage",
        "progress_percent",
        "created_at",
    ]
    list_filter = ["status", "viz_type", "created_at"]
    search_fields = ["source_title", "source_text", "id"]
    ordering = ["-created_at"]

    readonly_fields = [
        "id",
        "status",
        "current_stage",
        "progress_percent",
        "task_id",
        "cancel_requested",
        "source_hash",
        "facts_payload",
        "script_payload",
        "render_payload",
        "animation_html",
        "error_message",
        "started_at",
        "finished_at",
        "created_by",
        "created_at",
        "updated_at",
    ]

    def get_readonly_fields(self, request: HttpRequest, obj: StoryAnimation | None = None) -> list[str]:
        if obj is None:
            return []
        return list(self.readonly_fields)

    def get_fields(self, request: HttpRequest, obj: StoryAnimation | None = None) -> list[str]:  # type: ignore[override]
        if obj is None:
            return ["source_title", "source_text", "viz_type"]
        return [
            "id",
            "source_title",
            "source_text",
            "viz_type",
            "status",
            "current_stage",
            "progress_percent",
            "task_id",
            "cancel_requested",
            "source_hash",
            "facts_payload",
            "script_payload",
            "render_payload",
            "animation_html",
            "error_message",
            "started_at",
            "finished_at",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def save_model(self, request: HttpRequest, obj: StoryAnimation, form: Any, change: bool) -> None:
        if change:
            super().save_model(request, obj, form, change)
            return

        animation = get_story_animation_job_service().create_from_admin(
            source_title=str(form.cleaned_data.get("source_title") or ""),
            source_text=str(form.cleaned_data.get("source_text") or ""),
            viz_type=str(form.cleaned_data.get("viz_type") or "timeline"),
            created_by=getattr(request, "user", None),
        )
        obj.pk = animation.pk

    def status_badge(self, obj: StoryAnimation) -> str:
        color_map = {
            "pending": "#8d6e63",
            "processing": "#1565c0",
            "completed": "#2e7d32",
            "failed": "#c62828",
            "cancelled": "#546e7a",
        }
        color = color_map.get(obj.status, "#546e7a")
        return format_html('<span style="color:{};font-weight:700;">{}</span>', color, obj.get_status_display())

    status_badge.short_description = "状态"  # type: ignore[attr-defined]

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        extra = extra_context or {}
        extra["story_viz_status_api"] = f"/api/v1/story-viz/animations/{object_id}"
        extra["story_viz_retry_api"] = f"/api/v1/story-viz/animations/{object_id}/retry"
        extra["story_viz_cancel_api"] = f"/api/v1/story-viz/animations/{object_id}/cancel"
        extra["story_viz_preview_api"] = f"/api/v1/story-viz/animations/{object_id}/preview"
        return super().change_view(request, object_id, form_url, extra_context=extra)
