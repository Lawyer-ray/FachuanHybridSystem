"""收件箱消息 MCP tools"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from mcp_server.client import client
from mcp_server.tool_shaping import list_result

#: 列表项里最多保留几个附件名。
#:
#: 收件箱列表现在带附件元信息（文件名/页数），这是好事——模型不用为「这封邮件
#: 有什么材料」再跑一次详情；但**原始元信息一条就约 200 字节**（8 个字段 + 键名），
#: 一封法院送达带 6 份文书就能让单条从 0.57KB 涨到 1.8KB。pi 对工具输出 20KB 起
#: 腰斩（见 `tool_shaping.list_result` 的说明），不收敛就会在默认调用上被拦腰
#: 截断——模型看到的是半截 JSON，而不是一个「还能翻页」的信封。
#:
#: 所以列表只做「有哪几份材料」的投影（名字 + 页数）；要看全部字段/正文/下载
#: 走 `get_inbox_message`。
MAX_ATTACHMENTS_PER_ROW = 3


def _compact_row(item: dict[str, Any]) -> dict[str, Any]:
    """列表投影：附件只留「名字 + 页数」（最多 3 份），其余走详情工具。

    没有附件（或老后端不带该字段）时把 `attachments` 整个去掉——空数组在
    每行白占 16 字节，在 20KB 的预算里不是零成本。
    """
    attachments = item.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        return {k: v for k, v in item.items() if k != "attachments"}

    compact: list[dict[str, Any]] = []
    for att in attachments[:MAX_ATTACHMENTS_PER_ROW]:
        if not isinstance(att, dict):
            continue
        name = str(att.get("custom_filename") or att.get("original_filename") or att.get("filename") or "")
        compact.append({"filename": name, "pages": int(att.get("page_count") or 0)})

    row = {**item, "attachments": compact}
    if len(attachments) > MAX_ATTACHMENTS_PER_ROW:
        # 让模型知道「还有几份没列出来」，而不是误以为这份材料只有 3 个附
        row["attachments_truncated"] = len(attachments) - MAX_ATTACHMENTS_PER_ROW
    return row


def list_inbox_messages(
    source_id: Annotated[int | None, Field(description="按消息来源筛选(来源 ID 见 list_message_sources)")] = None,
    has_attachments: Annotated[bool | None, Field(description="按是否有附件筛选")] = None,
    search: Annotated[str | None, Field(description="主题/发件人/正文关键词")] = None,
    limit: Annotated[int, Field(description="最多返回条数(默认 20,约 0.7KB/条,默认调用留在 20KB 截断线内)", ge=1)] = 20,
    offset: Annotated[
        int, Field(description="跳过前 offset 条再取——truncated=true 时续取翻页用(第 N 页传 offset=N×limit)", ge=0)
    ] = 0,
) -> dict[str, Any]:
    """查询收件箱消息列表。可按来源（source_id）、是否有附件（has_attachments）、关键词（search）筛选。

    每行带 `attachments`（前 3 份的**文件名 + 页数**，超出部分记在
    `attachments_truncated`）——扫描件的主题行常常等于没信息（`Attached Image`），
    材料名才是判断依据。全字段 / 正文 / 附件字节请用 `get_inbox_message`。

    limit 默认 20（实测约 0.7KB/条,20 条 ≈ 14KB——pi 对工具输出 20KB 起
    腰斩,默认调用应留在截断线内;REST 端点默认 500 是给前端收件箱的）;
    truncated=true 时用 offset 续取(第 N 页传 offset=N×limit),或换更窄筛选。

    Args:
        source_id: 按消息来源筛选。
        has_attachments: 按是否有附件筛选。
        search: 主题/发件人/正文关键词。
        limit: 最多返回条数(默认 30)。
        offset: 跳过前 offset 条再取——续取翻页用。
    """
    params: dict[str, Any] = {"limit": limit + 1, "offset": offset}  # limit+1 探测:知还有更多
    if source_id is not None:
        params["source_id"] = source_id
    if has_attachments is not None:
        params["has_attachments"] = has_attachments
    if search:
        params["search"] = search
    items = client.get("/inbox/messages", params=params)
    rows = [_compact_row(item) for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    return list_result(rows, limit=limit)


def get_inbox_message(message_id: int) -> dict[str, Any]:
    """获取单条消息的详细信息，包含正文（text/html）和附件列表。

    注意：材料包的预处理草稿（draft_state）虽随本工具原样返回，但整份草稿
    远超 pi 的 20KB 工具输出截断线——读分段正文请用 get_material_draft_segments。
    """
    return client.get(f"/inbox/messages/{message_id}")  # type: ignore[no-any-return]


#: 单段 md 窗口的字符上限与字节预算。pi 对工具输出按 20480 字节拦腰截断
#: （client.py 实测口径）：信封 + 段投影约 1-2KB，md 正文预算 16000 字节；
#: 字符窗口 6000（中文 UTF-8 3 字节/字 = 18000，必触发字节兜底 ≈ 5333 字），
#: 与 fetch_url._BYTE_BUDGET 同一原则——截断发生在截断线之前且可续读。
_MD_WINDOW_CHARS = 6000
_MD_BYTE_BUDGET = 16_000


def get_material_draft_segments(
    message_id: int,
    offset: Annotated[
        int, Field(description="目录模式：跳过前 offset 段再取（翻页用，第 N 页传 offset=N×limit）", ge=0)
    ] = 0,
    limit: Annotated[
        int, Field(description="目录模式：最多返回段数（默认 5，投影约 0.4KB/段，留在 20KB 截断线内）", ge=1, le=20)
    ] = 5,
    segment_index: Annotated[
        int | None,
        Field(description="单段模式：取该段（0 起，见目录模式的 segment_index）的 md 全文；不传则只返回段目录", ge=0),
    ] = None,
    md_offset: Annotated[
        int, Field(description="单段模式：md 字符偏移续读——md_truncated=true 时传 next_md_offset 取下一窗口", ge=0)
    ] = 0,
) -> dict[str, Any]:
    """读取材料包预处理草稿的分段正文（律师在材料预处理中核对过的 Markdown）。

    已预处理的材料包优先用本工具读正文，不要把附件 base64 上传重新解析——
    重解析拿不到律师的人工校对成果，质量更差且重复计费。

    两种用法：
    - 目录模式（默认）：只投影段名/类型/页区间/quality_flags/md 长度，不含 md
      本体；offset/limit 按段翻页，truncated=true 时用 offset 续取。
    - 单段模式：传 segment_index 取该段 md；md 超长按窗口截断，
      md_truncated=true 时以 md_offset=next_md_offset 续读同一段。

    权限与 get_inbox_message 一致（REST 端点按上传人/管理员收敛，无权返回 404）。
    草稿为空（未做自动识别）时 total_segs=0——此时再走解析工具读附件。

    Args:
        message_id: 材料包对应的收件箱消息 ID。
        offset: 目录模式分段偏移。
        limit: 目录模式每页段数。
        segment_index: 单段模式的段下标（0 起）。
        md_offset: 单段模式 md 字符偏移。
    """
    msg = client.get(f"/inbox/messages/{message_id}")
    draft = (msg or {}).get("draft_state") or {}
    segs = draft.get("segs") or []
    if not isinstance(segs, list):
        segs = []

    if segment_index is not None:
        if segment_index >= len(segs):
            raise ValueError(f"segment_index={segment_index} 越界：该材料包草稿共 {len(segs)} 段")
        return _segment_md_window(message_id, segs[segment_index], segment_index, md_offset)

    window = segs[offset : offset + limit]
    return {
        "message_id": message_id,
        "total_segs": len(segs),
        "offset": offset,
        "returned": len(window),
        "truncated": offset + len(window) < len(segs),
        "items": [_project_segment(seg, offset + i) for i, seg in enumerate(window)],
    }


def _project_segment(seg: dict[str, Any], index: int) -> dict[str, Any]:
    """段投影：只取起草需要的字段，blocks/坐标等大字段不进工具输出。"""
    md = seg.get("md") or ""
    return {
        "segment_index": index,
        "id": seg.get("id") or "",
        "name": seg.get("fn") or "",
        "type": seg.get("t") or "",
        "pages": _seg_pages(seg),
        "quality_flags": seg.get("qualityFlags") or [],
        "review_flag": seg.get("reviewFlag") or "",
        "confidence": seg.get("confidence"),
        "manual_edit": bool((seg.get("manualEdit") or {}).get("md")),
        "md_chars": len(md),
    }


def _seg_pages(seg: dict[str, Any]) -> list[dict[str, int]]:
    """refs（[{mi: 来源附件下标, p: 页码}]）按附件聚合成页区间。"""
    by_part: dict[int, list[int]] = {}
    for ref in seg.get("refs") or []:
        if not isinstance(ref, dict):
            continue
        mi, p = ref.get("mi"), ref.get("p")
        if isinstance(mi, int) and isinstance(p, int):
            by_part.setdefault(mi, []).append(p)
    return [{"part_index": mi, "page_start": min(ps), "page_end": max(ps)} for mi, ps in sorted(by_part.items())]


def _segment_md_window(message_id: int, seg: dict[str, Any], index: int, md_offset: int) -> dict[str, Any]:
    """单段 md 窗口：字符切窗 + UTF-8 字节兜底，next_md_offset 按实际送达字符推进。"""
    md = seg.get("md") or ""
    window = md[md_offset : md_offset + _MD_WINDOW_CHARS]
    encoded = window.encode("utf-8")
    if len(encoded) > _MD_BYTE_BUDGET:
        # 字节刀落在多字节字符中段时丢弃残字，续读偏移按实际送达字符数推进
        window = encoded[:_MD_BYTE_BUDGET].decode("utf-8", errors="ignore")
    next_offset = md_offset + len(window)
    truncated = next_offset < len(md)
    return {
        "message_id": message_id,
        "segment": {**_project_segment(seg, index), "md": window},
        "md_total_chars": len(md),
        "md_offset": md_offset,
        "md_truncated": truncated,
        "next_md_offset": next_offset if truncated else None,
    }


def rename_inbox_attachment(
    message_id: int,
    part_index: int,
    custom_filename: str,
) -> dict[str, Any]:
    """重命名消息附件。custom_filename 为空字符串时恢复原始文件名。"""
    payload: dict[str, Any] = {"custom_filename": custom_filename}
    return client.post(  # type: ignore[no-any-return]
        f"/inbox/messages/{message_id}/attachments/{part_index}/rename",
        json=payload,
    )


def download_inbox_attachment(message_id: int, part_index: int) -> dict[str, Any]:
    """下载消息附件，返回文件内容（base64 编码）。"""
    content, filename, content_type = client.download(
        f"/inbox/messages/{message_id}/attachments/{part_index}/download",
    )
    import base64

    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode("ascii"),
    }


def preview_inbox_attachment(message_id: int, part_index: int) -> dict[str, Any]:
    """预览消息附件（在线查看），返回文件内容（base64 编码）。"""
    content, filename, content_type = client.download(
        f"/inbox/messages/{message_id}/attachments/{part_index}/preview",
    )
    import base64

    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode("ascii"),
    }
