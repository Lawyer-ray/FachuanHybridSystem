from __future__ import annotations

import logging

from apps.story_viz.services.wiring import get_story_animation_workflow_service

logger = logging.getLogger("apps.story_viz")


def generate_story_animation(animation_id: str) -> None:
    try:
        get_story_animation_workflow_service().run(animation_id=animation_id)
    except Exception:
        logger.exception("story_viz_task_failed", extra={"animation_id": animation_id})
        raise
