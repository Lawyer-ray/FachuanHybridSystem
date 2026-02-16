"""
Documents API 模块

提供文书生成系统的 REST API 接口.
"""

from .authorization_material_api import router as authorization_material_router
from .document_api import router as document_router
from .folder_template_api import router as folder_template_router
from .generation_api import router as generation_router
from .litigation_generation_api import router as litigation_generation_router
from .placeholder_api import router as placeholder_router
from .preservation_materials_api import router as preservation_materials_router

__all__ = [
    "authorization_material_router",
    "document_router",
    "folder_template_router",
    "generation_router",
    "litigation_generation_router",
    "placeholder_router",
    "preservation_materials_router",
]
