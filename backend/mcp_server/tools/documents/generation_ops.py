"""文档生成操作 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def preview_supplementary_agreement_context(contract_id: int, agreement_id: int) -> dict[str, Any]:
    """预览补充协议的替换词上下文。"""
    return client.get(f"/documents/contracts/{contract_id}/supplementary-agreements/{agreement_id}/preview")  # type: ignore[return-value]


def preview_archive_context(contract_id: int, template_subtype: str) -> dict[str, Any]:
    """预览归档文档替换词上下文。"""
    return client.get(
        f"/documents/contracts/{contract_id}/archive-preview", params={"template_subtype": template_subtype}
    )  # type: ignore[return-value]


def get_archive_overrides(contract_id: int) -> dict[str, Any]:
    """获取归档文档保存的替换词覆盖值。"""
    return client.get(f"/documents/contracts/{contract_id}/archive-placeholder-overrides")  # type: ignore[return-value]


def save_archive_overrides(contract_id: int, overrides: dict[str, Any]) -> dict[str, Any]:
    """保存归档文档替换词覆盖值。"""
    return client.post(f"/documents/contracts/{contract_id}/archive-placeholder-overrides", json=overrides)  # type: ignore[return-value]


def delete_archive_overrides(contract_id: int) -> None:
    """删除（丢弃）归档文档替换词覆盖值。"""
    client.delete(f"/documents/contracts/{contract_id}/archive-placeholder-overrides")


def download_supplementary_agreement(contract_id: int, agreement_id: int) -> dict[str, Any]:
    """下载补充协议为 DOCX。"""
    content, filename, content_type = client.download(
        f"/documents/contracts/{contract_id}/supplementary-agreements/{agreement_id}/download"
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}
