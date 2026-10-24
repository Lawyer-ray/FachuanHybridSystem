"""文书生产 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def list_document_templates(
    template_type: str | None = None,
    case_type: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    """获取文件模板列表，支持按类型/案件类型/启用状态过滤。"""
    params: dict[str, Any] = {}
    if template_type:
        params["template_type"] = template_type
    if case_type:
        params["case_type"] = case_type
    if is_active is not None:
        params["is_active"] = is_active
    return client.get("/documents/templates", params=params)  # type: ignore[no-any-return]


def get_document_template(template_id: int) -> dict[str, Any]:
    """获取文书模板详情（含占位符定义）。"""
    return client.get(f"/documents/templates/{template_id}")  # type: ignore[no-any-return]


def create_document_template(
    name: str,
    template_type: str,
    contract_sub_type: str | None = None,
    case_sub_type: str | None = None,
    archive_sub_type: str | None = None,
    file_path: str | None = None,
    case_types: list[str] | None = None,
    case_stages: list[str] | None = None,
    contract_types: list[str] | None = None,
    is_active: bool = True,
) -> dict[str, Any]:
    """登记文书模板元数据（模板正文是已上传的 docx 文件）。

    Args:
        name: 模板名称。
        template_type: contract 合同文件模板 / case 案件文件模板 /
            archive 归档文件模板。
        contract_sub_type / case_sub_type / archive_sub_type: 对应类型的
            子类型（template_type 决定哪个生效）。
        file_path: 模板 docx 的存储路径——**模板正文来自文件,不是内联
            文本**;新模板应先落文件再登记。缺省则模板暂无正文。
        case_types: 适用案件类型列表（civil/administrative/criminal/
            execution/bankruptcy/all）。
        case_stages: 适用案件阶段列表（first_trial/second_trial/…英文键）。
        contract_types: 适用合同子类型列表。
        is_active: 是否启用,默认 True。

    2026-10-25 修复:旧签名的 ``case_type``（单数）与 ``content``（内联
    正文）从未生效——端点 ``DocumentTemplateIn`` 没有这两个字段。
    """
    payload: dict[str, Any] = {"name": name, "template_type": template_type, "is_active": is_active}
    if contract_sub_type:
        payload["contract_sub_type"] = contract_sub_type
    if case_sub_type:
        payload["case_sub_type"] = case_sub_type
    if archive_sub_type:
        payload["archive_sub_type"] = archive_sub_type
    if file_path:
        payload["file_path"] = file_path
    if case_types is not None:
        payload["case_types"] = case_types
    if case_stages is not None:
        payload["case_stages"] = case_stages
    if contract_types is not None:
        payload["contract_types"] = contract_types
    return client.post("/documents/templates", json=payload)  # type: ignore[no-any-return]


def list_folder_templates(
    template_type: str | None = None,
    case_type: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    """获取文件夹模板列表（新案件的目录结构模板）。"""
    params: dict[str, Any] = {}
    if template_type:
        params["template_type"] = template_type
    if case_type:
        params["case_type"] = case_type
    if is_active is not None:
        params["is_active"] = is_active
    return client.get("/documents/folder-templates", params=params)  # type: ignore[no-any-return]


def list_placeholders(is_active: bool | None = None) -> list[dict[str, Any]]:
    """获取替换词（占位符）列表——文书生成的变量字典。"""
    params: dict[str, Any] = {}
    if is_active is not None:
        params["is_active"] = is_active
    return client.get("/documents/placeholders", params=params)  # type: ignore[no-any-return]


def preview_placeholders(
    contract_id: int,
    keys: str = "",
) -> dict[str, Any]:
    """预览合同的替换词值。keys: 逗号分隔的键名，为空则返回全部。"""
    params: dict[str, Any] = {}
    if keys:
        params["keys"] = keys
    return client.get(f"/documents/placeholders/preview/{contract_id}", params=params)  # type: ignore[no-any-return]


def preview_contract_context(contract_id: int) -> dict[str, Any]:
    """预览合同文书的占位符上下文（生成前核对数据会填成什么）。"""
    return client.get(f"/documents/contracts/{contract_id}/preview")  # type: ignore[no-any-return]


def download_contract_document(contract_id: int) -> dict[str, Any]:
    """下载合同文档（DOCX）。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/documents/contracts/{contract_id}/download")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def download_contract_folder(contract_id: int) -> dict[str, Any]:
    """下载合同文件夹（ZIP）。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/documents/contracts/{contract_id}/folder/download")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }
