"""合同文件夹绑定 API。"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.contracts.schemas import (
    FolderBindingCreateSchema,
    FolderBindingResponseSchema,
    FolderBrowseEntrySchema,
    FolderBrowseResponseSchema,
)
from apps.core.exceptions import PermissionDenied
from apps.core.security import get_request_access_context

logger = logging.getLogger("apps.contracts.api")
router = Router()


def _get_folder_binding_service() -> Any:
    """
    工厂函数:创建 FolderBindingService 实例

    Returns:
        FolderBindingService 实例
    """
    from apps.contracts.services import FolderBindingService
    from apps.core.dependencies.documents import build_document_template_binding_service

    return FolderBindingService(document_template_binding_service=build_document_template_binding_service())


def _require_contract_access(request: HttpRequest, contract_id: int) -> None:
    from apps.contracts.services.contract import wiring

    ctx = get_request_access_context(request)
    wiring.get_contract_query_facade().get_contract_ctx(contract_id=contract_id, ctx=ctx)


def _require_admin(request: HttpRequest) -> None:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("需要登录")


@router.post("/{contract_id}/folder-binding", response=FolderBindingResponseSchema)
def create_folder_binding(request: HttpRequest, contract_id: int, data: FolderBindingCreateSchema) -> Any:
    """
    创建或更新文件夹绑定

    Args:
        contract_id: 合同ID
        data: 绑定数据,包含文件夹路径

    Returns:
        FolderBindingResponseSchema: 绑定信息

    Raises:
        ValidationException: 路径无效或合同不存在

    Requirements: 9.1, 9.4
    """
    _require_admin(request)
    _require_contract_access(request, contract_id)
    service = _get_folder_binding_service()
    ctx = get_request_access_context(request)

    # Resolve storage_account if provided
    storage_account = None
    if data.storage_account_id and data.storage_type != "local":
        from apps.core.cloud_storage.models import CloudStorageAccount

        storage_account = CloudStorageAccount.objects.filter(
            id=data.storage_account_id, storage_type=data.storage_type, is_active=True
        ).first()
        if storage_account is None:
            from apps.core.exceptions import ValidationException

            raise ValidationException(
                message="指定的云存储账号不存在或已禁用",
                code="STORAGE_ACCOUNT_NOT_FOUND",
                errors={"storage_account_id": data.storage_account_id},
            )

    binding = service.create_binding(
        owner_id=contract_id,
        folder_path=data.folder_path,
        storage_type=data.storage_type,
        storage_account=storage_account,
    )

    display_path = service.format_path_for_display(binding.folder_path)
    is_accessible = service.check_folder_accessible(binding.folder_path, binding=binding)

    logger.info(
        "contract_folder_binding_upsert",
        extra={
            "action": "contract_folder_binding_upsert",
            "contract_id": contract_id,
            "folder_path": str(getattr(binding, "folder_path", "") or ""),
            "display_path": str(display_path or ""),
            "is_accessible": bool(is_accessible),
            "user_id": getattr(getattr(ctx, "user", None), "id", None),
        },
    )

    return FolderBindingResponseSchema.from_binding(
        binding,
        is_accessible=is_accessible,
        display_path=display_path,
        path_auto_repaired=False,
    )


@router.get("/{contract_id}/folder-binding", response=FolderBindingResponseSchema | None)
def get_folder_binding(request: HttpRequest, contract_id: int) -> Any:
    """
    获取文件夹绑定信息

    Args:
        contract_id: 合同ID

    Returns:
        Optional[FolderBindingResponseSchema]: 绑定信息,如果未绑定则返回 None

    Requirements: 9.2, 9.4
    """
    _require_contract_access(request, contract_id)
    service = _get_folder_binding_service()

    binding = service.get_binding(owner_id=contract_id)
    if not binding:
        return None

    # 通过 inode 自动修复路径（如果需要）
    is_accessible, path_auto_repaired = service.check_and_repair_path(binding)

    # 格式化显示路径
    display_path = service.format_path_for_display(binding.folder_path)

    return FolderBindingResponseSchema.from_binding(
        binding,
        is_accessible=is_accessible,
        display_path=display_path,
        path_auto_repaired=path_auto_repaired,
    )


@router.delete("/{contract_id}/folder-binding")
def delete_folder_binding(request: HttpRequest, contract_id: int) -> Any:
    """
    删除文件夹绑定

    Args:
        contract_id: 合同ID

    Returns:
        dict: 删除结果

    Requirements: 9.3, 9.5
    """
    _require_admin(request)
    _require_contract_access(request, contract_id)
    service = _get_folder_binding_service()

    ctx = get_request_access_context(request)
    success = service.delete_binding(owner_id=contract_id)

    logger.info(
        "contract_folder_binding_delete",
        extra={
            "action": "contract_folder_binding_delete",
            "contract_id": contract_id,
            "success": bool(success),
            "user_id": getattr(getattr(ctx, "user", None), "id", None),
        },
    )

    return {"success": success, "message": "绑定已删除" if success else "绑定不存在"}


@router.get("/folder-browse", response=FolderBrowseResponseSchema)
def browse_folders(
    request: HttpRequest,
    path: str | None = None,
    include_hidden: bool = False,
    storage_type: str = "local",
    storage_account_id: int | None = None,
) -> Any:
    _require_admin(request)
    ctx = get_request_access_context(request)

    # ── Cloud storage browse ──
    if storage_type and storage_type != "local" and storage_account_id:
        from apps.core.cloud_storage.browse_helper import browse_cloud_folder

        result = browse_cloud_folder(
            storage_type=storage_type,
            storage_account_id=storage_account_id,
            path=path,
            include_hidden=include_hidden,
        )
        return FolderBrowseResponseSchema(
            browsable=result["browsable"],
            message=result["message"],
            path=result["path"],
            parent_path=result["parent_path"],
            entries=[FolderBrowseEntrySchema(**e) for e in result["entries"]],
            storage_type=result["storage_type"],
        )

    # ── Local filesystem browse (existing logic) ──
    service = _get_folder_binding_service()

    if not path or not str(path).strip():
        # 默认进入用户下载文件夹
        default_path = service.get_default_browse_path()
        if default_path:
            path = str(default_path)
        else:
            # 降级：显示根目录列表
            roots = service.get_browse_roots()
            entries = [FolderBrowseEntrySchema(name=(p.name or str(p)), path=str(p)) for p in roots]
            logger.info(
                "contract_folder_browse_roots",
                extra={
                    "action": "contract_folder_browse_roots",
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
            browsable=False,
            message=browse_message,
            path=str(path).strip(),
            parent_path=None,
            entries=[],
            storage_type="local",
        )

    resolved = service.resolve_under_allowed_roots(str(path))
    entries = [
        FolderBrowseEntrySchema(**item) for item in service.list_subdirs(str(path), include_hidden=include_hidden)
    ]
    parent_path = service.compute_parent_path(resolved)

    logger.info(
        "contract_folder_browse",
        extra={
            "action": "contract_folder_browse",
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
    _require_admin(request)
    from apps.core.cloud_storage.browse_helper import list_active_cloud_accounts

    return list_active_cloud_accounts()
