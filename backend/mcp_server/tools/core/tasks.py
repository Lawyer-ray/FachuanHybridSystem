"""异步任务统一状态查询 MCP tools。

## 为什么需要统一入口

系统里有至少六个子系统各自维护「异步任务/会话」，字段名各不相同：

| 子系统 | 表 / 端点 | 状态字段 |
|---|---|---|
| PDF 拆页 | ``PdfSplitJob`` | ``status`` + ``progress`` + ``current_page`` |
| OA 立案 | ``FilingSession`` | ``status`` |
| OA 归档 | ``ArchiveSession`` | ``status`` |
| OA 盖章 | ``StampSession`` | ``status`` |
| 诉讼文书 | ``LitigationTask`` | ``status`` |
| 文档转换 | ``DocConverterJob`` | ``status`` |

模型此前每次问「那个任务好了吗」都得先猜是哪个子系统、再猜字段名。
本模块提供 ``get_async_task_status(task_id)``：用一个 ``kind:task_id``
的统一寻址方式分派到对应端点，并把结果归一成同一张表：

    {kind, task_id, status, progress, finished, failed, error, raw}

``raw`` 保留后端原始返回，模型需要细节时仍可查看——归一化不隐藏信息，
只保证顶层字段稳定。
"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client

#: 支持的子系统前缀 → (端点模板, 是否已完成判定字段)
_KINDS: dict[str, str] = {
    "pdf_split": "/pdf-splitting/jobs/{task_id}",
    "archive": "/oa-archive/session/{task_id}",
    "stamp": "/oa-stamp/session/{task_id}",
    "litigation": "/litigation/tasks/{task_id}",
}

#: 各子系统里表示「已终结」的状态值（其余按进行中处理）
_DONE_STATUSES = frozenset({"completed", "success", "succeeded", "done", "finished"})
_FAILED_STATUSES = frozenset({"failed", "error", "cancelled", "canceled", "timeout"})


def get_async_task_status(kind: str, task_id: str) -> dict[str, Any]:
    """查询任意子系统的异步任务状态（统一字段）。

    Args:
        kind: 子系统标识：
            ``pdf_split``（PDF 拆页）/ ``archive``（OA 归档）/
            ``stamp``（OA 盖章）/ ``litigation``（诉讼文书生成）。
        task_id: 该子系统里的任务/会话 ID。

    Returns:
        ``{kind, task_id, status, progress, finished, failed, error, raw}``。
        ``progress`` 在子系统未提供时为 ``None``（不要当成 0）。
    """
    key = kind.strip().lower()
    template = _KINDS.get(key)
    if template is None:
        raise ValueError(f"未知的 kind={kind!r}；支持: {', '.join(sorted(_KINDS))}")

    raw: dict[str, Any] = client.get(template.format(task_id=task_id))
    if not isinstance(raw, dict):
        raw = {"data": raw}

    status = str(raw.get("status") or "").lower()
    progress = raw.get("progress")
    if progress is None and isinstance(raw.get("processed_pages"), int) and isinstance(raw.get("total_pages"), int):
        total = raw["total_pages"] or 0
        progress = round(raw["processed_pages"] * 100 / total) if total else None

    return {
        "kind": key,
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "finished": status in _DONE_STATUSES,
        "failed": status in _FAILED_STATUSES,
        "error": raw.get("error") or raw.get("error_message") or raw.get("message") or None,
        "raw": raw,
    }


def list_doc_converter_jobs(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """列出 DOC→DOCX 转换任务（含进行中与历史）。

    Args:
        page: 页码，从 1 开始。
        page_size: 每页条数，默认 20。
    """
    return client.get(  # type: ignore[no-any-return]
        "/doc-converter/jobs",
        params={"page": max(1, page), "page_size": max(1, min(page_size, 200))},
    )


def create_doc_converter_job(files: list[dict[str, Any]]) -> dict[str, Any]:
    """创建 DOC→DOCX 转换任务。

    Args:
        files: 待转换文件列表，每项含 ``filename`` 与 ``content_base64``。

    Notes:
        文件以 base64 传入；后端按 multipart 接收，这里逐条解码后上传。
        端点只收文件列表,无其他选项字段（旧版的 ``options`` 参数从未被
        端点读取,已移除）。
    """
    import base64

    # 端点声明 files: list[UploadedFile] = File(...)——多文件必须用
    # **同名字段 files 重复**传递(httpx files 列表形态)。早前用
    # file_0/file_1 逐个编号,端点拿不到 files 字段,每次调用必 422
    # ``Field required: files``(2026-10-25 修复)。
    files_payload: list[tuple[str, tuple[str, bytes, str]]] = [
        (
            "files",
            (
                str(item.get("filename") or "upload.doc"),
                base64.b64decode(str(item.get("content_base64") or "")),
                "application/msword",
            ),
        )
        for item in files
    ]
    return client.upload(  # type: ignore[no-any-return]
        "/doc-converter/jobs", files=files_payload
    )


def list_litigation_sessions(
    case_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """列出诉讼文书生成会话。

    Args:
        case_id: 可选，按案件筛选。
        status: 可选，按状态筛选。
        page: 页码，从 1 开始。
        page_size: 每页条数，默认 20。
    """
    params: dict[str, Any] = {"page": max(1, page), "page_size": max(1, min(page_size, 200))}
    if case_id is not None:
        params["case_id"] = case_id
    if status:
        params["status"] = status
    return client.get("/litigation/sessions", params=params)  # type: ignore[no-any-return]


def list_pending_court_document_tasks(limit: int = 50) -> dict[str, Any]:
    """列出待人工处理的法院文书识别任务（自动关联案件失败的那些）。

    Args:
        limit: 最多返回条数，默认 50。
    """
    return client.get(  # type: ignore[no-any-return]
        "/document-recognition/court-document/tasks/pending",
        params={"limit": max(1, limit)},
    )
