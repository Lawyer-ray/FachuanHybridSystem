"""授权委托材料生成 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def download_authority_letter(case_id: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """下载所函（DOCX,1MB 闸门内返回 base64）。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/authorization/letter/download",
        method="POST",
        json=extra or {},
        timeout=180,
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_legal_rep_certificate(case_id: int, client_id: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """下载法定代表人身份证明（DOCX）。

    Args:
        case_id: 案件 ID。
        client_id: 客户(单位) ID——须是本案客户。
        extra: 可选,透传给后端的附加字段(原样并入请求体)。
    """
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/authorization/legal-rep-certificate/{client_id}/download",
        method="POST",
        json=extra or {},
        timeout=180,
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_power_of_attorney_combined(
    case_id: int, client_ids: list[int], extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """下载多客户合并版授权委托书（DOCX）。

    Args:
        case_id: 案件 ID。
        client_ids: 参与合并的客户 ID 列表(≥2 才有合并意义)。
        extra: 可选,透传给后端的附加字段(原样并入请求体)。
    """
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/authorization/power-of-attorney/combined/download",
        method="POST",
        json={"client_ids": client_ids, **(extra or {})},
        timeout=180,
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_authorization_package(case_id: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """下载完整授权委托材料包（ZIP）。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/authorization/package/download",
        method="POST",
        json=extra or {},
        timeout=180,
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_power_of_attorney(case_id: int, client_id: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """下载单个客户的授权委托书（DOCX）。

    Args:
        case_id: 案件 ID。
        client_id: 客户 ID——须是本案客户。
        extra: 可选,透传给后端的附加字段(原样并入请求体)。
    """
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/authorization/power-of-attorney/{client_id}/download",
        method="POST",
        json=extra or {},
        timeout=180,
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}
