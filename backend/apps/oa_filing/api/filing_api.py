from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import File, Router, UploadedFile

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.oa_filing.schemas.filing_schemas import ExecuteFilingIn, FilingAttachmentOut, FilingSessionOut, OAConfigOut
from apps.oa_filing.services.oa_firm_registry import SUPPORTED_SITES

logger = logging.getLogger("apps.oa_filing.api")
router = Router()


def _get_executor_service() -> Any:
    from apps.oa_filing.services.script_executor_service import ScriptExecutorService

    return ScriptExecutorService()


def _get_organization_service() -> Any:
    from apps.core.dependencies import build_organization_service

    return build_organization_service()


@router.get("/configs", response=list[OAConfigOut])
async def list_configs(request: HttpRequest) -> Any:  # pragma: no cover
    """返回当前用户有凭证且系统支持的 OA 站点列表。"""
    if not request.user.is_authenticated:
        return []
    lawyer_id = getattr(request.user, "id", None)
    org_service = _get_organization_service()
    user_sites: set[str] = (
        set(await sync_to_async(org_service.list_sites_for_lawyer, thread_sensitive=False)(int(lawyer_id)))
        if lawyer_id is not None
        else set()
    )
    return [{"id": name, "oa_system_name": name, "has_credential": name in user_sites} for name in SUPPORTED_SITES]


@router.post("/execute", response=FilingSessionOut)
async def execute_filing(request: HttpRequest, payload: ExecuteFilingIn) -> Any:  # pragma: no cover
    """执行OA立案。"""
    service = _get_executor_service()
    return await sync_to_async(service.execute, thread_sensitive=False)(
        payload.site_name,
        payload.contract_id,
        payload.case_id,
        request.user,
    )


@router.post("/attachment", response=FilingAttachmentOut)
@rate_limit_from_settings("TASK", by_user=True)
async def stage_filing_attachment(
    request: HttpRequest, contract_id: int, file: UploadedFile = File(...)
) -> Any:  # pragma: no cover
    """立案前拖拽暂存合同文件：落为合同正本材料（幂等去重）。"""
    from apps.core.exceptions import NotFoundError
    from apps.core.security import get_request_access_context

    def _stage() -> Any:
        from apps.contracts.services.contract import wiring

        ctx = get_request_access_context(request)
        wiring.get_contract_query_facade().get_contract_ctx(contract_id=contract_id, ctx=ctx)

        from apps.oa_filing.services.filing_attachment_service import stage_filing_attachment

        return stage_filing_attachment(contract_id, file)

    try:
        return await sync_to_async(_stage, thread_sensitive=False)()
    except NotFoundError:
        raise
    except Exception:
        logger.exception("立案附件暂存失败: contract_id=%s", contract_id)
        from apps.core.exceptions import ValidationException

        raise ValidationException(message="合同文件保存失败，请重试") from None


@router.get("/session/{session_id}", response=FilingSessionOut)
async def get_session(request: HttpRequest, session_id: int) -> Any:  # pragma: no cover
    """查询立案会话状态。"""
    service = _get_executor_service()
    # 安全审计 A-04：传入当前用户做会话属主校验
    return await sync_to_async(service.get_session, thread_sensitive=False)(session_id, request.user)
