"""把「草稿里的段」导出成 zip —— 没跑过自动拆分的材料也有导出。

## 为什么需要这条链路

现成的下载入口全挂在**后端拆分任务**上（`segments/{id}/pdf`、`/download`）：段必须
有 `splitRef`（自动分段落地时写入）才给按钮。但律师完全可以**不跑自动分段**——
自己切页、改名、旋转之后直接归案。这种包在界面上一个导出按钮都没有
（`SegmentDownloadBar` 整块不渲染），数据却是全的：段名与页区间在草稿里，源附件
也在收件箱里。缺的只是一个「按草稿切页并打包」的服务端动作。

## 契约（`POST /pdf-splitting/export-draft`，multipart）

- ``files``：一份素材一个文件，**文件名必须是** ``part_<partIndex>.<ext>``。
  用文件名当键而不是「按顺序对应」：客户端可能因为某份素材读不出来而少发一个，
  按顺序对应会让后面每份都错位——表现是「导出包里的内容和段名对不上」，
  这种错几乎没人能一眼看出来。
- ``spec``：JSON 字符串
  ``{"segments": [{"name": "起诉状", "part_index": 0, "page_start": 1, "page_end": 4,
                    "rotations": "1:90,2:90", "md": "..."}]}``
- 出参：``application/zip``，包内平铺 ``NN-<名字>.pdf``；有 Markdown 的段配同名 ``.md``
  （与既有整包下载同结构，律师学一次就够）。

## 为什么 PDF 在服务端切、图片原样收

PDF 的切页（`export_segment_pdf`）与页旋转（`apply_page_rotations`）都只有一份
实现，必须复用；图片素材没有页对象，前端提交前已按旋转重编码（与归案上传同一条
路径），服务端原样收进包里。

## 坏段是怎么处理的

页区间越界、素材缺失、文件打不开 → **跳过这一段并计数**，其余照常导出；一段都
导不出来时才报错。理由：导出是补救手段，不该因为草稿里有一段脏数据就整包失败；
但也不能静默少几份——数量通过响应头 ``X-Export-Skipped`` 回给前端提示。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

import pymupdf as fitz

from apps.core.exceptions import ValidationException
from apps.pdf_splitting.services.split.export_utils import deduplicate_filename, export_segment_pdf
from apps.pdf_splitting.services.split.output_rotation import apply_page_rotations, merge_page_rotations
from apps.pdf_splitting.services.split.service import _zip_bytes

logger = logging.getLogger("apps.pdf_splitting")

#: 单次导出的段数上限：草稿是前端可改的 JSON，不能让它无限放大服务端内存
MAX_SEGMENTS = 500
#: 每份素材的体积上限（与 /jobs 的 MAX_FILE_SIZE 同量级；超出直接 400）
MAX_FILE_BYTES = 200 * 1024 * 1024

_INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


@dataclass(frozen=True)
class DraftExportSegment:
    """一段要导出的内容（草稿里的段投影）。"""

    name: str
    part_index: int
    page_start: int
    page_end: int
    rotations: str = ""
    md: str = ""


def parse_spec(raw: str) -> list[DraftExportSegment]:
    """``spec`` JSON → 段列表。结构性错误 → 400（不是「跳过」：那说明调用方拼错了）。"""
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValidationException(message="导出参数不是合法 JSON", errors={"spec": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise ValidationException(message="导出参数格式不正确", errors={"spec": "应为对象"})
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValidationException(message="没有可导出的分段", errors={"segments": "至少一段"})
    if len(raw_segments) > MAX_SEGMENTS:
        raise ValidationException(message=f"分段过多（上限 {MAX_SEGMENTS} 段）", errors={"segments": len(raw_segments)})

    segments: list[DraftExportSegment] = []
    for index, item in enumerate(raw_segments):
        if not isinstance(item, dict):
            raise ValidationException(message=f"第 {index + 1} 段格式不正确", errors={"segments": index})
        try:
            part_index = int(item.get("part_index", -1))
            page_start = int(item.get("page_start", 0))
            page_end = int(item.get("page_end", 0))
        except (TypeError, ValueError) as exc:
            raise ValidationException(
                message=f"第 {index + 1} 段的素材或页范围不是整数", errors={"segments": index}
            ) from exc
        if part_index < 0 or page_start < 1 or page_end < page_start:
            raise ValidationException(
                message=f"第 {index + 1} 段的页范围不合法",
                errors={"segments": f"[{index}] {page_start}-{page_end}"},
            )
        segments.append(
            DraftExportSegment(
                name=str(item.get("name") or f"第{index + 1}段"),
                part_index=part_index,
                page_start=page_start,
                page_end=page_end,
                rotations=str(item.get("rotations") or ""),
                md=str(item.get("md") or ""),
            )
        )
    return segments


def collect_files(uploaded: list[Any]) -> dict[int, tuple[str, bytes]]:
    """``part_<n>.<ext>`` 上传文件 → ``{partIndex: (原始名, 字节)}``。

    文件名不合约定 / 体积超限直接 400：那是调用方的编程错误，静默跳过会让
    「导出包里少一份材料」变成一个查不出来的谜。
    """
    files: dict[int, tuple[str, bytes]] = {}
    for upload in uploaded:
        name = str(getattr(upload, "name", "") or "")
        match = re.fullmatch(r"part_(\d+)(\.[A-Za-z0-9]{1,6})?", name)
        if match is None:
            raise ValidationException(message="素材文件名必须形如 part_<序号>.<扩展名>", errors={"files": name[:80]})
        size = int(getattr(upload, "size", 0) or 0)
        if size > MAX_FILE_BYTES:
            raise ValidationException(message=f"素材 {name} 体积超限", errors={"files": name[:80]})
        files[int(match.group(1))] = (name, upload.read())
    if not files:
        raise ValidationException(message="没有收到素材文件", errors={"files": "empty"})
    return files


def build_export_zip(
    files: dict[int, tuple[str, bytes]],
    segments: list[DraftExportSegment],
) -> tuple[bytes, int]:
    """按草稿分段切页打包，返回 ``(zip 字节, 被跳过的段数)``。

    Raises:
        ValidationException: 一段都没能导出（全被跳过）——此时返回空包等于骗人。
    """
    entries: list[tuple[str, bytes]] = []
    seen_names: set[str] = set()
    skipped = 0

    # 每份素材只打开一次、只烧一次旋转：同一 part 的多段共用一份 doc；
    # 逐段 apply 会把同一页转两次（90+90=180），是这条链路最容易犯的错。
    docs: dict[int, Any] = {}
    try:
        for seq, segment in enumerate(segments, start=1):
            payload = files.get(segment.part_index)
            if payload is None:
                logger.warning(
                    "draft_export_skip_missing_part",
                    extra={"part_index": segment.part_index, "segment": segment.name},
                )
                skipped += 1
                continue
            original_name, content = payload
            stem = _safe_stem(segment.name)

            if _looks_like_pdf(original_name, content):
                doc = docs.get(segment.part_index)
                if doc is None:
                    try:
                        doc = fitz.open(stream=content, filetype="pdf")
                    except (RuntimeError, ValueError) as exc:
                        logger.warning(
                            "draft_export_skip_bad_pdf",
                            extra={"part_index": segment.part_index, "error": str(exc)},
                        )
                        skipped += 1
                        continue
                    apply_page_rotations(doc, merge_page_rotations(_rotations_of_part(segments, segment.part_index)))
                    docs[segment.part_index] = doc
                if segment.page_end > int(doc.page_count):
                    logger.warning(
                        "draft_export_skip_out_of_range",
                        extra={
                            "part_index": segment.part_index,
                            "segment": segment.name,
                            "page_end": segment.page_end,
                            "page_count": int(doc.page_count),
                        },
                    )
                    skipped += 1
                    continue
                content_out = export_segment_pdf(doc, segment.page_start, segment.page_end)
                entries.append((deduplicate_filename(f"{seq:02d}-{stem}.pdf", seen_names), content_out))
            else:
                # 图片素材：前端已按旋转重编码，这里原样收（保留原扩展名）
                suffix = PurePath(original_name).suffix or ".png"
                entries.append((deduplicate_filename(f"{seq:02d}-{stem}{suffix}", seen_names), content))

            if segment.md.strip():
                entries.append((deduplicate_filename(f"{seq:02d}-{stem}.md", seen_names), segment.md.encode("utf-8")))
    finally:
        for doc in docs.values():
            doc.close()

    if not entries:
        raise ValidationException(
            message="没有可导出的内容（分段与素材对不上，或文件无法解析）",
            errors={"segments": len(segments), "skipped": skipped},
        )
    return _zip_bytes(entries), skipped


def _rotations_of_part(segments: list[DraftExportSegment], part_index: int) -> list[str]:
    return [seg.rotations for seg in segments if seg.part_index == part_index and seg.rotations]


def _looks_like_pdf(name: str, content: bytes) -> bool:
    if content[:4] == b"%PDF":
        return True
    return name.lower().endswith(".pdf")


def _safe_stem(name: str) -> str:
    """段名 → 文件名主干：去掉路径分隔符与控制字符、压掉首尾空白。"""
    cleaned = _INVALID_NAME_CHARS.sub("_", (name or "").strip()).strip(" .")
    return cleaned[:80] or "未命名材料"
