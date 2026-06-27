"""
文件模板 API

提供文件模板的 CRUD 接口.
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router

from apps.core.api.schema_utils import schema_to_update_dict
from apps.core.security.auth import JWTOrSessionAuth
from apps.documents.models import DocumentTemplate
from apps.documents.schemas import DocumentTemplateIn, DocumentTemplateOut, DocumentTemplateUpdate
from apps.documents.services.template.template_service import DocumentTemplateService
from apps.documents.storage import list_docx_templates_files

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


def _get_template_service() -> DocumentTemplateService:
    """工厂函数:创建 DocumentTemplateService 实例"""
    return DocumentTemplateService()


def _prewarm_template(obj: Any) -> Any:
    """Pre-warm lazy relations on a DocumentTemplate so Django Ninja
    serialization (which runs in the async event loop) won't trigger
    sync ORM calls.

    Re-fetches with prefetch_related to populate Django's internal
    queryset cache so that resolve_folder_bindings won't issue new queries.
    """
    return (
        DocumentTemplate.objects.prefetch_related("folder_bindings__folder_template")
        .get(pk=obj.pk)
    )


@router.get("/templates", response=list[DocumentTemplateOut])
async def list_document_templates(  # pragma: no cover
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
    @sync_to_async
    def _fetch() -> list[dict[str, Any]]:
        from apps.documents.models import DocumentTemplate

        qs = DocumentTemplate.objects.prefetch_related(
            "folder_bindings__folder_template"
        )
        if template_type is not None:
            qs = qs.filter(template_type=template_type)
        if case_type is not None:
            qs = qs.filter(case_types__contains=[case_type])
        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        # Materialize and return raw objects; pre-warm all lazy relations
        # so Django Ninja serialization won't trigger sync ORM calls.
        objs = list(qs)
        for obj in objs:
            _ = list(obj.folder_bindings.all())
            for binding in obj.folder_bindings.all():
                _ = binding.folder_template_id
                _ = binding.folder_template.name
        return objs  # type: ignore[return-value]

    return await _fetch()


@router.get("/templates/library-files", response=list[dict[str, str]])
async def list_template_library_files(request: Any) -> Any:  # pragma: no cover
    """列出模板库中可用的 docx 文件（用于前端下拉选择）"""
    files = await sync_to_async(list_docx_templates_files)()
    return [{"path": path, "name": name} for path, name in files]


@router.get("/templates/{template_id}", response=DocumentTemplateOut)
async def get_document_template(request: Any, template_id: int) -> Any:  # pragma: no cover
    """获取文件模板详情"""
    service = _get_template_service()

    @sync_to_async
    def _get() -> Any:
        template = service.get_template_by_id(template_id)
        return _prewarm_template(template)

    return await _get()


@router.post("/templates", response=DocumentTemplateOut)
async def create_document_template(request: Any, payload: DocumentTemplateIn) -> Any:  # pragma: no cover
    """创建文件模板"""
    service = _get_template_service()

    @sync_to_async
    def _create() -> Any:
        template = service.create_template_from_dict(payload.dict())
        return _prewarm_template(template)

    template = await _create()
    logger.info("创建文件模板: %s (ID: %s)", template.name, template.id)
    return template


@router.put("/templates/{template_id}", response=DocumentTemplateOut)
async def update_document_template(request: Any, template_id: int, payload: DocumentTemplateUpdate) -> Any:  # pragma: no cover
    """更新文件模板"""
    service = _get_template_service()

    @sync_to_async
    def _update() -> Any:
        template = service.update_template_from_dict(template_id, schema_to_update_dict(payload))
        return _prewarm_template(template)

    template = await _update()
    logger.info("更新文件模板: %s (ID: %s)", template.name, template.id)
    return template


@router.delete("/templates/{template_id}", response=dict[str, Any])
async def delete_document_template(request: Any, template_id: int) -> Any:  # pragma: no cover
    """删除文件模板(软删除)"""
    service = _get_template_service()
    await sync_to_async(service.delete_template)(template_id)
    return {"success": True, "message": "文件模板已删除"}


@router.get("/templates/{template_id}/placeholders", response=list[str])
async def extract_template_placeholders(request: Any, template_id: int) -> Any:  # pragma: no cover
    """提取文件模板中的占位符"""
    service = _get_template_service()
    template = await sync_to_async(service.get_template_by_id)(template_id)
    return await sync_to_async(service.extract_placeholders)(template)


@router.get("/templates/{template_id}/undefined-placeholders", response=list[str])
async def get_undefined_placeholders(request: Any, template_id: int) -> Any:  # pragma: no cover
    """获取文件模板中未定义的占位符"""
    service = _get_template_service()
    template = await sync_to_async(service.get_template_by_id)(template_id)
    return await sync_to_async(service.get_undefined_placeholders)(template)
