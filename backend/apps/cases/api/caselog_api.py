"""
案件日志 API 层
符合三层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from typing import Any, cast

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.cases.models import CaseLog
from apps.cases.schemas import CaseLogIn, CaseLogOut, CaseLogUpdate
from apps.cases.services.log.caselog_service import CaseLogService
from apps.core.dto.request_context import extract_request_context

router = Router()


def _get_caselog_service() -> CaseLogService:
    """工厂函数：创建 CaseLogService 实例"""
    return CaseLogService()


@router.get("/logs", response=list[CaseLogOut])
async def list_logs(request: HttpRequest, case_id: int | None = None) -> list[CaseLogOut]:  # pragma: no cover
    """获取日志列表"""
    service = _get_caselog_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _fetch() -> list[Any]:
        qs = service.list_logs(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
        objs = list(qs)
        # Pre-warm lazy reminder properties so Django Ninja serialization
        # (which runs in the async event loop) won't trigger sync ORM calls.
        for obj in objs:
            _ = obj.reminder_entries
        return objs

    return cast(list[CaseLogOut], await _fetch())


@router.post("/logs", response=CaseLogOut)
async def create_log(request: HttpRequest, payload: CaseLogIn) -> CaseLogOut:  # pragma: no cover
    """创建日志"""
    service = _get_caselog_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _create() -> Any:
        obj = service.create_log(
            case_id=payload.case_id,
            content=payload.content,
            user=ctx.user,
            reminder_type=payload.reminder_type,
            reminder_time=payload.reminder_time,
        )
        # Re-fetch with select_related/prefetch_related so Django Ninja
        # serialization (which runs in the async event loop) won't trigger
        # sync ORM calls for actor, attachments, etc.
        obj = CaseLog.objects.select_related("actor", "case").prefetch_related("attachments").get(id=obj.id)
        _ = obj.reminder_entries
        return obj

    return cast(CaseLogOut, await _create())


@router.get("/logs/{log_id}", response=CaseLogOut)
async def get_log(request: HttpRequest, log_id: int) -> CaseLogOut:  # pragma: no cover
    """获取单个日志"""
    service = _get_caselog_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _get() -> Any:
        obj = service.get_log(
            log_id=log_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
        # Pre-warm lazy reminder properties so Django Ninja serialization
        # (which runs in the async event loop) won't trigger sync ORM calls.
        _ = obj.reminder_entries
        return obj

    return cast(CaseLogOut, await _get())


@router.put("/logs/{log_id}", response=CaseLogOut)
async def update_log(request: HttpRequest, log_id: int, payload: CaseLogUpdate) -> CaseLogOut:  # pragma: no cover
    """更新日志"""
    service = _get_caselog_service()
    ctx = extract_request_context(request)

    data = payload.model_dump(exclude_unset=True)

    @sync_to_async
    def _update() -> Any:
        obj = service.update_log(
            log_id=log_id,
            data=data,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
        # Pre-warm lazy reminder properties so Django Ninja serialization
        # (which runs in the async event loop) won't trigger sync ORM calls.
        _ = obj.reminder_entries
        return obj

    return cast(CaseLogOut, await _update())


@router.delete("/logs/{log_id}")
async def delete_log(request: HttpRequest, log_id: int) -> Any:  # pragma: no cover
    """删除日志"""
    service = _get_caselog_service()
    ctx = extract_request_context(request)

    @sync_to_async
    def _delete() -> Any:
        return service.delete_log(
            log_id=log_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    return await _delete()


@router.post("/logs/{log_id}/attachments")
async def upload_log_attachments(request: HttpRequest, log_id: int) -> Any:  # pragma: no cover
    """上传日志附件"""
    service = _get_caselog_service()
    ctx = extract_request_context(request)

    files = request.FILES.getlist("files") if hasattr(request, "FILES") else []

    @sync_to_async
    def _upload() -> Any:
        return service.upload_attachments(
            log_id=log_id,
            files=files,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    return await _upload()
