"""预处理 Markdown → 证据 chunk 的适配与切分（起草消费预处理成果）。

ensure_ingested 入库前先经此找回律师核对过的分段 md：有则直接切 chunk
（全量，不受 max_pages_per_item 限制），无则回落 pymupdf 重新抽文本。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

logger = logging.getLogger("apps.litigation_ai")

if TYPE_CHECKING:
    from apps.cases.services.material.material_draft_md_service import DraftSegmentMd

#: md chunk 目标长度（字符）。与现有「一页一 chunk」粒度对齐： dense A4 页约
#: 1500-2500 字，1500 字落在常见嵌入模型输入上限内，避免整段（可达数万字）
#: 被嵌入端截断导致尾部内容检索不到。
MD_CHUNK_CHARS = 1500

#: 区别于 text/ocr/no_text，检索与观测可识别预处理来源。
EXTRACTION_METHOD_MD = "preprocessed_md"


class EvidenceDraftMdService:
    def find_draft_segments(self, evidence_item_id: int) -> list[DraftSegmentMd]:
        """按证据项找回预处理分段；任何失败都降级为空（走原抽文本路径）。"""
        # 跨模块只 import 服务（不 import Model）：cases 服务 + 本域 wiring。
        from apps.cases.services.material.material_draft_md_service import MaterialDraftMdService

        from ..wiring import get_evidence_service

        try:
            evidence_service = cast(Any, get_evidence_service())
            item = evidence_service.query_service.get_evidence_item(evidence_item_id)
            file_hash = item.file_hash or ""
            case_id = item.evidence_list.case_id
            if not file_hash or not case_id:
                return []
            return MaterialDraftMdService().find_draft_segments_for_file(case_id, file_hash)
        except Exception:
            # md 查找是增强而非必需：失败不能阻断起草，回落原路径并留痕。
            logger.warning("预处理 md 查找失败，回落重新抽文本: item=%s", evidence_item_id, exc_info=True)
            return []


def chunks_from_draft_segments(segments: list[DraftSegmentMd]) -> list[dict[str, Any]]:
    """分段 md → chunk。首块带段页区间；续块 page_start=None。

    唯一约束 (evidence_item, page_start) 要求同证据 chunk 起始页互异；md 无页
    锚点，续块页码不可考——置 None（NULLS DISTINCT 不撞约束，也是负缓存标记
    的既有取值），比起伪造页码误导引用更诚实。
    """
    chunks: list[dict[str, Any]] = []
    for seg in segments:
        for i, text in enumerate(split_md(seg.md)):
            chunks.append(
                {
                    "page_start": seg.page_start if i == 0 else None,
                    "page_end": seg.page_end if i == 0 else None,
                    "text": text,
                    "extraction_method": EXTRACTION_METHOD_MD,
                }
            )
    return chunks


def split_md(md: str) -> list[str]:
    """按段落边界切到 ≤MD_CHUNK_CHARS；超长单段（怪兽表格行）硬切。"""
    chunks: list[str] = []
    buf = ""
    for para in md.split("\n\n"):
        if not para.strip():
            continue
        if len(para) > MD_CHUNK_CHARS:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(para[i : i + MD_CHUNK_CHARS] for i in range(0, len(para), MD_CHUNK_CHARS))
            continue
        candidate = f"{buf}\n\n{para}" if buf else para
        if len(candidate) > MD_CHUNK_CHARS:
            chunks.append(buf)
            buf = para
        else:
            buf = candidate
    if buf:
        chunks.append(buf)
    return chunks
