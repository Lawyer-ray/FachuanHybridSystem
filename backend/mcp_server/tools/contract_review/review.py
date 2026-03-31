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
    content_type = "application/pdf" if filename.endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return client.upload(  # type: ignore[return-value]
        "/contract-review/upload",
        files={"file": (filename, content, content_type)},
        data={"model_name": model_name} if model_name else {},
    )


def get_review_status(task_id: str) -> dict[str, Any]:
    """查询合同审查任务状态。status: pending/extracting/reviewing/completed/failed。"""
    return client.get(f"/contract-review/{task_id}/status")  # type: ignore[return-value]


def get_review_models() -> list[dict[str, str]]:
    """获取可用的 LLM 模型列表。"""
    return client.get("/contract-review/models")  # type: ignore[return-value]
