"""
文件夹模板 API

提供文件夹模板的 CRUD 接口.
"""

from __future__ import annotations

import logging
from typing import Any

from ninja import Router

from apps.core.api.schema_utils import schema_to_update_dict
from apps.core.auth import JWTOrSessionAuth
from apps.documents.schemas import FolderTemplateIn, FolderTemplateOut, FolderTemplateUpdate

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


def _get_folder_template_service() -> Any:
    """工厂函数:创建 FolderTemplateService 实例"""
    from apps.core.dependencies.documents_query import build_folder_template_service

    return build_folder_template_service()


@router.get("/folder-templates", response=list[FolderTemplateOut])
def list_folder_templates(
    request: Any, template_type: str | None = None, case_type: str | None = None, is_active: bool | None = None
) -> Any:
    """
    获取文件夹模板列表

    Args:
        template_type: 模板类型过滤 (contract/case)
        case_type: 案件类型过滤
        is_active: 启用状态过滤
    """
    service = _get_folder_template_service()
    return service.list_templates(  # type: ignore[return-value]
        case_type=case_type,
        is_active=is_active,
    )


@router.get("/folder-templates/{template_id}", response=FolderTemplateOut)
def get_folder_template(request: Any, template_id: int) -> Any:
    """获取文件夹模板详情"""
    service = _get_folder_template_service()
    return service.get_template_by_id(template_id)


@router.post("/folder-templates", response=FolderTemplateOut)
def create_folder_template(request: Any, payload: FolderTemplateIn) -> Any:
    """创建文件夹模板"""
    service = _get_folder_template_service()
    template = service.create_template_from_dict(payload.dict())
    logger.info("创建文件夹模板: %s (ID: %s)", template.name, template.id)
    return template


@router.put("/folder-templates/{template_id}", response=FolderTemplateOut)
def update_folder_template(request: Any, template_id: int, payload: FolderTemplateUpdate) -> Any:
    """更新文件夹模板"""
    service = _get_folder_template_service()
    template = service.update_template_from_dict(template_id, schema_to_update_dict(payload))
    logger.info("更新文件夹模板: %s (ID: %s)", template.name, template.id)
    return template


@router.delete("/folder-templates/{template_id}", response=dict[str, Any])
def delete_folder_template(request: Any, template_id: int) -> Any:
    """删除文件夹模板(软删除)"""
    service = _get_folder_template_service()
    service.delete_template(template_id)
    return {"success": True, "message": "文件夹模板已删除"}


@router.post("/folder-templates/{template_id}/validate", response=dict[str, Any])
def validate_folder_structure(request: Any, template_id: int) -> Any:
    """验证文件夹模板结构"""
    service = _get_folder_template_service()
    template = service.get_template_by_id(template_id)
    is_valid, error_msg = service.validate_structure(template.structure)
    return {
        "is_valid": is_valid,
        "error_message": error_msg if not is_valid else None,
    }
