"""
文件模板 API

提供文件模板的 CRUD 接口.
"""

from __future__ import annotations

import logging

from typing import Any

from django.utils.translation import gettext_lazy as _
from ninja import Router

from apps.core.api.schema_utils import schema_to_update_dict
from apps.core.auth import JWTOrSessionAuth
from apps.documents.schemas import DocumentTemplateIn, DocumentTemplateOut, DocumentTemplateUpdate
from apps.documents.services.template_service import DocumentTemplateService

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


def _get_template_service() -> DocumentTemplateService:
    """工厂函数:创建 DocumentTemplateService 实例"""
    return DocumentTemplateService()


@router.get("/templates", response=list[DocumentTemplateOut])
def list_document_templates(
    request: Any, template_type: str | None = None, case_type: str | None = None, is_active: bool | None = None
) -> Any:
    """
    获取文件模板列表

    Args:
        template_type: 模板类型过滤 (contract/case)
        case_type: 案件类型过滤
        is_active: 启用状态过滤
    """
    service = _get_template_service()
    templates = service.list_templates(
        template_type=template_type,
        case_type=case_type,
        is_active=is_active,
    )
    return templates  # type: ignore[return-value]


@router.get("/templates/{template_id}", response=DocumentTemplateOut)
def get_document_template(request: Any, template_id: int) -> Any:
    """获取文件模板详情"""
    service = _get_template_service()
    return service.get_template_by_id(template_id)


@router.post("/templates", response=DocumentTemplateOut)
def create_document_template(request: Any, payload: DocumentTemplateIn) -> Any:
    """创建文件模板"""
    service = _get_template_service()
    template = service.create_template_from_dict(payload.dict())
    logger.info("创建文件模板: %s (ID: %s)", template.name, template.id)
    return template


@router.put("/templates/{template_id}", response=DocumentTemplateOut)
def update_document_template(request: Any, template_id: int, payload: DocumentTemplateUpdate) -> Any:
    """更新文件模板"""
    service = _get_template_service()
    template = service.update_template_from_dict(template_id, schema_to_update_dict(payload))
    logger.info("更新文件模板: %s (ID: %s)", template.name, template.id)
    return template


@router.delete("/templates/{template_id}")
def delete_document_template(request: Any, template_id: int) -> Any:
    """删除文件模板(软删除)"""
    service = _get_template_service()
    service.delete_template(template_id)
    return {"success": True, "message": _("文件模板已删除")}


@router.get("/templates/{template_id}/placeholders", response=list[str])
def extract_template_placeholders(request: Any, template_id: int) -> Any:
    """提取文件模板中的占位符"""
    service = _get_template_service()
    template = service.get_template_by_id(template_id)
    return service.extract_placeholders(template)


@router.get("/templates/{template_id}/undefined-placeholders", response=list[str])
def get_undefined_placeholders(request: Any, template_id: int) -> Any:
    """获取文件模板中未定义的占位符"""
    service = _get_template_service()
    template = service.get_template_by_id(template_id)
    return service.get_undefined_placeholders(template)
