"""诉讼文书生成 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def generate_complaint(case_id: int, **extra: Any) -> dict[str, Any]:
    """生成起诉状（LLM 结构化链）。"""
    return client.post("/documents/litigation/complaint/generate", json={"case_id": case_id, **extra})  # type: ignore[return-value]


def generate_defense(case_id: int, **extra: Any) -> dict[str, Any]:
    """生成答辩状（LLM 结构化链）。"""
    return client.post("/documents/litigation/defense/generate", json={"case_id": case_id, **extra})  # type: ignore[return-value]


def preview_litigation_context(case_id: int, litigation_type: str) -> dict[str, Any]:
    """预览诉讼文书替换词上下文。litigation_type: complaint / defense。"""
    return client.get(f"/documents/cases/{case_id}/litigation/{litigation_type}/preview")  # type: ignore[return-value]


def download_litigation_document(case_id: int, litigation_type: str, **extra: Any) -> dict[str, Any]:
    """生成并下载诉讼文书为 DOCX。"""
    content, filename, content_type = client.download(
        f"/documents/cases/{case_id}/litigation/{litigation_type}/download", method="POST", json=extra
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}
