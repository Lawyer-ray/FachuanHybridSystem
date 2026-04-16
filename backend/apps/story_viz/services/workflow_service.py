from __future__ import annotations

import logging
from uuid import UUID

from django.utils import timezone

from apps.story_viz.models import StoryAnimation, StoryAnimationStage, StoryAnimationStatus
from apps.story_viz.services.animation_script_service import AnimationScriptService
from apps.story_viz.services.fact_extraction_service import FactExtractionService
from apps.story_viz.services.html_composer_service import AnimationHtmlComposerService
from apps.story_viz.services.preprocess_service import JudgmentPreprocessService
from apps.story_viz.services.svg_fragment_generator_service import SvgFragmentGeneratorService
from apps.story_viz.services.svg_layout_renderer_service import SvgLayoutRendererService

logger = logging.getLogger("apps.story_viz")


class StoryAnimationWorkflowService:
    def __init__(
        self,
        *,
        preprocess_service: JudgmentPreprocessService,
        fact_service: FactExtractionService,
        script_service: AnimationScriptService,
        renderer_service: SvgLayoutRendererService,
        fragment_service: SvgFragmentGeneratorService,
        composer_service: AnimationHtmlComposerService,
    ) -> None:
        self._preprocess_service = preprocess_service
        self._fact_service = fact_service
        self._script_service = script_service
        self._renderer_service = renderer_service
        self._fragment_service = fragment_service
        self._composer_service = composer_service

    def run(self, *, animation_id: str) -> None:
        animation = self._get_animation(animation_id=animation_id)
        try:
            self._update_progress(
                animation=animation,
                status=StoryAnimationStatus.PROCESSING,
                stage=StoryAnimationStage.EXTRACTING_FACTS,
                progress=10,
                started_at=timezone.now(),
            )

            preprocess = self._preprocess_service.preprocess(
                source_text=animation.source_text,
                viz_type=animation.viz_type,
            )
            self._update_fields(animation=animation, source_hash=preprocess.source_hash)

            facts = self._fact_service.extract(
                source_title=animation.source_title,
                source_text=preprocess.cleaned_text,
            )
            self._update_progress(
                animation=animation,
                status=StoryAnimationStatus.PROCESSING,
                stage=StoryAnimationStage.DIRECTING_SCRIPT,
                progress=35,
                facts_payload=facts.model_dump(),
            )

            if self._cancel_requested(animation=animation):
                self._mark_cancelled(animation=animation)
                return

            script = self._script_service.generate_script(facts=facts, viz_type=animation.viz_type)
            self._update_progress(
                animation=animation,
                status=StoryAnimationStatus.PROCESSING,
                stage=StoryAnimationStage.RENDERING_LAYOUT,
                progress=60,
                script_payload=script.model_dump(),
            )

            if self._cancel_requested(animation=animation):
                self._mark_cancelled(animation=animation)
                return

            render_payload = self._renderer_service.render(script=script, viz_type=animation.viz_type)
            self._update_progress(
                animation=animation,
                status=StoryAnimationStatus.PROCESSING,
                stage=StoryAnimationStage.GENERATING_FRAGMENTS,
                progress=80,
                render_payload=render_payload,
            )

            fragment_payload = self._fragment_service.generate(script=script)
            self._update_progress(
                animation=animation,
                status=StoryAnimationStatus.PROCESSING,
                stage=StoryAnimationStage.COMPOSING_HTML,
                progress=90,
            )

            if self._cancel_requested(animation=animation):
                self._mark_cancelled(animation=animation)
                return

            html = self._composer_service.compose(
                title=animation.source_title,
                viz_type=animation.viz_type,
                render_payload=render_payload,
                fragment_payload=fragment_payload,
            )

            self._update_progress(
                animation=animation,
                status=StoryAnimationStatus.COMPLETED,
                stage=StoryAnimationStage.COMPLETED,
                progress=100,
                animation_html=html,
                error_message="",
                finished_at=timezone.now(),
            )
        except Exception as exc:
            logger.exception("story_viz_workflow_failed", extra={"animation_id": animation_id})
            self._update_progress(
                animation=animation,
                status=StoryAnimationStatus.FAILED,
                stage=StoryAnimationStage.FAILED,
                progress=100,
                error_message=str(exc)[:4000],
                finished_at=timezone.now(),
            )

    def _get_animation(self, *, animation_id: str) -> StoryAnimation:
        return StoryAnimation.objects.get(id=UUID(animation_id))

    def _cancel_requested(self, *, animation: StoryAnimation) -> bool:
        animation.refresh_from_db(fields=["cancel_requested"])
        return bool(animation.cancel_requested)

    def _mark_cancelled(self, *, animation: StoryAnimation) -> None:
        self._update_progress(
            animation=animation,
            status=StoryAnimationStatus.CANCELLED,
            stage=StoryAnimationStage.CANCELLED,
            progress=100,
            finished_at=timezone.now(),
            error_message="任务已取消",
        )

    def _update_fields(self, *, animation: StoryAnimation, **kwargs: object) -> None:
        StoryAnimation.objects.filter(id=animation.id).update(**kwargs)
        animation.refresh_from_db()

    def _update_progress(
        self,
        *,
        animation: StoryAnimation,
        status: str,
        stage: str,
        progress: int,
        **extra: object,
    ) -> None:
        updates = {
            "status": status,
            "current_stage": stage,
            "progress_percent": max(0, min(100, int(progress))),
            **extra,
        }
        StoryAnimation.objects.filter(id=animation.id).update(**updates)
        animation.refresh_from_db()
