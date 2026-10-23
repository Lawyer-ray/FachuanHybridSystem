"""文档解析 MCP tools —— 把归档材料变成可检索的正文。

## 为什么重要

系统里 2000+ 份归档材料的正文此前对 agent 完全不可见：``CaseMaterial``
模型本身只有类型/方向等元数据，正文在附件文件里；而唯一能拿到正文的
``process_document_by_path`` 要求服务器上的文件路径，模型手里只有
``material_id``。结果是「材料在库里，但模型搜不到」。

本模块把 ``/document-parsing`` 的能力接出来：

- ``extract_document_text``：上传文件（base64）→ 纯文本
- ``parse_document``：上传文件 → 结构化解析（段落/表格）
- ``get_document_parsing_task``：异步解析任务状态（mineru/textin 后端）
- ``list_document_parsing_records``：历史解析记录（可按状态筛选）

正文提取是后续 ``search_materials`` 类能力的底座——先能拿到文本，
才谈得上跨材料检索。
"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client

#: 常用扩展名 → MIME。解析端点按 MIME 选后端，缺省按 PDF 处理。
#: 供其他工具模块复用（如 agent 附件白名单同口径），勿另建副本。
CONTENT_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".txt": "text/plain",
}


def content_type_for(filename: str) -> str:
    lowered = filename.lower()
    for suffix, mime in CONTENT_TYPES.items():
        if lowered.endswith(suffix):
            return mime
    return "application/octet-stream"


#: 文字层缺失时的模型引导（extract/parse 共用）。空字符串永远不能冒充成功——
#: 模型拿到空 text 容易把「扫描件无文字层」误读成「文档内容为空」并自信作答。
_NO_TEXT_LAYER_NOTICE = (
    "文档没有可提取的文字层（很可能是扫描件或图片型 PDF）。"
    "若是用户上传的对话附件，改用 read_agent_attachment(attachment_id, pages=…) "
    "获取页面原图（多模态模型可直接看图）；若是归档材料，如实告知用户该材料"
    "无文字层、无法提取文本，不要把空结果当作「文档内容为空」。"
)


def _annotate_no_text_layer(result: dict[str, Any]) -> dict[str, Any]:
    """解析「成功但文本为空」时加 no_text_layer 标记与引导，不静默透传。

    只在 ``success=True`` 且提取文本为空时触发：失败路径本就带 error，
    正常有文本的路径零改动（老行为不退化）。
    """
    if not result.get("success"):
        return result
    text = str(result.get("text") or "").strip()
    # parse 端点的正文在 sections/paragraphs，没有顶层 text 字段时不判
    if "text" not in result or text:
        return result
    metadata = dict(result.get("metadata") or {})
    metadata["no_text_layer"] = True
    return {**result, "metadata": metadata, "notice": _NO_TEXT_LAYER_NOTICE}


def extract_document_text(
    file_content_base64: str,
    filename: str,
    backend: str = "auto",
    max_length: int | None = None,
) -> dict[str, Any]:
    """提取文档的纯文本内容（用于让材料正文可被检索/引用）。

    Args:
        file_content_base64: 文件内容的 base64 编码。
        filename: 文件名（含扩展名，决定 MIME 与解析后端）。
        backend: 解析后端，``auto``（默认）/ ``local`` / ``paddleocr`` /
            ``mineru`` / ``textin``；显式选 mineru/textin 时转为异步任务，
            返回 ``task_id``，用 ``get_document_parsing_task`` 轮询。
        max_length: 可选，截断到多少字符（大材料建议显式限制，避免刷爆上下文）。

    Returns:
        ``{success, text, status, task_id?, method?, metadata?, error?}``
    """
    file_bytes = base64.b64decode(file_content_base64)
    payload: dict[str, Any] = {"backend": backend}
    if max_length is not None:
        payload["max_length"] = max_length
    result: dict[str, Any] = client.upload(
        "/document-parsing/extract-text",
        files={"file": (filename, file_bytes, content_type_for(filename))},
        data={key: str(value) for key, value in payload.items()},
    )
    return _annotate_no_text_layer(result)


def parse_document(
    file_content_base64: str,
    filename: str,
    backend: str = "auto",
    extract_tables: bool = True,
    extract_images: bool = False,
) -> dict[str, Any]:
    """结构化解析文档（段落、表格、图片位置），比纯文本提取保留更多结构。

    Args:
        file_content_base64: 文件内容的 base64 编码。
        filename: 文件名（含扩展名）。
        backend: 解析后端，``auto`` / ``local`` / ``paddleocr`` / ``mineru`` / ``textin``。
        extract_tables: 是否提取表格（默认 True）。
        extract_images: 是否提取图片（默认 False）。

    Returns:
        解析结果；mineru/textin 后端会返回 ``task_id`` 供轮询。
    """
    file_bytes = base64.b64decode(file_content_base64)
    data = {
        "backend": backend,
        "extract_tables": str(extract_tables).lower(),
        "extract_images": str(extract_images).lower(),
    }
    result: dict[str, Any] = client.upload(
        "/document-parsing/parse",
        files={"file": (filename, file_bytes, content_type_for(filename))},
        data=data,
    )
    return _annotate_no_text_layer(result)


def get_document_parsing_task(task_id: str) -> dict[str, Any]:
    """查询异步文档解析任务的进度与结果。

    Args:
        task_id: ``parse_document`` / ``extract_document_text`` 返回的任务 ID。
    """
    result: dict[str, Any] = client.get(f"/document-parsing/task/{task_id}")
    return result


def list_document_parsing_records(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """查询历史文档解析记录。

    Args:
        status: 可选，按状态筛选（如 pending / completed / failed）。
        page: 页码，从 1 开始。
        page_size: 每页条数，默认 20。
    """
    params: dict[str, Any] = {"page": max(1, page), "page_size": max(1, min(page_size, 200))}
    if status:
        params["status"] = status
    result: dict[str, Any] = client.get("/document-parsing/records", params=params)
    return result
