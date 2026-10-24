"""案件模板绑定 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_template_bindings(case_id: int) -> dict[str, Any]:
    """查询案件的模板绑定列表。

    返回 ``{categories, total_count}``（后端 ``BindingsResponseSchema``）——
    绑定按分类分组，不是扁平数组。
    """
    return client.get(f"/cases/{case_id}/template-bindings")  # type: ignore[return-value]


def create_template_binding(case_id: int, template_id: int, group_name: str = "") -> dict[str, Any]:
    """为案件绑定文书模板。template_id 为模板ID；group_name 为分组名称。"""
    return client.post(  # type: ignore[return-value]
        f"/cases/{case_id}/template-bindings",
        json={"template_id": template_id, "group_name": group_name},
    )


def delete_template_binding(case_id: int, binding_id: int) -> dict[str, Any]:
    """删除案件的某个文书模板绑定——已按该模板生成的文书不受影响。"""
    return client.delete(f"/cases/{case_id}/template-bindings/{binding_id}")  # type: ignore[no-any-return]


def list_available_templates(case_id: int) -> list[dict[str, Any]]:
    """获取案件可用的文书模板列表（已按案件类型过滤适用性）。"""
    return client.get(f"/cases/{case_id}/available-templates")  # type: ignore[return-value]


def generate_case_template(case_id: int, template_id: int) -> dict[str, Any]:
    """基于绑定的模板为案件生成文书（异步任务,返回任务信息,稍后查产物）。"""
    return client.post(  # type: ignore[return-value]
        f"/cases/{case_id}/generate-template",
        json={"template_id": template_id},
    )


def unified_generate(case_id: int, template_ids: list[int]) -> dict[str, Any]:
    """统一生成案件文书。template_ids 为要生成的模板ID列表。"""
    return client.post(  # type: ignore[return-value]
        f"/cases/{case_id}/unified-generate",
        json={"template_ids": template_ids},
    )
