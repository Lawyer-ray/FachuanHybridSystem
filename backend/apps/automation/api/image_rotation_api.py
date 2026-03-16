"""Compatibility shim for moved image rotation API."""

from apps.image_rotation.api.image_rotation_api import router

__all__ = ["router"]
