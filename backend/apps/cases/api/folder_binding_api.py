"""案件文件夹绑定 API"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import (
    CaseFolderBindingCreateSchema,
    CaseFolderBindingResponseSchema,
    CaseStorageSubdirBrowseResponseSchema,
    CaseStorageSubdirRecommendResponseSchema,
    ContractFolderPathSchema,
    FolderBrowseEntrySchema,
    FolderBrowseResponseSchema,
)
from apps.core.security import get_request_access_context

logger = logging.getLogger("apps.cases.api")
router = Router()


def _get_folder_binding_service() -> Any:
    """工厂函数:获取案件文件夹绑定服务"""
    from apps.cases.services import CaseFolderBindingService
    from apps.core.dependencies import (
        build_case_service_with_deps,
        build_client_service,
        build_contract_query_service,
        build_document_service,
    )

    return CaseFolderBindingService(
        document_service=build_document_service(),
        case_service=build_case_service_with_deps(
            contract_service=build_contract_query_service(),
            client_service=build_client_service(),
        ),
    )


@router.post("/{case_id}/folder-binding", response=CaseFolderBindingResponseSchema)
def create_folder_binding(request: HttpRequest, case_id: int, data: CaseFolderBindingCreateSchema) -> Any:
    """创建或更新案件文件夹绑定"""
    service = _get_folder_binding_service()
    ctx = get_request_access_context(request)

    binding = service.create_binding_ctx(case_id=case_id, folder_path=data.folder_path, ctx=ctx)
    is_accessible: bool = service.check_folder_accessible(binding.resolved_folder_path)
    display_path: str = service.format_path_for_display(binding.resolved_folder_path)

    logger.info(
        "case_folder_binding_upsert",
        extra={
            "action": "case_folder_binding_upsert",
            "case_id": case_id,
            "folder_path": str(getattr(binding, "folder_path", "") or ""),
            "display_path": str(display_path or ""),
            "is_accessible": bool(is_accessible),
            "user_id": getattr(getattr(ctx, "user", None), "id", None),
        },
    )

    return CaseFolderBindingResponseSchema.from_binding(
        binding,
        is_accessible=is_accessible,
        display_path=display_path,
    )


@router.get("/{case_id}/folder-binding", response=CaseFolderBindingResponseSchema | None)
def get_folder_binding(request: HttpRequest, case_id: int) -> CaseFolderBindingResponseSchema | None:
    """获取案件文件夹绑定信息

    自动修复链路：
    1. 先修复合同文件夹路径（通过 inode BFS 搜索）
    2. 再检查案件 resolved_folder_path 是否可达
    """
    service = _get_folder_binding_service()
    ctx = get_request_access_context(request)

    binding = service.get_binding_ctx(case_id=case_id, ctx=ctx)

    if not binding:
        return None

    # 先尝试修复合同文件夹路径（合同路径修复后，案件的 resolved_folder_path 自动更新）
    contract_auto_repaired = service.check_and_repair_contract_path(binding)

    is_accessible: bool = service.check_folder_accessible(binding.resolved_folder_path)
    display_path: str = service.format_path_for_display(binding.resolved_folder_path)

    return CaseFolderBindingResponseSchema.from_binding(
        binding,
        is_accessible=is_accessible,
        display_path=display_path,
        path_auto_repaired=contract_auto_repaired,
    )


@router.delete("/{case_id}/folder-binding")
def delete_folder_binding(request: HttpRequest, case_id: int) -> dict[str, bool | str]:
    """删除案件文件夹绑定"""
    service = _get_folder_binding_service()
    ctx = get_request_access_context(request)

    success: bool = service.delete_binding_ctx(case_id=case_id, ctx=ctx)

    logger.info(
        "case_folder_binding_delete",
        extra={
            "action": "case_folder_binding_delete",
            "case_id": case_id,
            "success": bool(success),
            "user_id": getattr(getattr(ctx, "user", None), "id", None),
        },
    )

    return {"success": success, "message": "文件夹绑定删除成功" if success else "未找到绑定记录"}


@router.get("/{case_id}/contract-folder-path", response=ContractFolderPathSchema)
def get_contract_folder_path(request: HttpRequest, case_id: int) -> ContractFolderPathSchema:
    """获取案件关联合同的文件夹路径"""
    service = _get_folder_binding_service()
    ctx = get_request_access_context(request)

    folder_path = service.get_contract_folder_path(case_id)

    logger.info(
        "case_contract_folder_path",
        extra={
            "action": "case_contract_folder_path",
            "case_id": case_id,
            "has_folder_path": folder_path is not None,
            "user_id": getattr(getattr(ctx, "user", None), "id", None),
        },
    )

    return ContractFolderPathSchema(folder_path=folder_path)


@router.get("/folder-browse", response=FolderBrowseResponseSchema)
def browse_folders(request: HttpRequest, path: str | None = None, include_hidden: bool = False) -> Any:
    service = _get_folder_binding_service()
    ctx = get_request_access_context(request)
    service.require_admin(ctx)

    if not path or not str(path).strip():
        default_path = service.get_default_browse_path()
        if default_path:
            path = str(default_path)
        else:
            roots = service.get_browse_roots()
            entries = [FolderBrowseEntrySchema(name=(p.name or str(p)), path=str(p)) for p in roots]
            logger.info(
                "case_folder_browse_roots",
                extra={
                    "action": "case_folder_browse_roots",
                    "include_hidden": bool(include_hidden),
                    "roots_count": len(roots),
                    "user_id": getattr(getattr(ctx, "user", None), "id", None),
                },
            )
            return FolderBrowseResponseSchema(
                browsable=True,
                message=None,
                path=None,
                parent_path=None,
                entries=entries,
            )

    browsable, browse_message = service.is_browsable_path(str(path))
    if not browsable:
        return FolderBrowseResponseSchema(
            browsable=False,
            message=browse_message,
            path=str(path).strip(),
            parent_path=None,
            entries=[],
        )

    resolved = service.resolve_under_allowed_roots(str(path))
    entries = [
        FolderBrowseEntrySchema(**item) for item in service.list_subdirs(str(path), include_hidden=include_hidden)
    ]
    parent_path: str | None = service.compute_parent_path(resolved)

    logger.info(
        "case_folder_browse",
        extra={
            "action": "case_folder_browse",
            "path": str(path).strip(),
            "resolved_path": str(resolved),
            "include_hidden": bool(include_hidden),
            "entries_count": len(entries),
            "user_id": getattr(getattr(ctx, "user", None), "id", None),
        },
    )

    return FolderBrowseResponseSchema(
        browsable=True,
        message=None,
        path=str(resolved),
        parent_path=parent_path,
        entries=entries,
    )


@router.get("/{case_id}/storage-subdirs", response=CaseStorageSubdirBrowseResponseSchema)
def browse_case_storage_subdirs(
    request: HttpRequest,
    case_id: int,
    path: str | None = None,
) -> Any:
    ctx = get_request_access_context(request)
    service = _get_folder_binding_service()
    return service.list_bound_subdirs(
        owner_id=case_id,
        relative_path=str(path or ""),
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.get("/{case_id}/recommended-log-attachment-subdir", response=CaseStorageSubdirRecommendResponseSchema)
def recommend_case_log_attachment_subdir(
    request: HttpRequest,
    case_id: int,
    log_id: int | None = None,
    file_name: str = "",
) -> Any:
    ctx = get_request_access_context(request)
    service = _get_folder_binding_service()

    source_subfolder = ""
    if log_id:
        from apps.cases.models import CaseLog

        log = (
            CaseLog.objects.filter(pk=log_id, case_id=case_id)
            .only("id", "case_id", "source_subfolder")
            .first()
        )
        if log:
            source_subfolder = str(log.source_subfolder or "")

    return service.recommend_bound_subdir_for_log_attachment(
        owner_id=case_id,
        source_subfolder=source_subfolder,
        file_name=str(file_name or ""),
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
