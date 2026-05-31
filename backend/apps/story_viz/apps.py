from __future__ import annotations

from django.apps import AppConfig

class StoryVizConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.story_viz"
    verbose_name = "故事可视化"
