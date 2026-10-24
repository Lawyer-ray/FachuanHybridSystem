"""_workflow_tool 注册包装:参数剥离 + 业务异常翻译。

## 背景

带 Bearer 的线上 E2E(2026-10-25)抓到:workflow 工具直接 ORM,访问校验
抛 ``apps.core`` 的 ``BusinessException``(NotFoundError/PermissionDenied)——
不是 ``ToolError`` 子类,SDK 包成 ``UnexpectedToolError``,模型只看到
"Error executing tool get_workflow_detail",连「案件不存在」还是「无权限」
都分不清,无法自纠。与 REST 侧 FachuanApiError(6f6c8050)是同一原则的
两半:预期内业务失败必须带详情直达模型。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.core.exceptions.common import NotFoundError, PermissionDenied
from apps.workflow.models import WorkflowTemplate


def _load_wrapper() -> Any:
    """加载 server._workflow_tool(Django setup 由 conftest/pytest-django 处理)。"""
    from mcp_server.server import _workflow_tool

    return _workflow_tool


@pytest.mark.asyncio
async def test_biz_exception_translated_to_tool_error() -> None:
    """NotFoundError → ToolError,中文 detail 直达模型。"""
    from mcp.server.mcpserver.exceptions import ToolError

    wrap = _load_wrapper()

    async def fake_tool(run_id: int) -> dict[str, Any]:
        raise NotFoundError("工作流运行 #999 不存在")

    wrapped = wrap(fake_tool)
    with pytest.raises(ToolError, match="工作流运行 #999 不存在"):
        await wrapped(run_id=999)


@pytest.mark.asyncio
async def test_permission_denied_translated() -> None:
    from mcp.server.mcpserver.exceptions import ToolError

    wrap = _load_wrapper()

    async def guarded(run_id: int) -> dict[str, Any]:
        raise PermissionDenied(message="无权限访问此案件", code="PERMISSION_DENIED")

    wrapped = wrap(guarded)
    with pytest.raises(ToolError, match="无权限访问此案件"):
        await wrapped(run_id=1)


@pytest.mark.asyncio
async def test_unexpected_exception_not_translated() -> None:
    """非业务异常(如 KeyError)保持原样——意外错误的黑盒是 MCP 规范语义,
    翻译它反而会把内部细节泄露给模型。"""
    wrap = _load_wrapper()

    async def broken(case_id: int) -> dict[str, Any]:
        raise KeyError("internal")

    wrapped = wrap(broken)
    with pytest.raises(KeyError):
        await wrapped(case_id=1)


@pytest.mark.asyncio
async def test_auth_params_stripped_from_signature() -> None:
    """user/org_access/perm_open_access 不出现在包装后的签名(MCP inputSchema
    据此生成,模型不应看到无法构造的 object 参数)。"""
    import inspect

    wrap = _load_wrapper()

    async def with_ctx(
        template_slug: str, case_id: int, *, user: Any = None, org_access: dict | None = None, perm_open_access: bool = False
    ) -> dict[str, Any]:
        return {}

    params = list(inspect.signature(wrap(with_ctx)).parameters)
    assert params == ["template_slug", "case_id"]


@pytest.mark.asyncio
async def test_return_value_passthrough() -> None:
    wrap = _load_wrapper()

    async def ok(run_id: int) -> dict[str, Any]:
        return {"run_id": run_id}

    assert await wrap(ok)(run_id=7) == {"run_id": 7}


def test_sync_function_variant() -> None:
    """同步工具走 def 分支(当前 workflow 全 async,防御未来新增同步工具)。"""
    from mcp.server.mcpserver.exceptions import ToolError

    wrap = _load_wrapper()

    def sync_tool(x: int) -> dict[str, Any]:
        raise NotFoundError("不存在")

    import inspect

    wrapped = wrap(sync_tool)
    assert not inspect.iscoroutinefunction(wrapped)
    with pytest.raises(ToolError, match="不存在"):
        wrapped(x=1)


@pytest.mark.asyncio
async def test_django_does_not_exist_translated() -> None:
    """Django 原生 DoesNotExist(坏 slug/坏 id)同样直达模型。"""
    from mcp.server.mcpserver.exceptions import ToolError

    wrap = _load_wrapper()

    async def by_slug(template_slug: str, case_id: int) -> dict[str, Any]:
        from apps.workflow.models import WorkflowTemplate

        raise WorkflowTemplate.DoesNotExist("WorkflowTemplate matching query does not exist.")

    wrapped = wrap(by_slug)
    with pytest.raises(ToolError, match="对象不存在"):
        await wrapped(template_slug="no-such", case_id=1)
