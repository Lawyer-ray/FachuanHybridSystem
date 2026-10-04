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
    OpenStampIn,
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
    """根据第一个文件路径反查合同，返回 OA 案件编号。

    安全审计：返回合同信息前按查询用户做 ContractAccessPolicy 校验；
    无权与未命中返回同款响应，避免借此探测他所合同。
    """
    from ninja.errors import HttpError

    if not payload.file_paths:
        raise HttpError(400, "file_paths 不能为空")

    from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy
    from apps.core.exceptions import PermissionDenied
    from apps.oa_filing.services.stamp_lookup_service import StampLookupError

    service = _get_stamp_lookup_service()

    def _lookup() -> Any:
        try:
            result = service.lookup_by_file_path(payload.file_paths[0])
        except StampLookupError:
            raise HttpError(404, "无法根据文件路径找到关联合同") from None
        ContractAccessPolicy().ensure_access(contract_id=result.contract_id, user=request.user, org_access=None)
        return result

    try:
        # thread_sensitive 默认（True）：复用调用线程的事务上下文，测试与事务内可见性一致
        return await sync_to_async(_lookup)()
    except PermissionDenied:
        raise HttpError(404, "无法根据文件路径找到关联合同") from None


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
    # 安全审计 A-04：传入当前用户做会话属主校验
    return await sync_to_async(service.get_archive_session, thread_sensitive=False)(session_id, request.user)


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


@router.post("/open-stamp")
async def open_stamp_page(request: HttpRequest, payload: OpenStampIn) -> dict[str, Any]:
    """打开 OA 盖章页面，登录→搜索案件→填表，保持浏览器打开。"""
    service = _get_task_executor_service()
    await sync_to_async(service.open_stamp_page, thread_sensitive=False)(
        payload.case_id,
        request.user,
        payload.site_name,
    )
    return {"success": True, "message": "浏览器已打开，请查看"}
