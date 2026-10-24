"""案件模板绑定 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_template_bindings(case_id: int) -> dict[str, Any]:
    """查询案件的模板绑定列表。

    返回 ``{categories, total_count}``（后端 ``BindingsResponseSchema``）——
    绑定按分类分组，不是扁平数组。
    """
    return client.get(f"/cases/{case_id}/template-bindings")  # type: ignore[no-any-return]


def create_template_binding(case_id: int, template_id: int) -> dict[str, Any]:
    """为案件绑定文书模板（手动绑定记录）。

    template_id 为模板 ID——绑定没有分组概念,旧签名的 ``group_name``
    参数从未生效（端点 ``BindTemplateRequestSchema`` 只声明 template_id,
    2026-10-25 移除）。
    """
    return client.post(  # type: ignore[no-any-return]
        f"/cases/{case_id}/template-bindings",
        json={"template_id": template_id},
    )


def delete_template_binding(case_id: int, binding_id: int) -> dict[str, Any]:
    """删除案件的某个文书模板绑定——已按该模板生成的文书不受影响。"""
    return client.delete(f"/cases/{case_id}/template-bindings/{binding_id}")  # type: ignore[no-any-return]


def list_available_templates(case_id: int) -> dict[str, Any]:
    """获取案件可用的文书模板列表（已按案件类型过滤适用性）。"""
    return list_result(client.get(f"/cases/{case_id}/available-templates"))


def generate_case_template(case_id: int, template_id: int) -> dict[str, Any]:
    """基于绑定的模板为案件生成文书（异步任务,返回任务信息,稍后查产物）。"""
    return client.post(  # type: ignore[no-any-return]
        f"/cases/{case_id}/generate-template",
        json={"template_id": template_id},
    )


def unified_generate(
    case_id: int,
    template_id: int | None = None,
    function_code: str | None = None,
    client_id: int | None = None,
    client_ids: list[int] | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """统一生成案件文书（template_id 与 function_code 二选一）。

    Args:
        case_id: 案件 ID。
        template_id: 模板 ID（优先使用）。
        function_code: 功能标识（template_id 为空时使用,如授权类文书）。
        client_id: 当事人 ID（法定代表人身份证明书/单独授权用）。
        client_ids: 当事人 ID 列表（合并授权用）。
        mode: 授权模式：``individual`` 单独 / ``combined`` 合并。

    旧签名只有 ``template_ids`` 列表参数——端点 ``UnifiedGenerateRequest``
    根本没有该字段,每次调用都被静默当成空请求（2026-10-25 重写）。
    """
    payload: dict[str, Any] = {}
    if template_id is not None:
        payload["template_id"] = template_id
    if function_code:
        payload["function_code"] = function_code
    if client_id is not None:
        payload["client_id"] = client_id
    if client_ids is not None:
        payload["client_ids"] = client_ids
    if mode:
        payload["mode"] = mode
    return client.post(  # type: ignore[no-any-return]
        f"/cases/{case_id}/unified-generate",
        json=payload,
    )
