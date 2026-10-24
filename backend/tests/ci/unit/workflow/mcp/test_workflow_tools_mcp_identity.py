"""MCP 直连链路的身份重建(Bearer → 律师)与 run 访问校验。

## 背景

workflow 工具直接 ORM 不走 REST。共享 MCP(streamable-http)模式下 pi 以
「当前律师」的 Bearer 调工具,但工具签名的 ``user`` 参数模型永远传不进来,
此前一律 ``None``:归属校验全跳过(IDOR)、审批/创建不留痕。本轮接入
``_resolve_mcp_access``(从 ContextVar Bearer 重建)+ ``_guard_run_access``
(复用 REST 层同一校验服务)。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from apps.organization.models import Lawyer


@pytest.fixture()
def lawyer(db: Any) -> Lawyer:
    return Lawyer.objects.create_user(username="mcp-identity-lawyer")  # type: ignore[no-untyped-def]


def _set_bearer(token: str) -> None:
    from mcp_server.identity import request_authorization

    request_authorization.set(f"Bearer {token}")


def _clear_bearer() -> None:
    from mcp_server.identity import request_authorization

    request_authorization.set("")


@pytest.mark.asyncio
async def test_no_bearer_returns_anonymous(lawyer: Lawyer) -> None:
    """stdio / 无透传:返回原值(None),维持既有「手工跑 = 服务账号语义」。"""
    from apps.workflow.mcp.workflow_tools import _resolve_mcp_access

    _clear_bearer()
    assert await _resolve_mcp_access(None, None, False) == (None, None, False)


@pytest.mark.asyncio
async def test_rest_user_passthrough_untouched(lawyer: Lawyer) -> None:
    """REST 调用已传 user:原样返回,不触发 token 解析/查库。"""
    from apps.workflow.mcp.workflow_tools import _resolve_mcp_access

    _set_bearer("Bearer garbage-that-would-fail-decode")
    assert await _resolve_mcp_access(lawyer, {"team_ids": [1]}, True) == (lawyer, {"team_ids": [1]}, True)
    _clear_bearer()


@pytest.mark.asyncio
async def test_bearer_rebuilds_lawyer(lawyer: Lawyer) -> None:
    """MCP Bearer → 重建出真实律师 + org_access 补算 + PERM_OPEN_ACCESS。

    Lawyer.objects.get 打桩:thread_sensitive=False 的 ORM 跑在独立线程,
    pytest-django 的事务对它不可见(仅测试环境),此处验证的是身份链逻辑
    而非 ORM 本身。
    """
    from ninja_jwt.tokens import AccessToken

    from apps.workflow.mcp.workflow_tools import _resolve_mcp_access

    _set_bearer(str(AccessToken.for_user(lawyer)))
    try:
        with (
            patch.object(Lawyer.objects, "get", return_value=lawyer),
            patch(
                "apps.organization.middleware.get_or_compute_org_access",
                return_value={"visible_case_ids": [1, 2]},
            ) as org_mock,
            patch("django.conf.settings.PERM_OPEN_ACCESS", True),
        ):
            user, org_access, perm_open = await _resolve_mcp_access(None, None, False)
        assert user == lawyer
        assert org_access == {"visible_case_ids": [1, 2]}
        assert perm_open is True
        org_mock.assert_called_once_with(lawyer)
    finally:
        _clear_bearer()


@pytest.mark.asyncio
async def test_invalid_bearer_degrades_to_anonymous() -> None:
    """解码失败:回退匿名并记 warning,不能让工具整体不可用。"""
    from apps.workflow.mcp.workflow_tools import _resolve_mcp_access

    _set_bearer("Bearer not-a-jwt")
    try:
        assert await _resolve_mcp_access(None, None, False) == (None, None, False)
    finally:
        _clear_bearer()


@pytest.mark.asyncio
async def test_mcp_guard_skipped_without_bearer() -> None:
    """REST 调用链 / stdio 手工:无 ContextVar Bearer,guard 直接跳过。

    REST 的访问校验在 API 层(``_require_run_case_access``)已做,函数内
    不重复校验——直调本函数的既有测试(audit_round4 等)也不受影响。
    """
    from apps.workflow.mcp.workflow_tools import _mcp_guard_run_access

    _clear_bearer()
    with patch(
        "apps.workflow.services.run_access_service.WorkflowRunAccessService.ensure_run_case_access",
        new_callable=AsyncMock,
    ) as guard:
        await _mcp_guard_run_access(1)
    guard.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_guard_invoked_with_bearer(lawyer: Lawyer) -> None:
    """共享 MCP(有 Bearer):重建身份后走 run 访问校验。"""
    from ninja_jwt.tokens import AccessToken

    from apps.core.security.access_context import AccessContext
    from apps.workflow.mcp.workflow_tools import _mcp_guard_run_access

    _set_bearer(str(AccessToken.for_user(lawyer)))
    try:
        with (
            patch.object(Lawyer.objects, "get", return_value=lawyer),
            patch(
                "apps.workflow.services.run_access_service.WorkflowRunAccessService.ensure_run_case_access",
                new_callable=AsyncMock,
            ) as guard,
        ):
            await _mcp_guard_run_access(42)
        guard.assert_awaited_once()
        _, kwargs = guard.call_args
        assert kwargs["run_id"] == 42
        assert isinstance(kwargs["ctx"], AccessContext)
        assert kwargs["ctx"].user == lawyer
    finally:
        _clear_bearer()


@pytest.mark.asyncio
async def test_get_workflow_detail_guards_with_identity(lawyer: Lawyer) -> None:
    """有 Bearer 时 get_workflow_detail 走 run 访问校验(此前完全无校验,IDOR)。

    不预置 run 数据:guard mock 掉后 aget 抛 DoesNotExist 即可证明
    「guard 先于查询执行」——这正是要断言的顺序。
    """
    from ninja_jwt.tokens import AccessToken

    from apps.workflow.mcp.workflow_tools import get_workflow_detail
    from apps.workflow.models import WorkflowRun

    _set_bearer(str(AccessToken.for_user(lawyer)))
    try:
        with (
            patch.object(Lawyer.objects, "get", return_value=lawyer),
            patch(
                "apps.workflow.services.run_access_service.WorkflowRunAccessService.ensure_run_case_access",
                new_callable=AsyncMock,
            ) as guard,
        ):
            with pytest.raises(WorkflowRun.DoesNotExist):
                await get_workflow_detail(99999)
        guard.assert_awaited_once()
        assert guard.call_args.kwargs["ctx"].user == lawyer
    finally:
        _clear_bearer()
