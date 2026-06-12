"""文档转换 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_conversion_progress(job_id: str) -> dict[str, Any]:
    """查询文档转换任务进度。"""
    return client.get(f"/doc-converter/jobs/{job_id}")  # type: ignore[return-value]


def cancel_conversion_job(job_id: str) -> dict[str, Any]:
    """取消进行中的文档转换任务。"""
    return client.post(f"/doc-converter/jobs/{job_id}/cancel", json={})  # type: ignore[return-value]


def download_converted_files(job_id: str) -> dict[str, Any]:
    """下载转换后的文件（ZIP）。返回 {filename, content_type, data_base64}。"""
    import base64

    content, filename, content_type = client.download(f"/doc-converter/jobs/{job_id}/download")
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def delete_conversion_job(job_id: str) -> None:
    """删除转换任务及其关联文件。"""
    client.delete(f"/doc-converter/jobs/{job_id}")


def doc_converter_health_check() -> dict[str, Any]:
    """检查 LibreOffice 服务是否可用。"""
    return client.get("/doc-converter/health")  # type: ignore[return-value]


def save_to_directory(job_id: str, directory: str) -> dict[str, Any]:
    """将转换后的文件保存到指定目录。"""
    return client.post(f"/doc-converter/jobs/{job_id}/save-to-dir", json={"target_dir": directory})  # type: ignore[return-value]
