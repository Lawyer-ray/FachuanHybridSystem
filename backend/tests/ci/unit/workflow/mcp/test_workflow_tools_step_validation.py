"""安全审计 A-01 旁路修复：MCP 模板写入入口的步骤类型校验。

历史缺口：A-01 只堵了 HTTP API（template_service._FORBIDDEN_STEP_TYPES），
MCP 的 create_workflow_template / update_workflow_template 是另一条写入
WorkflowTemplate.steps_schema 的入口且零校验，code 步骤可经此落库后由
workflows.py 调度 generic_code_exec（AST 黑名单沙箱可逃逸）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.workflow.models import WorkflowTemplate

_CODE_STEP: dict[str, Any] = {
    "id": "evil",
    "name": "任意代码执行",
    "type": "code",
    "config": {"code": "print(1)"},
}
_SAFE_STEP: dict[str, Any] = {
    "id": "collect_facts",
    "name": "收集案件事实",
    "type": "activity",
    "mcp_tool": "get_case",
    "config": {},
}


@pytest.mark.asyncio
async def test_create_workflow_template_rejects_code_step() -> None:
    """安全审计 A-01：MCP 创建模板不得接受 code 步骤。"""
    from apps.workflow.mcp.workflow_tools import create_workflow_template

    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.acreate = AsyncMock()
        result = await create_workflow_template(name="恶意模板", steps=[_CODE_STEP])

    assert "error" in result
    MockObjs.acreate.assert_not_called()


@pytest.mark.asyncio
async def test_create_workflow_template_rejects_code_step_for_superuser() -> None:
    """code 步骤对 superuser 同样禁止——它是全局禁用类型，不是权限分级。"""
    from apps.workflow.mcp.workflow_tools import create_workflow_template

    superuser = SimpleNamespace(id=1, is_authenticated=True, is_superuser=True)
    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.acreate = AsyncMock()
        result = await create_workflow_template(name="恶意模板", steps=[_CODE_STEP], user=superuser)

    assert "error" in result
    MockObjs.acreate.assert_not_called()


@pytest.mark.asyncio
async def test_create_workflow_template_allows_safe_step() -> None:
    """合法 activity 步骤不受影响（携带 mcp_tool 需 superuser，故传 superuser）。"""
    from apps.workflow.mcp.workflow_tools import create_workflow_template

    created = MagicMock()
    created.id = 1
    created.name = "正常模板"
    created.slug = "zhengchang-moban"
    created.category = "litigation"

    superuser = SimpleNamespace(id=1, is_authenticated=True, is_superuser=True)
    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.filter.return_value.aexists = AsyncMock(return_value=False)
        MockObjs.acreate = AsyncMock(return_value=created)
        result = await create_workflow_template(name="正常模板", steps=[_SAFE_STEP], user=superuser)

    assert result.get("template_id") == 1
    assert result.get("steps_count") == 1


@pytest.mark.asyncio
async def test_create_workflow_template_rejects_mcp_tool_for_non_superuser() -> None:
    """白名单绕过防护：type 合法但携带 mcp_tool 字段，非 superuser 拒绝。"""
    from apps.workflow.mcp.workflow_tools import create_workflow_template

    plain_user = SimpleNamespace(id=2, is_authenticated=True, is_superuser=False)
    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.acreate = AsyncMock()
        result = await create_workflow_template(name="模板", steps=[_SAFE_STEP], user=plain_user)

    assert "error" in result
    MockObjs.acreate.assert_not_called()


@pytest.mark.asyncio
async def test_update_workflow_template_rejects_code_step() -> None:
    """安全审计 A-01：MCP 更新模板同样不得写入 code 步骤。"""
    from apps.workflow.mcp.workflow_tools import update_workflow_template

    template = MagicMock()
    template.pk = 5
    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(return_value=template)
        result = await update_workflow_template(template_id=5, steps=[_CODE_STEP])

    assert "error" in result
    template.save.assert_not_called()


@pytest.mark.asyncio
async def test_update_workflow_template_metadata_only_still_works() -> None:
    """不传 steps 的纯元数据更新不走步骤校验，行为不变。"""
    from apps.workflow.mcp.workflow_tools import update_workflow_template

    template = MagicMock()
    template.pk = 5
    template.name = "旧名"
    template.asave = AsyncMock()
    with patch.object(WorkflowTemplate, "objects") as MockObjs:
        MockObjs.aget = AsyncMock(return_value=template)
        result = await update_workflow_template(template_id=5, description="新描述")

    assert template.description == "新描述"
    assert "error" not in result
