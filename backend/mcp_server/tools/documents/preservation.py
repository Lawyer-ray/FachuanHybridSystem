"""财产保全材料生成 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def download_preservation_application(case_id: int, **extra: Any) -> dict[str, Any]:
    """下载财产保全申请书。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/preservation/application/download", method="POST", json=extra
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_delay_delivery_application(case_id: int, **extra: Any) -> dict[str, Any]:
    """下载暂缓送达申请书。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/preservation/delay-delivery/download", method="POST", json=extra
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def download_full_preservation_package(case_id: int, **extra: Any) -> dict[str, Any]:
    """下载完整财产保全材料包（ZIP）。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/preservation/package/download", method="POST", json=extra
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}
