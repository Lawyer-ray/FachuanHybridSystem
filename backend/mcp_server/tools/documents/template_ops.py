"""文件模板操作 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def update_document_template(template_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """更新文书模板元数据。只传需要修改的字段。"""
    return client.put(f"/documents/templates/{template_id}", json=fields or {})  # type: ignore[return-value]


def delete_document_template(template_id: int) -> dict[str, Any]:
    """软删除文件模板。返回后端删除结果。"""
    return client.delete(f"/documents/templates/{template_id}")  # type: ignore[no-any-return]


def extract_template_placeholders(template_id: int) -> list[str]:
    """提取模板中的替换词变量。后端返回占位符名列表（``list[str]``）。"""
    return client.get(f"/documents/templates/{template_id}/placeholders")  # type: ignore[return-value]


def get_undefined_placeholders(template_id: int) -> list[str]:
    """获取模板中尚未定义的替换词。后端 ``response=list[str]``，返回名字列表。"""
    return client.get(f"/documents/templates/{template_id}/undefined-placeholders")  # type: ignore[return-value]


def list_template_library_files() -> list[dict[str, Any]]:
    """列出模板库目录下可用的 docx 文件——新建模板前查可选用哪些文件。"""
    return client.get("/documents/templates/library-files")  # type: ignore[return-value]
