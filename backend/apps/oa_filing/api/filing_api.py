from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.oa_filing.schemas.filing_schemas import ExecuteFilingIn, OAConfigOut, SessionOut
from apps.oa_filing.services.script_executor_service import SUPPORTED_SITES

logger = logging.getLogger("apps.oa_filing.api")
router = Router()


def _get_executor_service() -> Any:
    from apps.oa_filing.services.script_executor_service import ScriptExecutorService

    return ScriptExecutorService()


def _get_organization_service() -> Any:
    from apps.core.dependencies import build_organization_service

    return build_organization_service()


@router.get("/configs", response=list[OAConfigOut])
def list_configs(request: HttpRequest) -> Any:
    """返回当前用户有凭证且系统支持的 OA 站点列表。"""
    if not request.user.is_authenticated:
        return []
    lawyer_id = getattr(request.user, "id", None)
    user_sites: set[str] = (
        set(_get_organization_service().list_sites_for_lawyer(int(lawyer_id))) if lawyer_id is not None else set()
    )
    return [
        {"id": name, "oa_system_name": name, "has_credential": name in user_sites}
        for name in SUPPORTED_SITES
    ]


@router.post("/execute", response=SessionOut)
def execute_filing(request: HttpRequest, payload: ExecuteFilingIn) -> Any:
    """执行OA立案。"""
    service = _get_executor_service()
    return service.execute(
        payload.site_name,
        payload.contract_id,
        payload.case_id,
        request.user,
    )


@router.get("/session/{session_id}", response=SessionOut)
def get_session(request: HttpRequest, session_id: int) -> Any:
    """查询立案会话状态。"""
    from apps.oa_filing.models import FilingSession

    return FilingSession.objects.get(pk=session_id)
