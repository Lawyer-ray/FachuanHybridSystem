from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.oa_filing.schemas.filing_schemas import (
    ExecuteFilingIn,
    OAConfigOut,
    SessionOut,
)

logger = logging.getLogger("apps.oa_filing.api")
router = Router()


def _get_executor_service() -> Any:
    from apps.oa_filing.services.script_executor_service import ScriptExecutorService

    return ScriptExecutorService()


def _get_configs(user: Any) -> list[dict[str, Any]]:
    from apps.oa_filing.models import OAConfig
    from apps.organization.models import AccountCredential

    configs = OAConfig.objects.filter(is_enabled=True)
    user_sites: set[str] = set(
        AccountCredential.objects.filter(lawyer=user).values_list("site_name", flat=True)
    )
    return [
        {"id": c.id, "oa_system_name": c.site_name, "has_credential": c.site_name in user_sites}
        for c in configs
    ]


@router.get("/configs", response=list[OAConfigOut])
def list_configs(request: HttpRequest) -> Any:
    """获取当前用户可用的OA配置列表。"""
    if not request.user.is_authenticated:
        return []
    return _get_configs(request.user)


@router.post("/execute", response=SessionOut)
def execute_filing(request: HttpRequest, payload: ExecuteFilingIn) -> Any:
    """执行OA立案。"""
    service = _get_executor_service()
    return service.execute(
        payload.oa_config_id,
        payload.contract_id,
        payload.case_id,
        request.user,
    )


@router.get("/session/{session_id}", response=SessionOut)
def get_session(request: HttpRequest, session_id: int) -> Any:
    """查询立案会话状态。"""
    from apps.oa_filing.models import FilingSession

    return FilingSession.objects.get(pk=session_id)
