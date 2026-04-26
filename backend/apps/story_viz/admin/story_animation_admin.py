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
    actions = ["requeue_selected", "delete_selected"]
    list_display = [
        "source_title",
        "viz_type_display",
        "status_badge",
        "stage_display",
        "progress_display",
        "created_by",
        "created_at_display",
    ]
    list_filter = ["status", "viz_type", "current_stage", "created_at"]
    search_fields = ["source_title", "source_text", "id__icontains"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_per_page = 20

    fieldsets = [
        (
            None,
            {"fields": ("source_title", "source_text", "viz_type")},
        ),
        (
            "任务状态",
            {
                "fields": (
                    "status",
                    "current_stage",
                    "progress_percent",
                    "cancel_requested",
                    "task_id",
                    "started_at",
                    "finished_at",
                    "duration",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "结构化结果",
            {
                "fields": (
                    "facts_payload_display",
                    "script_payload_display",
                    "render_payload_display",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "输出",
            {
                "fields": (
                    "animation_html",
                    "error_message",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "元信息",
            {
                "fields": (
                    "id",
                    "source_hash",
                    "created_by",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    ]

    readonly_fields = [
        "id",
        "status",
        "current_stage",
        "progress_percent",
        "task_id",
        "cancel_requested",
        "source_hash",
        "facts_payload_display",
        "script_payload_display",
        "render_payload_display",
        "animation_html",
        "error_message",
        "started_at",
        "finished_at",
        "duration",
        "created_by",
        "created_at",
        "updated_at",
    ]

    def get_readonly_fields(self, request: HttpRequest, obj: StoryAnimation | None = None) -> list[str]:
        if obj is None:
            return []
        return list(self.readonly_fields)

    def get_fieldsets(self, request: HttpRequest, obj: StoryAnimation | None = None) -> Any:
        if obj is None:
            return [(None, {"fields": ("source_title", "source_text", "viz_type")})]
        return self.fieldsets

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

    def viz_type_display(self, obj: StoryAnimation) -> str:
        return obj.get_viz_type_display()

    viz_type_display.short_description = "类型"

    def stage_display(self, obj: StoryAnimation) -> str:
        return obj.get_current_stage_display()

    stage_display.short_description = "阶段"

    def progress_display(self, obj: StoryAnimation) -> str:
        pct = obj.progress_percent or 0
        width = max(40, min(pct, 100))
        color = "#0ea5e9" if pct < 100 else "#34d399"
        return format_html(
            '<div style="width:{}px;height:8px;background:#e2e8f0;border-radius:999px;overflow:hidden;">'
            '<div style="width:{}%;height:100%;background:{};"></div></div>',
            width, pct, color
        ) + format_html(' <span style="color:#64748b;font-size:11px;">{}%</span>', pct)

    progress_display.short_description = "进度"

    def created_at_display(self, obj: StoryAnimation) -> str:
        return obj.created_at.strftime("%Y-%m-%d %H:%M") if obj.created_at else "-"

    created_at_display.short_description = "创建时间"

    @admin.display(description="耗时")
    def duration(self, obj: StoryAnimation) -> str:
        if not obj.started_at:
            return "-"
        from django.utils import timezone
        end = obj.finished_at or timezone.now()
        elapsed = (end - obj.started_at).total_seconds()
        if elapsed < 60:
            return f"{int(elapsed)} 秒"
        return f"{int(elapsed / 60)} 分 {int(elapsed % 60)} 秒"

    @admin.display(description="事实数据")
    def facts_payload_display(self, obj: StoryAnimation) -> str:
        facts = obj.facts_payload or {}
        events = facts.get("events", [])
        parties = facts.get("parties", [])
        rv = []
        if events:
            rv.append(f"事件节点: {len(events)} 个")
        if parties:
            rv.append(f"人物节点: {len(parties)} 个")
        if not rv:
            rv.append("无数据")
        return " · ".join(rv)

    @admin.display(description="脚本数据")
    def script_payload_display(self, obj: StoryAnimation) -> str:
        script = obj.script_payload or {}
        nodes = script.get("timeline_nodes", [])
        rnodes = script.get("relationship_nodes", [])
        edges = script.get("edges", [])
        rv = []
        if nodes:
            rv.append(f"时间线节点: {len(nodes)} 个")
        if rnodes:
            rv.append(f"关系节点: {len(rnodes)} 个")
        if edges:
            rv.append(f"关系连线: {len(edges)} 条")
        if not rv:
            rv.append("无数据")
        return " · ".join(rv)

    @admin.display(description="渲染数据")
    def render_payload_display(self, obj: StoryAnimation) -> str:
        render = obj.render_payload or {}
        nodes = render.get("nodes", [])
        edges = render.get("edges", [])
        rv = []
        if nodes:
            rv.append(f"节点: {len(nodes)} 个")
        if edges:
            rv.append(f"连线: {len(edges)} 条")
        if not rv:
            rv.append("无数据")
        return " · ".join(rv)

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
