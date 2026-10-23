"""Agent 对话附件读取 —— 模型按 attachment_id 取附件正文或原件页图。

## 为什么不是把整份文件 base64 塞给模型

对话附件（PDF/图片/文档）由前端上传、服务端存档（apps/agent
services/attachments.py）。模型需要的是**正文文本**或**看得懂的页图**，不是
文件字节：把整份 PDF 的 base64 过一遍上下文意味着数十万 token，且模型回显
长 base64 不可靠。本工具在 mcp_server 侧把文件转投 /document-parsing 提取
文本（图片类按 MIME 走 OCR 后端）；只有「文字层不可用」时才按页取原件渲染图。

## 返回的是 content blocks，不是 dict

返回类型注解是 ``list[TextContent | ImageContent]``——MCP 框架对这类注解
**不生成 output_schema、不做 pydantic 校验**，直接把返回值当 content blocks
下发给模型。注解若仍是 dict，框架会生成 output_schema 做结构化校验，
而图片必须以 image block 下发（拍平成 dict 里的 base64 字符串，模型侧拿到的
是文字而不是能「看」的图）。

块序列：

    1. TextContent：JSON 元数据（attachment_id/filename/mime/total_pages/
       pages_returned/strategy/chars/truncated/notices[]，出错时含 error）
    2. 文本路径：一个 TextContent 放正文（max_length/start 分段）
       图像路径：每页一条「第 N 页（原图，非 OCR）」TextContent + 一个 ImageContent

## 为什么必须能回落到原件图（2026 扫描件 chars:0 故障）

- ``local_backend`` 对 PDF 只做 ``page.get_text()``，扫描件得空文本且
  ``success=True``；
- 解析端点「解析成功但文本为空」时，旧实现把它当成功返回 ``content: ""``；
两层叠加就是「工具成功、正文 0 字符、模型什么也没看到」且无任何报错。
现在的规则是：

- 文字层总长 < 50 字符 → 整体走图像路径；
- 有文字层但存在空页 → 按页回落（该页出图、其余仍用文本），strategy="mixed"；
- 文字层空 且 渲染失败 → ``error="parse_empty"``，**绝不返回空内容冒充成功**。

## 链路

    read_agent_attachment(attachment_id, …)
      → GET /agent/attachments/{id}/content（律师身份，归属校验在服务端）
      → 文本类直接解码；其余 POST /document-parsing/extract-text（max_length 探针）
      → 需要页图时 GET /agent/attachments/{id}/pages?pages=&dpi=&format=&max_pages=
      → content blocks（元数据 + 正文/页图）
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from typing import Any

from mcp.types import ImageContent, TextContent

from mcp_server.client import client
from mcp_server.tools.documents.parsing import content_type_for

#: 正文回给模型的默认上限（字符）——大材料应显式分段/收敛查询
DEFAULT_MAX_LENGTH = 20000
#: max_length 钳制上限：防一次请求刷爆模型上下文与解析端点
MAX_LENGTH_CEILING = 100_000
#: max_length 钳制下限：防 0/负数等退化值（显式小值不再被静默放大）
MAX_LENGTH_FLOOR = 100

#: 只取前 3 页是「够模型判断这是什么材料」与上下文成本之间的折中；
#: 真要看后面几页用 pages 显式指定。
DEFAULT_PAGE_COUNT = 3
#: 图像路径的页数硬上限：每页都是一张 base64 图，再多必然撑爆上下文
MAX_PAGES_CEILING = 10
#: 渲染分辨率（dpi）：150 是「扫描件小字可读」与体积的下限平衡点
DEFAULT_DPI = 150
DPI_FLOOR = 72
DPI_CEILING = 300

#: 文字层短于此长度视为「没有可用文字层」（扫描件常残留页码/水印几个字）
MIN_TEXT_CHARS = 50

DEFAULT_FORMAT = "png"
_IMAGE_MIMES = {"png": "image/png", "jpeg": "image/jpeg"}

#: attachment_id 为 UUID（消息里的附件引用原样携带）
_ATTACHMENT_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

_TEXT_MIMES = {"text/plain"}

#: 「页 N 正文」标记行——解析端点返回的文本带 `\n\n` 页分隔，靠它做页粒度切分
_PAGE_MARKER_RE = re.compile(r"^【第(\d+)页】$", re.MULTILINE)

#: 禁止把附件内容当成功返回的失败原因。名字即错误码，写进元数据块 error 字段，
#: 让模型能区分「附件不存在」「没权限」「是扫描件」「解析失败」。
ERROR_NOT_FOUND = "not_found"
ERROR_FORBIDDEN = "forbidden"
ERROR_ENCRYPTED = "encrypted"
ERROR_UNSUPPORTED_MIME = "unsupported_mime"
ERROR_TOO_LARGE = "too_large"
ERROR_PAGE_OUT_OF_RANGE = "page_out_of_range"
ERROR_PARSE_EMPTY = "parse_empty"
ERROR_PARSE_FAILED = "parse_failed"

#: 页图端点在「一页也没渲出来」时能给出的**具体**失败原因（其余一律归 parse_empty）
_FINAL_RENDER_ERRORS = frozenset(
    {
        ERROR_ENCRYPTED,
        ERROR_UNSUPPORTED_MIME,
        ERROR_TOO_LARGE,
        ERROR_PAGE_OUT_OF_RANGE,
        ERROR_NOT_FOUND,
        ERROR_FORBIDDEN,
    }
)


def read_agent_attachment(
    attachment_id: str,
    max_length: int = DEFAULT_MAX_LENGTH,
    start: int = 0,
    pages: str | list[int] | None = None,
    dpi: int = DEFAULT_DPI,
    format: str = DEFAULT_FORMAT,
    max_pages: int = MAX_PAGES_CEILING,
) -> list[TextContent | ImageContent]:
    """读取一个对话附件的正文；文字层不可用时返回原件页图（非 OCR）。

    用户消息里的「[已上传附件：name (attachment_id=…)]」引用用本工具取内容。
    第一个 content block 是 JSON 元数据（strategy/chars/pages_returned/error 等），
    其后是正文文本块（strategy="text"）或每页的说明文本 + 图片块
    （strategy="image"/"mixed"，图片是**原件的渲染图**，不是 OCR 结果）。

    Args:
        attachment_id: 消息里引用的附件标识（UUID 格式）。
        max_length: 文本路径本次返回的正文上限（字符），默认 20000，
            钳制在 [100, 100000] 区间。
        start: 从正文的第几个字符开始读（分段读长材料用）。
        pages: 要出图的页（1 起）。``"all"``、``"1-3,5"`` 这类字符串或页码
            数组；默认前 3 页。显式给出时优先按图像路径返回这些页。
        dpi: 页图渲染分辨率，默认 150，钳制在 [72, 300]。
        format: 页图格式，``png``（默认）或 ``jpeg``。
        max_pages: 单次最多返回多少页图，默认且最多 10；超出部分截断并在
            元数据 notices 里明确告知。

    Raises:
        ValueError: attachment_id 不是 UUID 格式（拼错/被截断的引用），
            或 format 不是 png/jpeg。

    Returns:
        ``[元数据 TextContent, …正文 TextContent 或 每页 TextContent+ImageContent]``。
    """

    if not _ATTACHMENT_ID_RE.match(attachment_id or ""):
        raise ValueError(f"attachment_id 应为 UUID（来自消息里的附件引用），收到：{attachment_id!r}")

    return _read_file_via_source(
        ref_id=attachment_id,
        load_content=lambda notices: _load_content(attachment_id, notices),
        fetch_pages=lambda **kw: _render_pages(attachment_id=attachment_id, **kw),
        max_length=max_length,
        start=start,
        pages=pages,
        dpi=dpi,
        format=format,
        max_pages=max_pages,
    )


def _read_file_via_source(
    *,
    ref_id: str,
    load_content: Callable[[list[str]], dict[str, Any]],
    fetch_pages: Callable[..., Any],
    max_length: int,
    start: int,
    pages: str | list[int] | None,
    dpi: int,
    format: str,
    max_pages: int,
) -> list[TextContent | ImageContent]:
    """read_* 工具的共享编排：取字节 → 文本/图像分流 → content blocks。

    ``ref_id`` 进元数据块（附件版为 uuid，文件夹引用版为 ``folder:{cid}/{subpath}``）；
    ``load_content``/``fetch_pages`` 是数据源回调——附件版走
    ``/agent/attachments/{id}/*``，文件夹引用版走 ``/agent/folder-refs/*``，
    其余编排（文本探针、扫描件回落、分段、限额）完全共用，避免两处漂移。
    """
    image_format = _normalize_format(format)
    image_format = _normalize_format(format)
    requested_pages = _parse_pages(pages)
    notices: list[str] = []

    info = load_content(notices)
    if info.get("error"):
        return _metadata_only(info, notices)

    filename = str(info.get("filename") or "")
    mime = str(info.get("mime") or "")
    meta: dict[str, Any] = {
        "attachment_id": ref_id,
        "filename": filename,
        "mime": mime,
        "total_pages": None,
    }

    if _is_plain_text(mime, filename):
        text = info["file_bytes"].decode("utf-8", errors="replace")
        meta["total_pages"] = 1
        return _text_result(meta, text, start=int(start), limit=_clamp_limit(max_length), notices=notices)

    # 位图附件直接就出图：它本来就没有文字层，送去 OCR 只会白跑一趟异步任务，
    # 且 OCR 结果丢失版式/表格结构。模型本身是多模态的，原图比 OCR 更忠实。
    if mime.startswith(_IMAGE_MIME_PREFIX):
        meta["total_pages"] = 1
        notices.append("图片附件：直接返回原图（非 OCR 文本）")
        selection = _select_pages(
            requested=requested_pages,
            text="",
            total_pages=1,
            page_texts=None,
            max_pages=max_pages,
        )
        notices.extend(selection["notices"])
        return _render_selection(
            meta=meta,
            selection=selection,
            fetch_pages=fetch_pages,
            text="",
            requested_pages=requested_pages,
            dpi=dpi,
            image_format=image_format,
            start=int(start),
            max_length=max_length,
            notices=notices,
        )

    parsed = _extract_text(
        filename=filename,
        file_bytes=info["file_bytes"],
        offset=max(0, int(start)),
        limit=_clamp_limit(max_length),
    )

    if parsed.get("error"):
        # 文本提取失败**不等于**附件读不到：扫描件/图片本就没有文字层，
        # 解析端点还可能把它转成异步 OCR 任务（task_id + pending）。
        # 这几种情况必须回落到页图路径，否则就是本次故障原样复现——
        # 「分析不出文字」被当成「没有内容」，模型收到空结果。
        # 只有「解析端点没能给出文字」就回落页图；但**加密/损坏**这类确定性
        # 错误必须优先报出去——把加密 PDF 降级成 parse_empty，用户会把「密码问题」
        # 当成「文件没内容」，下一步动作完全不同。
        #
        # 异步 OCR 任务（retryable=True）**也要回落**：扫描件正是这类典型，
        # 让模型去看原图比让它轮询一个数分钟后才有结果的 OCR 任务更好——原图
        # 保留版式与表格结构，OCR 只会给一份可能出错的纯文本。这条曾被
        # 「保住旧测试」的顾虑搭掉，代价是扫描件合同完全不返图（实测踩到）。
        if _can_render_pages(mime, filename) and _is_empty_text_reason(parsed.get("error")):
            image_like = mime.startswith(_IMAGE_MIME_PREFIX)
            notices.extend(parsed.get("notices") or [])
            notices.append(
                f"文字提取不可用（{parsed.get('error') or 'empty'}）：已回落到原件页图，以下为原图而非 OCR 结果"
            )
            text = ""
            # 页数在文字提取失败时是未知的，除非是位图（恒 1 页）。
            # 不能因此就把 "all" 当成越界：调用方要的是「把能给的页都给我」，
            # 而不是「告诉我这文件没页」。具体页数交给页图端点自己数——
            # 它打开 PDF 后才有 doc.page_count。
            total_pages = 1 if image_like else None
            meta["total_pages"] = total_pages
            selection = _select_pages(
                requested=requested_pages,
                text=text,
                total_pages=total_pages,
                page_texts=None,
                max_pages=max_pages,
            )
            notices.extend(selection["notices"])
            return _render_selection(
                meta=meta,
                selection=selection,
                fetch_pages=fetch_pages,
                text=text,
                requested_pages=requested_pages,
                dpi=dpi,
                image_format=image_format,
                start=int(start),
                max_length=max_length,
                notices=notices,
            )

        meta["error"] = parsed["error"]
        if parsed.get("retryable"):
            meta["retryable"] = True
        meta["chars"] = 0
        meta["truncated"] = False
        meta["pages_returned"] = []
        meta["strategy"] = "text"
        notices.extend(parsed.get("notices") or [])
        return _metadata_only(meta, notices)

    text = parsed["text"]
    total_pages = parsed.get("total_pages")
    meta["total_pages"] = total_pages
    notices.extend(parsed.get("notices") or [])

    selection = _select_pages(
        requested=requested_pages,
        text=text,
        total_pages=total_pages,
        page_texts=parsed.get("page_texts"),
        max_pages=max_pages,
    )
    notices.extend(selection["notices"])
    return _render_selection(
        meta=meta,
        selection=selection,
        fetch_pages=fetch_pages,
        text=text,
        requested_pages=requested_pages,
        dpi=dpi,
        image_format=image_format,
        start=int(start),
        max_length=max_length,
        notices=notices,
    )


def _render_selection(
    *,
    meta: dict[str, Any],
    selection: dict[str, Any],
    fetch_pages: Callable[..., Any],
    text: str,
    requested_pages: list[int] | str | None,
    dpi: int,
    image_format: str,
    start: int,
    max_length: int,
    notices: list[str],
) -> list[TextContent | ImageContent]:
    """按 ``_select_pages`` 的判定把结果组装成 content blocks。

    抽出来是为了让「文字层可用」与「文字提取失败后回落」两条入口共用同一套
    出图/混排逻辑，避免两处判断漂移导致某一侧又静默返回空内容。
    """
    if selection["error"]:
        meta["error"] = selection["error"]
        meta["chars"] = 0
        meta["truncated"] = False
        meta["pages_returned"] = []
        meta["strategy"] = selection["strategy"]
        return _metadata_only(meta, notices)

    if not selection["image_pages"]:
        if not text.strip():
            return _empty_text_result(meta, notices)
        return _text_result(meta, text, start=max(0, start), limit=_clamp_limit(max_length), notices=notices)

    blocks, rendered_pages, render_notices, render_error = fetch_pages(
        pages=selection["image_pages"],
        dpi=dpi,
        image_format=image_format,
    )
    notices.extend(render_notices)

    if not rendered_pages:
        # 选定要出图的页一张都没渲出来：文字层若可用就仍然给文本，
        # 否则如实报 parse_empty——两种情况都不返回空内容冒充成功。
        return _fallback_after_render_failure(
            meta=meta,
            text=text,
            start=max(0, start),
            limit=_clamp_limit(max_length),
            selection=selection,
            notices=notices,
            render_error=render_error,
        )

    mixed = selection["text_chars"] >= MIN_TEXT_CHARS
    # 端点可能把文字页的正文送回来（文字层页按设计不出图）——这时本工具
    # 实际拿到了正文，不能继续按「纯图」报 chars=0，否则上游又会当它没内容。
    has_image_block = any(getattr(block, "type", None) == "image" for block in blocks)
    if not has_image_block:
        meta["strategy"] = "text"
        meta["pages_returned"] = rendered_pages
        meta["chars"] = _count_text_chars(blocks)
        meta["truncated"] = False
        return [_metadata_block(meta, notices), *blocks]

    meta["strategy"] = "mixed" if mixed else "image"
    meta["pages_returned"] = rendered_pages
    meta["chars"] = selection["text_chars"] or _count_text_chars(blocks)
    meta["truncated"] = False
    if not mixed:
        return [_metadata_block(meta, notices), *blocks]
    # mixed：元数据块 + 正文块 + 每页「说明 + 图」
    text_blocks = _text_blocks(
        meta,
        selection["text"],
        start=max(0, start),
        limit=_clamp_limit(max_length),
        notices=notices,
    )
    return [*text_blocks, *blocks]


# ─── 元数据块 ────────────────────────────────────────────────────────────────


def _metadata_block(meta: dict[str, Any], notices: list[str]) -> TextContent:
    """元数据块：先给模型「这是什么、返回了什么、有没有问题」，再给正文/图。

    必须是纯 ASCII 的 JSON（``ensure_ascii=True``）——中文在 prompt 里
    转义后可读性略差，但非 ASCII 的 JSON 文本在部分网关/日志链路上会被
    二次转码，模型读到的就是乱码；这里选择「一定能被正确解析」优先。
    """
    payload = dict(meta)
    payload["notices"] = list(notices)
    if "strategy" not in payload:
        payload["strategy"] = "text"
    payload.setdefault("chars", 0)
    payload.setdefault("truncated", False)
    payload.setdefault("pages_returned", [])
    payload.setdefault("total_pages", None)
    return TextContent(type="text", text=json.dumps(payload, ensure_ascii=True))


def _metadata_only(meta: dict[str, Any], notices: list[str]) -> list[TextContent | ImageContent]:
    """失败时只返回元数据块（含 error 与指导性 notice），绝不返回空正文块。"""
    return [_metadata_block(meta, notices)]


# ─── 读取与解析 ──────────────────────────────────────────────────────────────


def _load_content(attachment_id: str, notices: list[str]) -> dict[str, Any]:
    """取附件原始字节；把服务端 4xx 归一化成错误码写进返回值（不抛 500）。"""
    try:
        info = client.get(f"/agent/attachments/{attachment_id}/content")
    except Exception as exc:
        code, detail = _classify_http_error(exc, not_found=ERROR_NOT_FOUND, forbidden=ERROR_FORBIDDEN)
        notices.append(detail)
        return {
            "attachment_id": attachment_id,
            "filename": "",
            "mime": "",
            "error": code,
        }

    payload = str(info.get("content_base64") or "")
    file_bytes = base64.b64decode(payload) if payload else b""
    if not file_bytes:
        notices.append("服务端返回的附件内容为空（0 字节）")
        return {
            "attachment_id": attachment_id,
            "filename": str(info.get("filename") or ""),
            "mime": str(info.get("mime") or ""),
            "error": ERROR_PARSE_EMPTY,
        }
    return {
        "attachment_id": attachment_id,
        "filename": str(info.get("filename") or ""),
        "mime": str(info.get("mime") or ""),
        "file_bytes": file_bytes,
    }


def _extract_text(*, filename: str, file_bytes: bytes, offset: int, limit: int) -> dict[str, Any]:
    """调解析端点取正文，并把「成功但空文本」判定为失败而不是成功。

    ``max_length`` 向解析端点多要 ``offset+limit+1``：解析端点按 max_length
    硬截断且不回报总长，只有多要 1 个字符才能区分「恰好读完」与「还有更多」
    （否则 truncated 恒为 False，长 PDF 会被当全文引用）。
    """
    result = client.upload(
        "/document-parsing/extract-text",
        files={"file": (filename, file_bytes, content_type_for(filename))},
        data={"backend": "auto", "max_length": str(offset + limit + 1)},
    )
    task_id = str(result.get("task_id") or "")
    text_raw = str(result.get("text") or "")
    if task_id and not text_raw:
        return {
            "error": ERROR_PARSE_EMPTY,
            # 失败码与「本次结果暂缺、稍后重试」分开：模型据此决定是重试还是放弃
            "retryable": True,
            "notices": [
                f"解析已转异步任务 task_id={task_id}：用 get_document_parsing_task 查询结果，"
                "完成后重新调用 read_agent_attachment 读取正文"
            ],
        }

    if not result.get("success", True) and not text_raw:
        reason = str(result.get("error") or result.get("status") or "解析失败")
        code = _classify_parse_reason(reason)
        return {"error": code, "notices": [f"附件解析失败（{reason}）"]}

    if not text_raw.strip():
        # 「空正文」不是错误而是要回落的信号：继续走选页逻辑，由页图兜底。
        # 只有页图也拿不到时，选页层才把 parse_empty 作为最终 error 报出去。
        return {
            "text": "",
            "page_texts": None,
            "total_pages": _read_page_count(result.get("metadata")),
            "notices": ["解析成功但正文为空（常见于纯扫描件/纯图片 PDF），尝试回落原件页图"],
        }

    page_texts, total_pages, page_notices = _split_pages(text_raw, result.get("metadata"))
    return {
        "text": text_raw,
        "page_texts": page_texts,
        "total_pages": total_pages,
        "notices": page_notices,
    }


def _split_pages(text: str, metadata: Any) -> tuple[dict[int, str] | None, int | None, list[str]]:
    """把解析端点返回的正文按页切开（端点用 ``【第N页】`` 标记页边界）。

    返回 ``(page_texts, total_pages, notices)``；无标记时 ``page_texts`` 为
    ``None``，选页逻辑据此退化成「全文算一页」。
    """
    notices: list[str] = []
    total_pages = _read_page_count(metadata)
    markers = list(_PAGE_MARKER_RE.finditer(text))
    if not markers:
        return None, total_pages, notices

    page_texts: dict[int, str] = {}
    for index, marker in enumerate(markers):
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        page_texts[int(marker.group(1))] = text[start:end].strip()
    if total_pages is None and page_texts:
        total_pages = max(page_texts)
    if total_pages is not None and len(page_texts) < total_pages:
        notices.append(f"仅解析到前 {len(page_texts)} 页正文（共 {total_pages} 页），其余页可显式传 pages 取原件图")
    return page_texts, total_pages, notices


def _read_page_count(metadata: Any) -> int | None:
    """从解析端点 metadata 里取总页数（各后端字段名一致：``page_count``）。"""
    if not isinstance(metadata, dict):
        return None
    for key in ("page_count", "pages"):
        value = metadata.get(key)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    return None


# ─── 策略选择 ────────────────────────────────────────────────────────────────


def _select_pages(
    *,
    requested: list[int] | str | None,
    text: str,
    total_pages: int | None,
    page_texts: dict[int, str] | None,
    max_pages: int,
) -> dict[str, Any]:
    """决定这次返回文本还是图、出哪几页图、以及文本用哪一段。

    判定顺序（P0）：

    1. ``pages`` 显式给出 → 按图像路径返回这些页（用户明确要看原件）；
    2. 文字层总长 < 50 字符（含解析端点根本没给文字层）→ 整体走图像路径；
    3. 有文字层且存在空页 → 按页回落：空页出图、其余页仍给文本（mixed）；
    4. 其余 → 纯文本路径。
    """
    notices: list[str] = []
    cap = max(1, min(int(max_pages), MAX_PAGES_CEILING))
    has_text_layer = len(text.strip()) >= MIN_TEXT_CHARS

    if requested is not None:
        return _explicit_pages(
            requested=requested,
            text=text,
            total_pages=total_pages,
            has_text_layer=has_text_layer,
            cap=cap,
            notices=notices,
        )

    if not has_text_layer:
        pages = _default_pages(total_pages, cap, notices)
        return {
            "strategy": "image",
            "image_pages": pages,
            "text": text,
            "text_chars": 0,
            "error": None,
            "notices": notices,
        }

    empty_pages = _empty_pages(page_texts)
    if not empty_pages:
        return {
            "strategy": "text",
            "image_pages": [],
            "text": text,
            "text_chars": len(text),
            "error": None,
            "notices": notices,
        }

    pages, dropped = _truncate(empty_pages, cap)
    notices.append(
        f"第 {', '.join(str(p) for p in pages)} 页无文字层（扫描件），已按页回落原件图；正文文本块只含其余页"
    )
    if dropped:
        notices.append(f"另有 {dropped} 个无文字层页面超出单次 {cap} 页上限未返回，可再传 pages 指定")
    return {
        "strategy": "mixed",
        "image_pages": pages,
        "text": text,
        "text_chars": len(text),
        "error": None,
        "notices": notices,
    }


def _explicit_pages(
    *,
    requested: list[int] | str,
    text: str,
    total_pages: int | None,
    has_text_layer: bool,
    cap: int,
    notices: list[str],
) -> dict[str, Any]:
    """``pages`` 显式指定的路径：越界直接报 page_out_of_range，不静默裁剪成空。"""
    if requested == "all":
        if not total_pages:
            # 页数未知通常是「文字提取失败、直接回落页图」的路径（扫描件）。
            # 此时调用方的真实意图是「能给的页都给我」，报越界会让模型对用户
            # 说「这份材料没有页」——与事实相反。用 ``"all"`` 透传给页图端点，
            # 它打开文件后自己数页并受 max_pages 截断。
            return {
                "strategy": "image",
                "image_pages": "all",
                "text": text,
                "text_chars": 0,
                "error": None,
                "notices": list(notices),
            }
        requested_pages = list(range(1, total_pages + 1))
    else:
        requested_pages = sorted({int(page) for page in requested if int(page) > 0})

    if not requested_pages:
        return {
            "strategy": "image",
            "image_pages": [],
            "text": text,
            "text_chars": 0,
            "error": ERROR_PAGE_OUT_OF_RANGE,
            "notices": [*notices, "pages 解析后没有有效页码（页码从 1 开始）"],
        }

    pages, dropped = _truncate(requested_pages, cap)
    if dropped:
        notices.append(f"请求 {len(requested_pages)} 页，超过单次 {cap} 页上限，已截断为前 {len(pages)} 页")
    return {
        "strategy": "mixed" if has_text_layer else "image",
        "image_pages": pages,
        "text": text,
        "text_chars": len(text) if has_text_layer else 0,
        "error": None,
        "notices": notices,
    }


def _empty_pages(page_texts: dict[int, str] | None) -> list[int]:
    """找出「有页结构但没有文字层」的页码（按页回落的依据）。"""
    if not page_texts:
        return []
    return [page for page, page_text in sorted(page_texts.items()) if not page_text.strip()]


def _default_pages(total_pages: int | None, cap: int, notices: list[str]) -> list[int] | str:
    """图像路径的默认页：前 3 页，受 max_pages 与总页数约束。

    页数未知时返回 ``"all"`` 而不是猜 ``[1,2,3]``：猜页码会在“单页附件”上
    直接报 page_out_of_range（实测：1 页扫描件 + 默认路径 = 一张图都拿不到）。
    真实意图是“能给的页按上限都给我”，页数由端点打开文件后自己数。
    """
    wanted = min(DEFAULT_PAGE_COUNT, cap)
    if total_pages is None:
        notices.append(f"页数未知，按上限取原件图（最多前 {wanted} 页）")
        return "all"
    pages, dropped = _truncate(list(range(1, total_pages + 1)), wanted)
    if dropped:
        notices.append(f"共 {total_pages} 页，默认只返回前 {len(pages)} 页原件图；其余页用 pages 指定")
    return pages


def _truncate(pages: list[int], cap: int) -> tuple[list[int], int]:
    """页数截断：返回 (保留页, 被丢弃页数)。"""
    if len(pages) <= cap:
        return pages, 0
    return pages[:cap], len(pages) - cap


# ─── 渲染 ────────────────────────────────────────────────────────────────────


def _pages_param(pages: list[int] | str) -> str:
    """把选页结果转成端点能理解的 ``pages`` 查询值。

    ``"all"`` 原样透传（页数未知时由端点打开文件自己数），否则转逗号分隔的
    1-based 页码列表。
    """
    if isinstance(pages, str):
        return pages
    return ",".join(str(page) for page in pages)


def _render_pages(
    *,
    attachment_id: str,
    pages: list[int] | str,
    dpi: int,
    image_format: str,
) -> tuple[list[TextContent | ImageContent], list[dict[str, Any]], list[str], str]:
    """取页图并把每页拼成「说明文本 + ImageContent」。

    响应契约（后端 ``GET /agent/attachments/{id}/pages``，T4 已落地）::

        {"attachment_id": str, "filename": str, "mime": str, "total_pages": int,
         "pages_returned": [{"page": int, "mime": "image/png", "b64": str,
                             "bytes": int, "width": int, "height": int,
                             "has_text_layer": bool, "error": str, "detail": str}, …],
         "strategy": "text"|"image"|"mixed",
         "error": "",   # not_found / forbidden / parse_empty / encrypted /
                        # unsupported_mime / too_large / page_out_of_range
         "detail": str, "notices": [str], "truncated_pages": bool}

    渲染失败是 **200 + error 错误码**（不是 500），所以必须读响应体里的
    ``error`` 而不是只看是否抛异常。

    ``max_pages`` 不传：服务端把它当**硬截断上限**，传小值会让「mixed 回落的
    单页」或「默认前 3 页」被二次裁剪且只报 truncated_pages；页数上限由本工具
    在选页阶段钳制（``MAX_PAGES_CEILING``）。

    Returns:
        ``(blocks, pages_returned, notices, error_code)``；单页失败不拖垮整次调用。
    """
    local_notices: list[str] = []
    params = {
        "pages": _pages_param(pages),
        "dpi": str(_clamp_dpi(dpi)),
        "format": image_format,
    }
    try:
        response = client.get(f"/agent/attachments/{attachment_id}/pages", params=params)
    except Exception as exc:
        # 这里不把 HTTP 状态映射成错误码：附件本身已经被 /content 取到了，
        # 页图请求失败只说明「渲染这条腿断了」（服务端 500/503、连接抖动），
        # 报 not_found 会让模型对用户说「附件不存在」——与事实相反。
        local_notices.append(f"页图渲染不可用：{exc}")
        return [], [], local_notices, ""

    return _consume_pages_response(response, local_notices, image_format=image_format)


def _consume_pages_response(
    response: dict[str, Any], local_notices: list[str], *, image_format: str
) -> tuple[list[TextContent | ImageContent], list[dict[str, Any]], list[str], str]:
    """把 /pages 端点响应拼成「说明文本 + ImageContent」块（附件与文件夹引用共用）。

    响应契约（``AttachmentPagesOut``）：渲染失败是 **200 + error 错误码**
    （不是 500），所以必须读响应体里的 ``error`` 而不是只看是否抛异常。
    """
    for notice in response.get("notices") or []:
        local_notices.append(str(notice))
    server_error = str(response.get("error") or "")
    entries = response.get("pages_returned") or []
    if not isinstance(entries, list) or not entries:
        local_notices.append("页图端点未返回任何页" + (f"（服务端 error={server_error}）" if server_error else ""))
        return [], [], local_notices, server_error

    blocks: list[TextContent | ImageContent] = []
    returned: list[dict[str, Any]] = []
    text_pages: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        data = str(entry.get("b64") or "")
        page_text = str(entry.get("text") or "")
        mime_type = str(entry.get("mime") or _IMAGE_MIMES[image_format])
        page = int(entry.get("page") or 0)

        if not data:
            # 文字层页按设计不出图（省视觉 token），但端点是**把文字带回来的**。
            # 旧实现只看到「没有 b64」就跳过，连带把该页正文丢了——当解析服务
            # 转异步（扫描件常见）时就会变成「明明有字却读不到」，模型只能报空。
            if page_text.strip():
                text_pages.append(page_text)
                returned.append(
                    {
                        "page": page,
                        "mime": mime_type,
                        "bytes": 0,
                        "width": entry.get("width"),
                        "height": entry.get("height"),
                        "has_text_layer": True,
                    }
                )
                continue
            local_notices.append(f"第 {page} 页未返回图像数据，已跳过（不渲染空白图冒充满意结果）")
            continue

        # 「原图，非 OCR」是**必读标记**：模型必须能区分「我看到的像素」与
        # 「OCR 出的文字」，否则会把自己没读到的字当作已核对内容引用。
        blocks.append(TextContent(type="text", text=f"第 {page} 页（原图，非 OCR）"))
        blocks.append(ImageContent(type="image", data=data, mime_type=mime_type))
        returned.append(
            {
                "page": page,
                "mime": mime_type,
                "bytes": int(entry.get("bytes") or 0),
                "width": entry.get("width"),
                "height": entry.get("height"),
                "has_text_layer": bool(entry.get("has_text_layer")),
            }
        )

    if text_pages:
        # 文字页统一放在图像块**之前**：模型先读到正文，再对照原图（若有）。
        joined = "\n\n".join(text_pages)
        blocks.insert(0, TextContent(type="text", text=joined))
        local_notices.append(f"另有 {len(text_pages)} 页有文字层，已按文本返回（未出图，省视觉 token）")
    return blocks, returned, local_notices, server_error


def _count_text_chars(blocks: list[TextContent | ImageContent]) -> int:
    """content blocks 里的正文总字数（不含「第 N 页」这类说明行）。

    用于端点把文字页正文送回来时如实报 ``chars``：报 0 会让上游误以为
    没有内容，又把一次成功读取降级成失败。
    """
    total = 0
    for block in blocks:
        if getattr(block, "type", None) != "text":
            continue
        text = str(getattr(block, "text", "") or "")
        if text.startswith("第 ") and "页（原图，非 OCR）" in text:
            continue
        total += len(text.strip())
    return total


def _fallback_after_render_failure(
    *,
    meta: dict[str, Any],
    text: str,
    start: int,
    limit: int,
    selection: dict[str, Any],
    notices: list[str],
    render_error: str = "",
) -> list[TextContent | ImageContent]:
    """要出图的页一张都没渲出来时的兜底：有文字层给文本，否则如实报错。

    服务端给出的具体错误码（encrypted / too_large / unsupported_mime /
    page_out_of_range）优先于笼统的 ``parse_empty``——模型据此知道该换文件、
    拆小文件，还是这个附件根本读不了。
    """
    usable_text = selection["text_chars"] >= MIN_TEXT_CHARS
    if usable_text:
        notices.append("页图渲染失败，已回落到文字层正文")
        return _text_blocks(meta, text, start=start, limit=limit, notices=notices)

    notices.append("文字层为空且原件页图渲染失败，本附件当前不可读；不要据此猜测内容")
    specific = render_error if render_error in _FINAL_RENDER_ERRORS else ""
    return _empty_text_result(meta, notices, strategy="image", error=specific)


def _empty_text_result(
    meta: dict[str, Any],
    notices: list[str],
    *,
    strategy: str = "text",
    error: str = "",
) -> list[TextContent | ImageContent]:
    """最终无内容可给：如实报 ``error``（缺省 ``parse_empty``），只返回元数据块。

    绝不追加一个正文空串块——那正是旧实现的故障形态：工具「成功」、
    正文 0 字符、模型什么也没看到且没有任何报错。
    """
    meta["error"] = error or ERROR_PARSE_EMPTY
    meta["strategy"] = strategy
    meta["chars"] = 0
    meta["truncated"] = False
    meta["pages_returned"] = []
    return _metadata_only(meta, notices)


# ─── 文本块 ──────────────────────────────────────────────────────────────────


def _text_result(
    meta: dict[str, Any],
    text: str,
    *,
    start: int,
    limit: int,
    notices: list[str],
) -> list[TextContent | ImageContent]:
    """纯文本路径：元数据块 + 正文块（分段 + 截断探针）。"""
    meta["strategy"] = "text"
    meta["pages_returned"] = []
    return _text_blocks(meta, text, start=start, limit=limit, notices=notices)


def _text_blocks(
    meta: dict[str, Any],
    text: str,
    *,
    start: int,
    limit: int,
    notices: list[str],
) -> list[TextContent | ImageContent]:
    """元数据块 + 正文块。``chars`` 记全文长度，``truncated`` 表示本次之后还有内容。"""
    # 只写正文相关字段：页图路径会先把 strategy/pages_returned 定好
    # （mixed 的元数据必须同时描述文本与页图），这里不能覆盖。
    meta["chars"] = len(text)
    meta["truncated"] = len(text) > start + limit
    segment = text[start : start + limit]
    return [_metadata_block(meta, notices), TextContent(type="text", text=segment)]


# ─── 参数归一化 ──────────────────────────────────────────────────────────────


def _clamp_limit(max_length: int) -> int:
    return max(MAX_LENGTH_FLOOR, min(int(max_length), MAX_LENGTH_CEILING))


def _clamp_dpi(dpi: int) -> int:
    return max(DPI_FLOOR, min(int(dpi), DPI_CEILING))


def _normalize_format(format: str) -> str:
    """页图格式只接受 png/jpeg（大小写与前导点无关）。"""
    normalized = (format or DEFAULT_FORMAT).strip().lower().lstrip(".")
    if normalized in ("jpg", "jpeg"):
        return "jpeg"
    if normalized == "png":
        return "png"
    raise ValueError(f"format 只支持 png 或 jpeg，收到：{format!r}")


def _parse_pages(pages: str | list[int] | None) -> list[int] | str | None:
    """归一化 pages：``None``（默认策略）/ ``"all"`` / ``list[int]``。

    接受 ``"1-3,5"`` / ``"1,2,3"`` / ``"all"`` / JSON 数组字符串
    （Claude Desktop 这类客户端会把数组当 JSON 字符串传过来）。
    """
    if pages is None:
        return None
    if isinstance(pages, list):
        return _dedupe_pages(pages)

    raw = str(pages).strip()
    if not raw:
        return None
    if raw.lower() == "all":
        return "all"
    if raw.startswith("["):
        try:
            decoded = json.loads(raw)
        except ValueError as exc:
            raise ValueError(f"pages 不是合法的页码列表：{raw!r}") from exc
        if not isinstance(decoded, list):
            raise ValueError(f"pages 应为页码列表，收到：{raw!r}")
        return _dedupe_pages(decoded)
    # "1-3,5" → 逐段展开：区间段按 a-b 展开，单值段直接取页码
    return _dedupe_pages([token for segment in raw.split(",") for token in _expand_page_segment(segment)])


def _expand_page_segment(segment: str) -> list[Any]:
    """展开一个逗号分隔段：``"3"`` → ``[3]``，``"1-3"`` → ``[1, 2, 3]``。"""
    token = segment.strip()
    if "-" not in token:
        return [token]
    start_text, _, end_text = token.partition("-")
    try:
        first, last = int(start_text), int(end_text)
    except ValueError as exc:
        raise ValueError(f"pages 区间格式非法：{token!r}（应为 a-b，a ≤ b）") from exc
    if first > last:
        raise ValueError(f"pages 区间起点大于终点：{token!r}")
    return list(range(first, last + 1))


def _dedupe_pages(values: list[Any]) -> list[int]:
    """页码去重升序；非法值（非数字）直接报错而不是静默丢弃。"""
    result: set[int] = set()
    for value in values:
        try:
            page = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"pages 含非数字页码：{value!r}") from exc
        result.add(page)
    return sorted(result)


# ─── 错误码映射 ──────────────────────────────────────────────────────────────


def _classify_http_error(exc: Exception, *, not_found: str, forbidden: str) -> tuple[str, str]:
    """把 client 抛的 ``RuntimeError("HTTP <status>: <detail>")`` 映射成错误码。

    越权与不存在在服务端就是同一个 404（不区分，避免校验式枚举），这里
    也保持同口径：404 → ``not_found``。服务器重启/断连（``ConnectError``）
    同样归一化为 ``not_found``，附原始异常文本便于模型向用户解释重试。
    """
    message = str(exc)
    match = re.match(r"HTTP (\d{3}):", message)
    if match is None:
        return not_found, f"服务端不可达：{message}"
    status = int(match.group(1))
    if status in (401, 403):
        return forbidden, f"无权访问该附件（HTTP {status}），不要重试，请让用户确认附件归属"
    if status == 404:
        return not_found, "附件不存在或不属于当前用户（服务端不区分两者）"
    if status == 413:
        return ERROR_TOO_LARGE, "附件超过解析体积上限（HTTP 413），请让用户换更小的文件"
    detail = message[len(match.group(0)) :].strip()
    return not_found, f"服务端返回 HTTP {status}：{detail}"


def _classify_parse_reason(reason: str) -> str:
    """把解析端点的失败原因归类成错误码（加密/超限/不支持，其余归 parse_failed）。"""
    lowered = reason.lower()
    if any(marker in lowered for marker in ("encrypt", "password", "加密", "密码")):
        return ERROR_ENCRYPTED
    if "too large" in lowered or "超过" in lowered or "413" in lowered:
        return ERROR_TOO_LARGE
    if any(marker in lowered for marker in ("unsupported", "not support", "不支持")) and "格式" in lowered:
        return ERROR_UNSUPPORTED_MIME
    return ERROR_PARSE_FAILED


def _is_plain_text(mime: str, filename: str) -> bool:
    return mime in _TEXT_MIMES or filename.lower().endswith(".txt")


#: 能出页图的格式（与服务端 attachment_render 的分流口径一致）。
#: 文字提取失败时只有这些格式能回落到图像，其余（如 docx）只能如实报错。
_IMAGE_MIME_PREFIX = "image/"
_PDF_SUFFIX = ".pdf"
_PDF_MIMES = {"application/pdf", "application/x-pdf"}


def _can_render_pages(mime: str, filename: str) -> bool:
    """该附件能否走「原件页图」路径。

    文本提取端点对扫描件/图片往往给不出文字（可能转成异步 OCR 任务），
    旧实现把这类无文字结果统一当成「读不到内容」直接返回——模型于是拿到
    空文本。这里给出回落的准入判断：只要格式本身能出图（PDF / 位图），
    就该拿原图给模型。
    """
    return bool(mime.startswith(_IMAGE_MIME_PREFIX) or mime in _PDF_MIMES or filename.lower().endswith(_PDF_SUFFIX))


#: 「没有文字可给」类失败：这些可以回落成页图。
#: 加密 / 损坏 等明确错误不在其中——它们要如实报给模型（下一步动作不同）。
_EMPTY_TEXT_REASONS = frozenset({ERROR_PARSE_EMPTY, ERROR_PARSE_FAILED, "", None})


def _is_empty_text_reason(reason: Any) -> bool:
    """该失败原因是否仅表示「拿不到文字」，而非「文件本身有确定性问题」。"""
    return reason in _EMPTY_TEXT_REASONS
