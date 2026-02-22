"""合同文件夹绑定 API。"""

from __future__ import annotations

import logging

from typing import Any

from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
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
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_admin", False):
        raise PermissionDenied(_("需要管理员权限"))


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

    binding = service.create_binding(contract_id, data.folder_path)

    display_path = service.format_path_for_display(binding.folder_path)
    is_accessible = service.check_folder_accessible(binding.folder_path)

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

    binding = service.get_binding(contract_id)
    if not binding:
        return None

    # 格式化显示路径
    display_path = service.format_path_for_display(binding.folder_path)

    # 检查文件夹是否可访问(只检查,不创建)
    is_accessible = service.check_folder_accessible(binding.folder_path)

    return FolderBindingResponseSchema.from_binding(binding, is_accessible=is_accessible, display_path=display_path)


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
    success = service.delete_binding(contract_id)

    logger.info(
        "contract_folder_binding_delete",
        extra={
            "action": "contract_folder_binding_delete",
            "contract_id": contract_id,
            "success": bool(success),
            "user_id": getattr(getattr(ctx, "user", None), "id", None),
        },
    )

    return {"success": success, "message": _("绑定已删除") if success else _("绑定不存在")}


@router.get("/folder-browse", response=FolderBrowseResponseSchema)
def browse_folders(request: HttpRequest, path: str | None = None, include_hidden: bool = False) -> Any:
    _require_admin(request)
    service = _get_folder_binding_service()
    ctx = get_request_access_context(request)

    if not path or not str(path).strip():
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
        browsable=True,
        message=None,
        path=str(resolved),
        parent_path=parent_path,
        entries=entries,
    )
