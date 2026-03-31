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
    return client.get("/documents/templates", params=params)  # type: ignore[return-value]


def get_document_template(template_id: int) -> dict[str, Any]:
    """获取文件模板详情。"""
    return client.get(f"/documents/templates/{template_id}")  # type: ignore[return-value]


def create_document_template(
    name: str,
    template_type: str,
    case_type: str = "",
    content: str = "",
) -> dict[str, Any]:
    """创建文件模板。"""
    payload: dict[str, Any] = {"name": name, "template_type": template_type}
    if case_type:
        payload["case_type"] = case_type
    if content:
        payload["content"] = content
    return client.post("/documents/templates", json=payload)  # type: ignore[return-value]


def list_folder_templates(
    template_type: str | None = None,
    case_type: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    """获取文件夹模板列表。"""
    params: dict[str, Any] = {}
    if template_type:
        params["template_type"] = template_type
    if case_type:
        params["case_type"] = case_type
    if is_active is not None:
        params["is_active"] = is_active
    return client.get("/documents/folder-templates", params=params)  # type: ignore[return-value]


def list_placeholders(is_active: bool | None = None) -> list[dict[str, Any]]:
    """获取替换词列表。"""
    params: dict[str, Any] = {}
    if is_active is not None:
        params["is_active"] = is_active
    return client.get("/documents/placeholders", params=params)  # type: ignore[return-value]


def preview_placeholders(
    contract_id: int,
    keys: str = "",
) -> dict[str, Any]:
    """预览合同的替换词值。keys: 逗号分隔的键名，为空则返回全部。"""
    params: dict[str, Any] = {}
    if keys:
        params["keys"] = keys
    return client.get(f"/documents/placeholders/preview/{contract_id}", params=params)  # type: ignore[return-value]


def preview_contract_context(contract_id: int) -> dict[str, Any]:
    """预览合同占位符上下文数据。"""
    return client.get(f"/documents/contracts/{contract_id}/preview")  # type: ignore[return-value]


def download_contract_document(contract_id: int) -> dict[str, Any]:
    """下载合同文档（DOCX）。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(
        f"/documents/contracts/{contract_id}/download"
    )
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def download_contract_folder(contract_id: int) -> dict[str, Any]:
    """下载合同文件夹（ZIP）。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(
        f"/documents/contracts/{contract_id}/folder/download"
    )
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }
