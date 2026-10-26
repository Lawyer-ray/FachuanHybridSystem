"""文件夹模板操作 MCP tools"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from mcp_server.client import client

#: 与 apps/documents/models/choices 的 TextChoices 逐值对账(门禁 test_schema_param_descriptions)。
_FolderTemplateTypeL = Literal["contract", "case", "archive"]
_FolderCaseTypeL = Literal["civil", "administrative", "criminal", "execution", "bankruptcy", "all"]


def get_folder_template(template_id: int) -> dict[str, Any]:
    """获取文件夹模板详情（目录结构树）。"""
    return client.get(f"/documents/folder-templates/{template_id}")  # type: ignore[no-any-return]


def create_folder_template(
    name: Annotated[str, Field(description="模板名称")],
    template_type: Annotated[_FolderTemplateTypeL | None, Field(description="contract 合同/case 案件/archive 归档")] = None,
    case_types: Annotated[list[_FolderCaseTypeL] | None, Field(description="适用案件类型列表(all=通用)")] = None,
    case_stages: Annotated[list[str] | None, Field(description="适用案件阶段列表(英文键,见 CaseStage 18 值)")] = None,
    contract_types: Annotated[list[str] | None, Field(description="适用合同类型列表")] = None,
    structure: Annotated[dict[str, Any] | None, Field(description="目录结构树(节点含 name/children 等;结构复杂时建议先 get_folder_template 参考现有样例)")] = None,
    is_default: Annotated[bool | None, Field(description="是否默认模板")] = None,
    is_active: Annotated[bool | None, Field(description="是否启用")] = None,
) -> dict[str, Any]:
    """创建文件夹模板。

    Args:
        name: 模板名称（必填）。
        template_type: 模板类型。
        case_types: 适用案件类型列表（civil / administrative / criminal /
            execution / bankruptcy / all 通用）。
        case_stages: 适用案件阶段列表。
        contract_types: 适用合同类型列表。
        structure: 目录结构树（节点含 name / children 等）。
        is_default: 是否默认模板。
        is_active: 是否启用。
    """
    payload: dict[str, Any] = {"name": name}
    for field in (
        "template_type",
        "case_types",
        "case_stages",
        "contract_types",
        "structure",
        "is_default",
        "is_active",
    ):
        value = locals()[field]
        if value is not None:
            payload[field] = value
    return client.post("/documents/folder-templates", json=payload)  # type: ignore[no-any-return]


def update_folder_template(template_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """更新文件夹模板（目录结构等）。只传需要修改的字段。"""
    return client.put(f"/documents/folder-templates/{template_id}", json=fields or {})  # type: ignore[no-any-return]


def delete_folder_template(template_id: int) -> dict[str, Any]:
    """软删除文件夹模板。返回后端删除结果。"""
    return client.delete(f"/documents/folder-templates/{template_id}")  # type: ignore[no-any-return]


def validate_folder_structure(template_id: int) -> dict[str, Any]:
    """校验文件夹模板的结构合法性（改完模板后自检）。"""
    return client.post(f"/documents/folder-templates/{template_id}/validate", json={})  # type: ignore[no-any-return]
