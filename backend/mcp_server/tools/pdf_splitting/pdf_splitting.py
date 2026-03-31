"""PDF 拆解 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def create_pdf_split_job(
    file_base64: str,
    filename: str,
    template_key: str = "filing_materials_v1",
    split_mode: str = "content_analysis",
    ocr_profile: str = "balanced",
) -> dict[str, Any]:
    """上传 PDF 并创建拆解任务。file_base64 为文件的 base64 编码；split_mode: content_analysis（内容识别）或 by_page（按页）；ocr_profile: balanced/fast/accurate。返回 job_id。"""
    file_bytes = base64.b64decode(file_base64)
    return client.upload(
        "/pdf-splitting/jobs",
        files={"file": (filename, file_bytes, "application/pdf")},
        data={
            "template_key": template_key,
            "split_mode": split_mode,
            "ocr_profile": ocr_profile,
        },
    )  # type: ignore[return-value]


def get_pdf_split_job(job_id: str) -> dict[str, Any]:
    """查询 PDF 拆解任务状态和结果。status: pending/processing/completed/failed。"""
    return client.get(f"/pdf-splitting/jobs/{job_id}")  # type: ignore[return-value]


def confirm_pdf_split(job_id: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
    """确认 PDF 拆解分段结果，触发最终打包。segments 为分段列表，每项包含 page_start、page_end、segment_type、filename 等字段。"""
    return client.post(f"/pdf-splitting/jobs/{job_id}/confirm", json={"segments": segments})  # type: ignore[return-value]


def cancel_pdf_split(job_id: str) -> dict[str, Any]:
    """取消 PDF 拆解任务。"""
    return client.post(f"/pdf-splitting/jobs/{job_id}/cancel", json={})  # type: ignore[return-value]


def download_pdf_split_result(job_id: str) -> dict[str, Any]:
    """下载 PDF 拆解结果 ZIP 压缩包。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/pdf-splitting/jobs/{job_id}/download")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }
