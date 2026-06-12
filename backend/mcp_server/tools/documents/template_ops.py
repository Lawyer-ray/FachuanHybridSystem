"""文件模板操作 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def update_document_template(template_id: int, **fields: Any) -> dict[str, Any]:
    """更新文件模板。"""
    return client.put(f"/documents/templates/{template_id}", json=fields)  # type: ignore[return-value]


def delete_document_template(template_id: int) -> None:
    """软删除文件模板。"""
    client.delete(f"/documents/templates/{template_id}")


def extract_template_placeholders(template_id: int) -> dict[str, Any]:
    """提取模板中的替换词变量。"""
    return client.get(f"/documents/templates/{template_id}/placeholders")  # type: ignore[return-value]


def get_undefined_placeholders(template_id: int) -> dict[str, Any]:
    """获取模板中尚未定义的替换词。"""
    return client.get(f"/documents/templates/{template_id}/undefined-placeholders")  # type: ignore[return-value]


def list_template_library_files() -> list[dict[str, Any]]:
    """列出模板库中可用的 docx 文件。"""
    return client.get("/documents/templates/library-files")  # type: ignore[return-value]
