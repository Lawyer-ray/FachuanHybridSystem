from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StoryVizConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.story_viz"
    verbose_name = _("故事可视化")
