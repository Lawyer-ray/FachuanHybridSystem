"""盖章申请 API 端点。"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.oa_filing.schemas.stamp_schemas import StampApplyIn, StampLookupOut, StampSessionOut

logger = logging.getLogger("apps.oa_filing.api.stamp")
router = Router()


def _get_stamp_lookup_service() -> Any:
    from apps.oa_filing.services.stamp_lookup_service import StampLookupService

    return StampLookupService()


def _get_task_executor_service() -> Any:
    from apps.oa_filing.services.script_executor_service import ScriptExecutorService

    return ScriptExecutorService()


@router.post("/lookup", response=StampLookupOut)
async def lookup_contract(request: HttpRequest, payload: StampApplyIn) -> Any:
    """根据文件路径反查合同，返回 OA 案件编号。"""
    service = _get_stamp_lookup_service()
    return await sync_to_async(service.lookup_by_file_path, thread_sensitive=False)(
        payload.file_path,
    )


@router.post("/apply", response=StampSessionOut)
async def apply_stamp(request: HttpRequest, payload: StampApplyIn) -> Any:
    """发起盖章申请（异步执行，返回 session 供轮询）。"""
    service = _get_task_executor_service()
    return await sync_to_async(service.execute_stamp, thread_sensitive=False)(
        payload.file_path,
        request.user,
        payload.site_name,
    )


@router.get("/session/{session_id}", response=StampSessionOut)
async def get_stamp_session(request: HttpRequest, session_id: int) -> Any:
    """查询盖章申请状态。"""
    service = _get_task_executor_service()
    return await sync_to_async(service.get_stamp_session, thread_sensitive=False)(session_id)
