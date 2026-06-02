from __future__ import annotations

from django.apps import AppConfig


class ImageRotationConfig(AppConfig):
    """Image rotation app configuration."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.image_rotation"
    verbose_name: str = "图片自动旋转"
