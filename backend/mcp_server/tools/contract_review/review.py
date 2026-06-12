"""合同审查 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def upload_contract_for_review(
    file_content_base64: str,
    filename: str,
    model_name: str = "",
) -> dict[str, Any]:
    """上传合同文件并创建审查任务。file_content_base64: 文件内容的 base64 编码。返回 task_id。"""
    content = base64.b64decode(file_content_base64)
    content_type = (
        "application/pdf"
        if filename.endswith(".pdf")
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return client.upload(  # type: ignore[no-any-return]
        "/contract-review/upload",
        files={"file": (filename, content, content_type)},
        data={"model_name": model_name} if model_name else {},
    )


def get_review_status(task_id: str) -> dict[str, Any]:
    """查询合同审查任务状态。status: pending/extracting/reviewing/completed/failed。"""
    return client.get(f"/contract-review/{task_id}/status")  # type: ignore[no-any-return]


def get_review_models() -> list[dict[str, str]]:
    """获取可用的 LLM 模型列表。"""
    result: dict[str, Any] = client.get("/contract-review/models")
    return list(result.get("models", []))


def confirm_party(task_id: str, party_name: str, party_type: str) -> dict[str, Any]:
    """确认合同当事人信息。party_type: plaintiff（原告）/ defendant（被告）/ third_party（第三人）。"""
    return client.post(  # type: ignore[return-value]
        f"/contract-review/{task_id}/confirm-party",
        json={"party_name": party_name, "party_type": party_type},
    )


def download_review_result(task_id: str) -> dict[str, Any]:
    """下载合同审查结果文件。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/contract-review/{task_id}/download")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def download_review_original(task_id: str) -> dict[str, Any]:
    """下载合同审查的原始文件。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/contract-review/{task_id}/download-original")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def normalize_contract_format(file_content_base64: str, filename: str) -> dict[str, Any]:
    """将合同文件转换为标准化格式。返回 task_id。"""
    file_bytes = base64.b64decode(file_content_base64)
    content_type = (
        "application/pdf"
        if filename.endswith(".pdf")
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return client.upload(  # type: ignore[return-value]
        "/contract-review/normalize",
        files={"file": (filename, file_bytes, content_type)},
    )


def download_normalized_result(task_id: str) -> dict[str, Any]:
    """下载标准化后的合同文件。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/contract-review/{task_id}/download-normalized")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }
