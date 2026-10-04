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
    """根据文件路径反查合同，返回 OA 案件编号。

    安全审计：返回合同信息前按查询用户做 ContractAccessPolicy 校验；
    无权与未命中返回同款响应，避免借此探测他所合同。
    """
    from ninja.errors import HttpError

    from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy
    from apps.core.exceptions import PermissionDenied
    from apps.oa_filing.services.stamp_lookup_service import StampLookupError

    service = _get_stamp_lookup_service()

    def _lookup() -> Any:
        try:
            result = service.lookup_by_file_path(payload.file_path)
        except StampLookupError:
            raise HttpError(404, "无法根据文件路径找到关联合同") from None
        ContractAccessPolicy().ensure_access(contract_id=result.contract_id, user=request.user, org_access=None)
        return result

    try:
        # thread_sensitive 默认（True）：复用调用线程的事务上下文，测试与事务内可见性一致
        return await sync_to_async(_lookup)()
    except PermissionDenied:
        raise HttpError(404, "无法根据文件路径找到关联合同") from None


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
    # 安全审计 A-04：传入当前用户做会话属主校验
    return await sync_to_async(service.get_stamp_session, thread_sensitive=False)(session_id, request.user)
