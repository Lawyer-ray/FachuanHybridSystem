"""材料预处理 Markdown 查找服务（起草 RAG 消费预处理成果的查询侧）。

链路：证据文件 SHA-256 ↔ 归案绑定附件哈希（CaseMaterial.source_file_hash）
→ 溯源（source_message_id / source_segment_ref）→ inbox draft_state.segs[].md。
律师在材料预处理里核对过的 md 由此进入起草，跳过 pymupdf 重新抽纯文本。

权限边界：只查「本案」材料的溯源——md 对应的 PDF 字节已随归案进入本案，
能读本案证据的律师本就能读这些材料，不额外泄露 inbox 归属。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.cases.models import CaseMaterial

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DraftSegmentMd:
    """一段预处理 Markdown 及其页区间（页码来自 draft refs，1 起）。"""

    segment_ref: str
    name: str
    page_start: int | None
    page_end: int | None
    md: str


def compute_file_sha256(path: str | Path) -> str:
    """流式哈希；文件不可读返回空串——溯源降级为无哈希，不阻断绑定/入库。"""
    h = hashlib.sha256()
    try:
        with Path(path).open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        logger.warning("溯源哈希计算失败（文件不可读）: %s", path)
        return ""
    return h.hexdigest()


def draft_segs(draft_state: Any) -> list[dict[str, Any]]:
    """draft_state 是前端定义的不透明 JSON，这里只取语义稳定的 segs 列表。"""
    segs = (draft_state or {}).get("segs") or []
    return [s for s in segs if isinstance(s, dict)]


def seg_page_range(seg: dict[str, Any]) -> tuple[int | None, int | None]:
    pages = [r["p"] for r in seg.get("refs") or [] if isinstance(r, dict) and isinstance(r.get("p"), int)]
    return (min(pages), max(pages)) if pages else (None, None)


def seg_covers_part(seg: dict[str, Any], part_index: int) -> bool:
    return any(isinstance(r, dict) and r.get("mi") == part_index for r in seg.get("refs") or [])


def to_draft_segment(seg: dict[str, Any]) -> DraftSegmentMd | None:
    md = (seg.get("md") or "").strip()
    if not md:
        return None
    start, end = seg_page_range(seg)
    return DraftSegmentMd(
        segment_ref=str(seg.get("id") or ""),
        name=str(seg.get("fn") or ""),
        page_start=start,
        page_end=end,
        md=md,
    )


class MaterialDraftMdService:
    def find_draft_segments_for_file(self, case_id: int, file_hash: str) -> list[DraftSegmentMd]:
        """按证据文件哈希找回预处理分段 md；找不到返回空（调用方走原抽文本路径）。

        两级匹配（都是逐字节哈希，确定性、可单测）：
        1. 段级：证据文件与某归案绑定附件逐字节一致（律师把切页材料传为证据）；
        2. 包级：证据文件与某来源附件逐字节一致（律师把整卷原包传为证据），
           取该附件覆盖的全部段——整包证据由此吃全量 md，不受 20 页上限。
        """
        if not file_hash:
            return []
        matched = self._load_seg_md(self._match_material_refs(case_id, file_hash))
        if matched:
            return matched
        return self._match_pack_level(case_id, file_hash)

    def _match_material_refs(self, case_id: int, file_hash: str) -> dict[int, set[str]]:
        rows = (
            CaseMaterial.objects.filter(case_id=case_id, source_file_hash=file_hash)
            .exclude(source_message_id=None)
            .values_list("source_message_id", "source_segment_ref")
        )
        refs: dict[int, set[str]] = {}
        for message_id, segment_ref in rows:
            if message_id is None:
                continue
            refs.setdefault(message_id, set()).add(segment_ref)
        return refs

    def _load_seg_md(self, refs: dict[int, set[str]]) -> list[DraftSegmentMd]:
        if not refs:
            return []
        # 跨模块只 import message_hub 的服务函数（不 import 其 Model）：
        # core 协议面没有 inbox 查询接口，服务层直读是既有先例的最小路径。
        from apps.message_hub.services.inbox_query import get_message_or_none

        out: list[DraftSegmentMd] = []
        for message_id, ref_set in refs.items():
            msg = get_message_or_none(message_id)
            if msg is None:
                logger.info("溯源消息已删除，跳过预处理 md: message_id=%s", message_id)
                continue
            # 按草稿段序输出（保持卷宗顺序），不按匹配集合的无序遍历
            for seg in draft_segs(msg.draft_state):
                if str(seg.get("id") or "") not in ref_set:
                    continue
                draft = to_draft_segment(seg)
                if draft is not None:
                    out.append(draft)
        return out

    def _match_pack_level(self, case_id: int, file_hash: str) -> list[DraftSegmentMd]:
        from apps.message_hub.services.base import resolve_media_attachment_path
        from apps.message_hub.services.inbox_query import get_message_or_none

        message_ids = (
            CaseMaterial.objects.filter(case_id=case_id)
            .exclude(source_message_id=None)
            .values_list("source_message_id", flat=True)
            .distinct()
        )
        for message_id in message_ids:
            if message_id is None:
                continue
            msg = get_message_or_none(message_id)
            if msg is None:
                continue
            for att in msg.attachments_meta or []:
                if not isinstance(att, dict):
                    continue
                path = resolve_media_attachment_path(str(att.get("local_path", "")))
                if path is None or compute_file_sha256(path) != file_hash:
                    continue
                part_index = att.get("part_index")
                if not isinstance(part_index, int):
                    continue
                drafts: list[DraftSegmentMd] = []
                for seg in draft_segs(msg.draft_state):
                    if not seg_covers_part(seg, part_index):
                        continue
                    draft = to_draft_segment(seg)
                    if draft is not None:
                        drafts.append(draft)
                if drafts:
                    return drafts
        return []
