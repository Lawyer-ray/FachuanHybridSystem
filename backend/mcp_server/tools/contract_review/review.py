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
    """查询合同审查任务状态。status: uploaded/parties_identified/confirmed/processing/completed/failed/extraction_failed。"""
    return client.get(f"/contract-review/{task_id}/status")  # type: ignore[no-any-return]


def get_review_models() -> dict[str, Any]:
    """获取可用的 LLM 模型列表。

    原样返回后端 ``{models, is_fallback, error_message}``——``is_fallback`` /
    ``error_message`` 是判断「模型清单是否降级」的唯一线索，之前被裁掉后
    模型无法分辨「没有模型」和「拉取失败」。
    """
    return client.get("/contract-review/models")  # type: ignore[no-any-return]


def confirm_party(
    task_id: str,
    represented_party: str,
    reviewer_name: str | None = None,
    party_a: str | None = None,
    party_b: str | None = None,
    party_c: str | None = None,
    party_d: str | None = None,
) -> dict[str, Any]:
    """确认本次审查代表哪一方当事人。

    后端 ``ConfirmPartyIn`` 的必填字段是 ``represented_party``（被代理方）。
    早前工具传 ``party_name`` / ``party_type``，字段名不符，调用必然 422。

    Args:
        task_id: 审查任务 ID。
        represented_party: 我方代表的当事人（通常是 party_a 或 party_b 的取值）。
        reviewer_name: 可选，审查人署名。
        party_a/party_b/party_c/party_d: 可选，覆盖解析出的各方名称。
    """
    payload: dict[str, Any] = {"represented_party": represented_party}
    if reviewer_name:
        payload["reviewer_name"] = reviewer_name
    for key, value in (("party_a", party_a), ("party_b", party_b), ("party_c", party_c), ("party_d", party_d)):
        if value:
            payload[key] = value
    return client.post(f"/contract-review/{task_id}/confirm-party", json=payload)  # type: ignore[no-any-return]


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


def normalize_contract_format(task_id: str, reference_file: str | None = None) -> dict[str, Any]:
    """对**已上传的审查任务**做合同格式规范化，产出可下载的标准化 DOCX。

    后端 ``FormatNormalizeIn`` 需要 ``{task_id, reference_file?}``——它复用审查
    任务里已解析的合同，不是重新上传文件。早前工具把「上传文件」的 multipart
    打到这个端点并声明返回 task_id，与后端语义完全不符，调用必然 422。

    正确的两步链路：先 ``upload_contract_for_review`` 拿到 task_id，再调本工具。

    Args:
        task_id: 既有合同审查任务 ID（UUID 字符串）。
        reference_file: 可选，参考文档路径（用于对齐格式）。
    """
    payload: dict[str, Any] = {"task_id": task_id}
    if reference_file:
        payload["reference_file"] = reference_file
    return client.post("/contract-review/format/normalize", json=payload)  # type: ignore[no-any-return]


def download_normalized_result(task_id: str) -> dict[str, Any]:
    """下载标准化后的合同文件。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/contract-review/format/{task_id}/download-normalized")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }
