"""财产保全材料生成 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def download_preservation_application(case_id: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成并下载财产保全申请书（DOCX）。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/preservation/application/download",
        method="POST",
        json=extra or {},
        timeout=180,
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_delay_delivery_application(case_id: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成并下载暂缓送达申请书（DOCX）。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/preservation/delay-delivery/download",
        method="POST",
        json=extra or {},
        timeout=180,
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_full_preservation_package(case_id: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """下载完整财产保全材料包（ZIP,含申请书/担保函等;LLM 链路,耗时较长）。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/preservation/package/download",
        method="POST",
        json=extra or {},
        timeout=180,
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}
