from __future__ import annotations

from typing import Any

from apps.core.dependencies.core import build_llm_service

from .animation_script_service import AnimationScriptService
from .fact_extraction_service import FactExtractionService
from .html_composer_service import AnimationHtmlComposerService
from .job_service import StoryAnimationJobService
from .preprocess_service import JudgmentPreprocessService
from .svg_fragment_generator_service import SvgFragmentGeneratorService
from .svg_layout_renderer_service import SvgLayoutRendererService
from .workflow_service import StoryAnimationWorkflowService


def get_story_animation_job_service() -> StoryAnimationJobService:
    return StoryAnimationJobService()


def get_story_animation_workflow_service() -> StoryAnimationWorkflowService:
    llm_service: Any = build_llm_service()
    preprocess_service = JudgmentPreprocessService()
    fact_service = FactExtractionService(llm_service=llm_service)
    script_service = AnimationScriptService(llm_service=llm_service)
    renderer_service = SvgLayoutRendererService()
    fragment_service = SvgFragmentGeneratorService(llm_service=llm_service)
    composer_service = AnimationHtmlComposerService()
    return StoryAnimationWorkflowService(
        preprocess_service=preprocess_service,
        fact_service=fact_service,
        script_service=script_service,
        renderer_service=renderer_service,
        fragment_service=fragment_service,
        composer_service=composer_service,
    )
