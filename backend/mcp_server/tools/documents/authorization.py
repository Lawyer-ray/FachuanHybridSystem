"""授权委托材料生成 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def download_authority_letter(case_id: int, **extra: Any) -> dict[str, Any]:
    """下载所函。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/authorization/letter/download", method="POST", json=extra
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_legal_rep_certificate(case_id: int, client_id: int, **extra: Any) -> dict[str, Any]:
    """下载法定代表人身份证明。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/authorization/legal-rep-certificate/{client_id}/download",
        method="POST",
        json=extra,
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_power_of_attorney_combined(case_id: int, client_ids: list[int], **extra: Any) -> dict[str, Any]:
    """下载合并的授权委托书。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/authorization/power-of-attorney/combined/download",
        method="POST",
        json={"client_ids": client_ids, **extra},
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_authorization_package(case_id: int, **extra: Any) -> dict[str, Any]:
    """下载完整授权委托材料包（ZIP）。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/authorization/package/download", method="POST", json=extra
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_power_of_attorney(case_id: int, client_id: int, **extra: Any) -> dict[str, Any]:
    """下载单个客户的授权委托书。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/authorization/power-of-attorney/{client_id}/download", method="POST", json=extra
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}
