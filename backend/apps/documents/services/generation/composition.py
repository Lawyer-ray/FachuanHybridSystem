"""Business logic services."""

from ..infrastructure.wiring import build_authorization_material_generation_service

__all__: list[str] = ["build_authorization_material_generation_service"]
