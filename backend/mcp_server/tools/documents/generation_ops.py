"""文档生成操作 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def preview_supplementary_agreement_context(contract_id: int, agreement_id: int) -> dict[str, Any]:
    """预览补充协议的占位符上下文（生成前核对）。"""
    return client.get(f"/documents/contracts/{contract_id}/supplementary-agreements/{agreement_id}/preview")  # type: ignore[return-value]


def preview_archive_context(contract_id: int, template_subtype: str) -> dict[str, Any]:
    """预览归档文档的占位符上下文（生成前核对）。"""
    return client.get(
        f"/documents/contracts/{contract_id}/archive-preview", params={"template_subtype": template_subtype}
    )  # type: ignore[return-value]


def get_archive_overrides(contract_id: int, template_subtype: str = "") -> dict[str, Any]:
    """读取归档文档已保存的替换词覆盖值。"""
    return client.get(
        f"/documents/contracts/{contract_id}/archive-placeholder-overrides",
        params={"template_subtype": template_subtype},
    )  # type: ignore[return-value]


def save_archive_overrides(contract_id: int, overrides: dict[str, Any], template_subtype: str = "") -> dict[str, Any]:
    """保存归档文档的替换词覆盖值（人工修正自动提取结果）。"""
    return client.post(
        f"/documents/contracts/{contract_id}/archive-placeholder-overrides",
        params={"template_subtype": template_subtype},
        json={"overrides": overrides},
    )  # type: ignore[return-value]


def delete_archive_overrides(contract_id: int, template_subtype: str = "") -> None:
    """丢弃归档文档的替换词覆盖值（回到自动提取）。"""
    client.delete(
        f"/documents/contracts/{contract_id}/archive-placeholder-overrides",
        params={"template_subtype": template_subtype},
    )


def download_supplementary_agreement(contract_id: int, agreement_id: int) -> dict[str, Any]:
    """生成并下载补充协议为 DOCX（1MB 闸门内 base64）。"""
    content, filename, content_type = client.download(
        f"/documents/contracts/{contract_id}/supplementary-agreements/{agreement_id}/download",
        timeout=180,
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}
