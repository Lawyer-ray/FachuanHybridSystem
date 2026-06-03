"""案件文件夹绑定 API"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import (
    CaseFolderBindingCreateSchema,
    CaseFolderBindingResponseSchema,
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

    # Resolve storage_account if provided
    storage_account = None
    if data.storage_account_id and data.storage_type != "local":
        from apps.core.cloud_storage.models import CloudStorageAccount

        storage_account = CloudStorageAccount.objects.filter(
            id=data.storage_account_id, storage_type=data.storage_type, is_active=True
        ).first()

    binding = service.create_binding_ctx(
        case_id=case_id,
        folder_path=data.folder_path,
        ctx=ctx,
        storage_type=data.storage_type,
        storage_account=storage_account,
    )
    is_accessible: bool = service.check_folder_accessible(binding.resolved_folder_path, binding=binding)
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

    is_accessible: bool = service.check_folder_accessible(binding.resolved_folder_path, binding=binding)
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
def browse_folders(
    request: HttpRequest,
    path: str | None = None,
    include_hidden: bool = False,
    storage_type: str = "local",
    storage_account_id: int | None = None,
) -> Any:
    service = _get_folder_binding_service()
    ctx = get_request_access_context(request)
    service.require_admin(ctx)

    # ── Cloud storage browse ──
    if storage_type and storage_type != "local" and storage_account_id:
        from apps.core.cloud_storage.factory import create_provider_from_account
        from apps.core.cloud_storage.models import CloudStorageAccount as CSA

        account = CSA.objects.filter(id=storage_account_id, storage_type=storage_type, is_active=True).first()
        if not account:
            return FolderBrowseResponseSchema(
                browsable=False, message="云存储账号不存在", path=path, parent_path=None, entries=[], storage_type=storage_type
            )

        provider = create_provider_from_account(account)
        browse_path = (path or "").strip().rstrip("/") or "/"

        try:
            children = provider.list_directory(browse_path)
        except Exception:
            logger.exception("cloud_browse_failed", extra={"path": browse_path, "account_id": storage_account_id})
            return FolderBrowseResponseSchema(
                browsable=False, message="云存储目录访问失败", path=browse_path, parent_path=None, entries=[], storage_type=storage_type
            )

        entries = []
        for child in children:
            if not child.is_dir:
                continue
            if not include_hidden and child.name.startswith("."):
                continue
            child_path = browse_path.rstrip("/") + "/" + child.name
            entries.append(FolderBrowseEntrySchema(name=child.name, path=child_path))
        entries.sort(key=lambda e: e.name.lower())

        parent_path: str | None = None
        if browse_path != "/":
            from pathlib import PurePosixPath
            parent_path = str(PurePosixPath(browse_path).parent)
            if parent_path == ".":
                parent_path = "/"

        return FolderBrowseResponseSchema(
            browsable=True, message=None, path=browse_path, parent_path=parent_path, entries=entries, storage_type=storage_type
        )

    # ── Local filesystem browse (existing logic) ──
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
                browsable=True, message=None, path=None, parent_path=None, entries=entries, storage_type="local"
            )

    browsable, browse_message = service.is_browsable_path(str(path))
    if not browsable:
        return FolderBrowseResponseSchema(
            browsable=False, message=browse_message, path=str(path).strip(), parent_path=None, entries=[], storage_type="local"
        )

    resolved = service.resolve_under_allowed_roots(str(path))
    entries = [
        FolderBrowseEntrySchema(**item) for item in service.list_subdirs(str(path), include_hidden=include_hidden)
    ]
    parent_path = service.compute_parent_path(resolved)

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
        browsable=True, message=None, path=str(resolved), parent_path=parent_path, entries=entries, storage_type="local"
    )


@router.get("/cloud-storage-accounts")
def list_cloud_storage_accounts(request: HttpRequest) -> list[dict[str, Any]]:
    """List available cloud storage accounts for folder binding."""
    from apps.core.cloud_storage.models import CloudStorageAccount as CSA

    service = _get_folder_binding_service()
    ctx = get_request_access_context(request)
    service.require_admin(ctx)
    accounts = CSA.objects.filter(is_active=True).values(
        "id", "name", "storage_type", "local_root_path", "webdav_root_path", "onedrive_root_path"
    )
    return list(accounts)
