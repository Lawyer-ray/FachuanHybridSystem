"""归档材料提交 API 端点。"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.oa_filing.schemas.archive_schemas import (
    ArchiveApplyIn,
    ArchiveLookupOut,
    ArchiveSessionOut,
    OpenInvoiceIn,
    OpenOAIn,
)

logger = logging.getLogger("apps.oa_filing.api.archive")
router = Router()


def _get_stamp_lookup_service() -> Any:
    from apps.oa_filing.services.stamp_lookup_service import StampLookupService

    return StampLookupService()


def _get_task_executor_service() -> Any:
    from apps.oa_filing.services.script_executor_service import ScriptExecutorService

    return ScriptExecutorService()


@router.post("/lookup", response=ArchiveLookupOut)
async def lookup_contract(request: HttpRequest, payload: ArchiveApplyIn) -> Any:
    """根据第一个文件路径反查合同，返回 OA 案件编号。"""
    if not payload.file_paths:
        from ninja.errors import HttpError

        raise HttpError(400, "file_paths 不能为空")
    service = _get_stamp_lookup_service()
    return await sync_to_async(service.lookup_by_file_path, thread_sensitive=False)(
        payload.file_paths[0],
    )


@router.post("/apply", response=ArchiveSessionOut)
async def apply_archive(request: HttpRequest, payload: ArchiveApplyIn) -> Any:
    """发起归档材料提交（异步执行，返回 session 供轮询）。"""
    if not payload.file_paths:
        from ninja.errors import HttpError

        raise HttpError(400, "file_paths 不能为空")
    service = _get_task_executor_service()
    return await sync_to_async(service.execute_archive, thread_sensitive=False)(
        payload.file_paths,
        request.user,
        payload.site_name,
    )


@router.get("/session/{session_id}", response=ArchiveSessionOut)
async def get_archive_session(request: HttpRequest, session_id: int) -> Any:
    """查询归档提交状态。"""
    service = _get_task_executor_service()
    return await sync_to_async(service.get_archive_session, thread_sensitive=False)(session_id)


@router.post("/open-oa")
async def open_oa_page(request: HttpRequest, payload: OpenOAIn) -> dict[str, Any]:
    """打开 OA 归档页面，自动填写案件编号和小结，保持浏览器打开。"""
    service = _get_task_executor_service()
    await sync_to_async(service.open_oa_page, thread_sensitive=False)(
        payload.contract_id,
        request.user,
        payload.description,
        payload.site_name,
    )
    return {"success": True, "message": "浏览器已打开，请查看"}


@router.post("/open-invoice")
async def open_invoice_page(request: HttpRequest, payload: OpenInvoiceIn) -> dict[str, Any]:
    """打开 OA 发票页面，输入案件编号并跳转到开票页面，保持浏览器打开。"""
    service = _get_task_executor_service()
    await sync_to_async(service.open_invoice_page, thread_sensitive=False)(
        payload.contract_id,
        request.user,
        payload.site_name,
    )
    return {"success": True, "message": "浏览器已打开，请查看"}
