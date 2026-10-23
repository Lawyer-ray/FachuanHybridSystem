"""合同绑定文件夹文件读取 —— 拖拽引用（folder-ref）型附件的正文 / 原件页图。

## 与 read_agent_attachment 的关系

编排完全共用（``_read_file_via_source``：文本探针、扫描件回落、分段、
限额），只有数据源不同：附件版读 ``/agent/attachments/{id}/*``，本工具读
``/agent/folder-refs/*``——即合同绑定文件夹里的**原文件**（不复制，始终
读到最新版；路径即归属）。权限与目录树同口径（行级 ACL：团队共享合同
的协办律师同样可读）。

## 为什么独立成工具而不是让模型拼 URL

用户从详情页目录树拖入文件后，消息里会出现
``[已引用文件：… (attachment_id=…, contract_id=…, subpath=…)]``——模型按
引用参数调用本工具，与「上传附件走 read_agent_attachment」两条链路各自
明确，互不猜测。
"""

from __future__ import annotations

import base64
from typing import Any

from mcp.types import ImageContent, TextContent

from mcp_server.client import client

from ..core.agent_attachments import (
    DEFAULT_DPI,
    DEFAULT_FORMAT,
    DEFAULT_MAX_LENGTH,
    ERROR_FORBIDDEN,
    ERROR_NOT_FOUND,
    ERROR_PARSE_EMPTY,
    MAX_PAGES_CEILING,
    _clamp_dpi,
    _classify_http_error,
    _consume_pages_response,
    _pages_param,
    _read_file_via_source,
)


def read_folder_file(
    contract_id: int,
    subpath: str,
    max_length: int = DEFAULT_MAX_LENGTH,
    start: int = 0,
    pages: str | list[int] | None = None,
    dpi: int = DEFAULT_DPI,
    format: str = DEFAULT_FORMAT,
    max_pages: int = MAX_PAGES_CEILING,
) -> list[TextContent | ImageContent]:
    """读取合同绑定文件夹内某个文件的正文；文字层不可用时返回原件页图（非 OCR）。

    用户消息里的「[已引用文件：… (contract_id=…, subpath=…)]」引用用本工具
    取内容。文件不复制、直接读原文件，始终读到最新版；权限与合同目录树同
    口径（行级 ACL）。返回块序列与 read_agent_attachment 一致：第一个块是
    JSON 元数据，其后是正文文本块或每页的说明文本 + 图片块。

    Args:
        contract_id: 消息里引用的合同 ID。
        subpath: 绑定根下的相对路径（posix），如 ``1-一审/2-立案材料/起诉状.pdf``。
        max_length: 文本路径本次返回的正文上限（字符），默认 20000，
            钳制在 [100, 100000] 区间。
        start: 从正文的第几个字符开始读（分段读长材料用）。
        pages: 要出图的页（1 起）。``"all"``、``"1-3,5"`` 或页码数组；
            默认前 3 页。显式给出时优先按图像路径返回这些页。
        dpi: 页图渲染分辨率，默认 150，钳制在 [72, 300]。
        format: 页图格式，``png``（默认）或 ``jpeg``。
        max_pages: 单次最多返回多少页图，默认且最多 10。

    Raises:
        ValueError: contract_id 非正整数、subpath 为空，或 format 不是 png/jpeg。

    Returns:
        ``[元数据 TextContent, …正文 TextContent 或 每页 TextContent+ImageContent]``。
    """
    if not isinstance(contract_id, int) or isinstance(contract_id, bool) or contract_id <= 0:
        raise ValueError(f"contract_id 应为正整数（来自消息里的文件夹引用），收到：{contract_id!r}")
    normalized_subpath = str(subpath or "").strip()
    if not normalized_subpath:
        raise ValueError("subpath 不能为空（来自消息里的文件夹引用，形如 1-一审/2-立案材料/起诉状.pdf）")
    return _read_file_via_source(
        ref_id=f"folder:{contract_id}/{normalized_subpath}",
        load_content=lambda notices: _load_folder_content(contract_id, normalized_subpath, notices),
        fetch_pages=lambda **kw: _render_folder_pages(contract_id=contract_id, subpath=normalized_subpath, **kw),
        max_length=max_length,
        start=start,
        pages=pages,
        dpi=dpi,
        format=format,
        max_pages=max_pages,
    )


def _load_folder_content(contract_id: int, subpath: str, notices: list[str]) -> dict[str, Any]:
    """取绑定文件夹原文件字节；服务端 4xx 归一化成错误码（不抛 500）。"""
    try:
        info = client.get("/agent/folder-refs/content", params={"contract_id": contract_id, "subpath": subpath})
    except Exception as exc:
        code, detail = _classify_http_error(exc, not_found=ERROR_NOT_FOUND, forbidden=ERROR_FORBIDDEN)
        notices.append(detail)
        return {
            "attachment_id": f"folder:{contract_id}/{subpath}",
            "filename": "",
            "mime": "",
            "error": code,
        }

    payload = str(info.get("content_base64") or "")
    file_bytes = base64.b64decode(payload) if payload else b""
    if not file_bytes:
        notices.append("服务端返回的文件内容为空（0 字节）")
        return {
            "attachment_id": f"folder:{contract_id}/{subpath}",
            "filename": str(info.get("filename") or ""),
            "mime": str(info.get("mime") or ""),
            "error": ERROR_PARSE_EMPTY,
        }
    return {
        "attachment_id": f"folder:{contract_id}/{subpath}",
        "filename": str(info.get("filename") or ""),
        "mime": str(info.get("mime") or ""),
        "file_bytes": file_bytes,
    }


def _render_folder_pages(
    *, contract_id: int, subpath: str, pages: list[int] | str, dpi: int, image_format: str
) -> tuple[list[TextContent | ImageContent], list[dict[str, Any]], list[str], str]:
    """取绑定文件夹文件的页图（响应消费与附件版共用 ``_consume_pages_response``）。"""
    local_notices: list[str] = []
    params = {
        "contract_id": str(contract_id),
        "subpath": subpath,
        "pages": _pages_param(pages),
        "dpi": str(_clamp_dpi(dpi)),
        "format": image_format,
    }
    try:
        response = client.get("/agent/folder-refs/pages", params=params)
    except Exception as exc:
        # 与附件版同口径：文件本身已被 /content 取到，页图请求失败只说明
        # 「渲染这条腿断了」，报 not_found 会让模型对用户说「文件不存在」。
        local_notices.append(f"页图渲染不可用：{exc}")
        return [], [], local_notices, ""
    return _consume_pages_response(response, local_notices, image_format=image_format)
