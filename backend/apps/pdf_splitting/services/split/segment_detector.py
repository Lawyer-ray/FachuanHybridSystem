"""段落检测与评分算法。"""

from __future__ import annotations

import logging
from typing import Any

from apps.core.services.storage_service import sanitize_upload_filename
from apps.pdf_splitting.models import PdfSplitReviewFlag, PdfSplitSegmentType
from apps.pdf_splitting.services.template_registry import (
    SegmentTemplateRule,
    get_default_filename,
    get_template_definition,
)

from .split_models import _NON_WORD_RE, _TEXT_MIN_LENGTH, PageDescriptor, SegmentDraft, _levenshtein_distance

logger = logging.getLogger("apps.pdf_splitting")


#: 模糊匹配的二元组重合率下限。低于它直接判定「不可能模糊命中」。
#:
#: 取值理由：编辑距离 ≤2 时，长度 ≤10 的关键词至少保留 8 个字符，二元组重合率
#: 通常 >0.7；0.5 留足余量，同时能把大量「完全不相干的关键词」一次性筛掉。
_FUZZY_BIGRAM_PREFILTER = 0.5


def _bigrams(text: str) -> set[str]:
    """字符串的全部相邻二元组（长度 <2 时退化为单字集合）。"""
    if len(text) < 2:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


class SegmentDetector:
    """段落检测、评分、补全未识别区间（LLM 不可用时的降级兜底）。"""

    COMPLAINT_MAX_SPAN = 20
    COMPLAINT_TERMINAL_KEYWORDS = ("此致", "具状人", "起诉人", "起诉状具状人", "日期")
    COMPLAINT_ATTACHMENT_KEYWORDS = (
        "证据",
        "借条",
        "转账",
        "聊天记录",
        "微信",
        "支付宝",
        "发票",
        "授权委托书",
        "居民身份证",
        "送达地址确认书",
    )

    # ------------------------------------------------------------------
    # 文本工具
    # ------------------------------------------------------------------

    def normalize_text(self, value: str) -> str:
        return _NON_WORD_RE.sub("", value or "")

    def contains_keyword(self, haystack: str, keyword: str) -> bool:
        return self.normalize_text(keyword) in haystack

    def fuzzy_contains_keyword(
        self,
        haystack: str,
        keyword: str,
        *,
        haystack_bigrams: set[str] | None = None,
    ) -> tuple[bool, float]:
        """
        模糊匹配关键词。

        返回 (是否匹配, 衰减系数)。
        - 精确匹配：系数 1.0
        - 模糊匹配（编辑距离 > 0）：系数 0.8
        - 不匹配：(False, 0.0)

        编辑距离阈值规则：
        - 关键词长度 <= 3：仅精确匹配
        - 关键词长度 4-6：允许编辑距离 <= 1
        - 关键词长度 > 6：允许编辑距离 <= 2
        """
        normalized_kw = self.normalize_text(keyword)
        kw_len = len(normalized_kw)

        if not normalized_kw:
            return False, 0.0

        if normalized_kw in haystack:
            return True, 1.0

        if kw_len <= 3:
            return False, 0.0

        max_dist = 1 if kw_len <= 6 else 2

        # 大前提过滤（2026-11-24 实测：40 页卷宗这里跑了 540 万次 Levenshtein，
        # 占掉整份取字的 20s）。编辑距离 ≤2 的片段必然**保留绝大多数二元组**，
        # 所以先用二元组重合率做一次 O(len) 的筛：重合率过低的关键词根本不可能
        # 模糊命中，直接返回，不必再滑窗逐位算距离。
        if haystack_bigrams is not None:
            keyword_bigrams = _bigrams(normalized_kw)
            if keyword_bigrams:
                overlap = len(keyword_bigrams & haystack_bigrams) / len(keyword_bigrams)
                if overlap < _FUZZY_BIGRAM_PREFILTER:
                    return False, 0.0

        window_size = kw_len + max_dist
        for i in range(max(1, len(haystack) - window_size + 1)):
            fragment = haystack[i : i + window_size]
            if _levenshtein_distance(fragment, normalized_kw) <= max_dist:
                return True, 0.8

        return False, 0.0

    def is_effective_text(self, value: str) -> bool:
        normalized = self.normalize_text(value)
        return len(normalized) >= _TEXT_MIN_LENGTH

    # ------------------------------------------------------------------
    # 评分
    # ------------------------------------------------------------------

    def score_page(self, *, head_text: str, normalized_text: str, template_key: str) -> list[dict[str, Any]]:
        template = get_template_definition(template_key)
        # 整页文字只算一次二元组集合，供下面每个关键词做前缀过滤
        haystack_bigrams = _bigrams(normalized_text)
        candidates: list[dict[str, Any]] = []
        for rule in template.rules:
            score = 0.0
            matched_strong: list[str] = []
            matched_weak: list[str] = []

            strong_score = 0.0
            for kw in rule.strong_keywords:
                hit, decay = self.fuzzy_contains_keyword(normalized_text, kw, haystack_bigrams=haystack_bigrams)
                if hit:
                    matched_strong.append(kw)
                    strong_score += (0.4 + 0.18) * decay
                    head_hit, _head_decay = self.fuzzy_contains_keyword(head_text, kw)
                    if head_hit:
                        strong_score += 0.15 * decay
            score += min(0.75, strong_score)

            for kw in rule.weak_keywords:
                hit, _decay = self.fuzzy_contains_keyword(normalized_text, kw, haystack_bigrams=haystack_bigrams)
                if hit:
                    matched_weak.append(kw)
            if matched_weak:
                score += min(0.2, 0.08 * len(matched_weak))

            matched_negative = [kw for kw in rule.negative_keywords if self.contains_keyword(normalized_text, kw)]
            if matched_negative:
                score -= min(0.4, 0.12 * len(matched_negative))

            score = round(max(score, 0.0), 3)

            if matched_strong and score >= 0.30:
                candidates.append(
                    {
                        "segment_type": rule.segment_type,
                        "label": rule.label,
                        "score": score,
                        "matched_strong": matched_strong,
                        "matched_weak": matched_weak,
                    }
                )
            elif not matched_strong and len(matched_weak) >= 2:
                candidates.append(
                    {
                        "segment_type": rule.segment_type,
                        "label": rule.label,
                        "score": score,
                        "matched_strong": [],
                        "matched_weak": matched_weak,
                        "weak_only": True,
                    }
                )

        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[:3]

    # ------------------------------------------------------------------
    # 段落检测
    # ------------------------------------------------------------------

    def detect_segments(self, pages: list[PageDescriptor], *, template_key: str) -> list[SegmentDraft]:
        template = get_template_definition(template_key)
        start_candidates: list[dict[str, Any]] = []
        previous_layout_title = ""
        previous_page_type = ""
        previous_page_title = ""
        for page in pages:
            if page.top_candidates:
                top = page.top_candidates[0]
                current_type = str(top["segment_type"])
                current_title = _normalize_title(page.layout_title)
                repeated_continuation = (
                    current_type == previous_page_type
                    and page.page_no > 1
                    and (not current_title or current_title == previous_page_title)
                )
                if not repeated_continuation:
                    start_candidates.append(
                        {
                            "page_no": page.page_no,
                            "segment_type": top["segment_type"],
                            "score": float(top["score"]),
                            "weak_only": bool(top.get("weak_only", False)),
                        }
                    )
                previous_page_type = current_type
                previous_page_title = current_title
                if page.layout_title:
                    previous_layout_title = _normalize_title(page.layout_title)
                continue
            previous_page_type = ""
            previous_page_title = ""
            title = _normalize_title(page.layout_title)
            if not title:
                continue
            if title == previous_layout_title:
                continue
            previous_layout_title = title
            start_candidates.append(
                {
                    "page_no": page.page_no,
                    "segment_type": PdfSplitSegmentType.UNRECOGNIZED,
                    "score": 0.5,
                    "weak_only": True,
                    "layout_title": page.layout_title,
                }
            )

        all_candidates = sorted(start_candidates, key=lambda c: c["page_no"])

        segments: list[SegmentDraft] = []
        for index, start in enumerate(all_candidates):
            following = all_candidates[index + 1] if index + 1 < len(all_candidates) else None
            next_start_page = following["page_no"] if following else len(pages) + 1

            end_page = next_start_page - 1
            if start["segment_type"] == PdfSplitSegmentType.COMPLAINT:
                end_page = self._find_complaint_end(pages, start["page_no"], next_start_page - 1, template.rules[0])
                if (
                    segments
                    and segments[-1].segment_type == PdfSplitSegmentType.COMPLAINT
                    and start["page_no"] == segments[-1].page_end + 1
                ):
                    continue

            review_flag = PdfSplitReviewFlag.NORMAL
            source_method = "rule"
            confidence = start["score"]

            if start.get("layout_title"):
                review_flag = PdfSplitReviewFlag.LOW_CONFIDENCE
                source_method = "layout_title"
                confidence = float(start["score"])
            elif start.get("weak_only"):
                review_flag = PdfSplitReviewFlag.LOW_CONFIDENCE
                source_method = "rule_weak_only"

            previous = all_candidates[index - 1] if index > 0 else None
            if previous and previous["page_no"] == start["page_no"] - 1:
                if previous["segment_type"] == start["segment_type"]:
                    review_flag = PdfSplitReviewFlag.LOW_CONFIDENCE
                    source_method = "rule_adjacent_start"
                    confidence = min(confidence, 0.55)

            segments.append(
                SegmentDraft(
                    order=len(segments) + 1,
                    page_start=start["page_no"],
                    page_end=max(start["page_no"], end_page),
                    segment_type=start["segment_type"],
                    filename=_suggest_filename(start),
                    confidence=round(confidence, 3),
                    source_method=source_method,
                    review_flag=review_flag,
                )
            )

        merged_segments = self._merge_adjacent_pack_segments(segments)
        return self.fill_unrecognized_gaps(segments=merged_segments, total_pages=len(pages))

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _find_complaint_end(
        self,
        pages: list[PageDescriptor],
        start_page: int,
        max_end_page: int,
        rule: SegmentTemplateRule,
    ) -> int:
        upper_bound = min(max_end_page, start_page + self.COMPLAINT_MAX_SPAN - 1)
        end_page = start_page
        terminal_seen = False
        for page_no in range(start_page, upper_bound + 1):
            page = pages[page_no - 1]
            if page_no == start_page:
                end_page = page_no
                continue

            has_continuation = any(self.contains_keyword(page.normalized_text, kw) for kw in rule.continuation_keywords)
            has_attachment_signal = any(
                self.contains_keyword(page.normalized_text, kw) for kw in self.COMPLAINT_ATTACHMENT_KEYWORDS
            )
            if not has_continuation and has_attachment_signal:
                break

            end_page = page_no
            if any(self.contains_keyword(page.normalized_text, kw) for kw in self.COMPLAINT_TERMINAL_KEYWORDS):
                terminal_seen = True
                next_page = pages[page_no] if page_no < len(pages) else None
                if next_page and not any(
                    self.contains_keyword(next_page.normalized_text, kw) for kw in rule.continuation_keywords
                ):
                    break

        if terminal_seen:
            return end_page
        return min(end_page, upper_bound)

    def fill_unrecognized_gaps(self, *, segments: list[SegmentDraft], total_pages: int) -> list[SegmentDraft]:
        filled: list[SegmentDraft] = []
        cursor = 1
        ordered_segments = sorted(segments, key=lambda item: (item.page_start, item.page_end))
        for item in ordered_segments:
            if item.page_start > cursor:
                filled.append(
                    SegmentDraft(
                        order=len(filled) + 1,
                        page_start=cursor,
                        page_end=item.page_start - 1,
                        segment_type=PdfSplitSegmentType.UNRECOGNIZED,
                        filename=f"未识别材料_{cursor}-{item.page_start - 1}.pdf",
                        confidence=0.0,
                        source_method="gap_fill",
                        review_flag=PdfSplitReviewFlag.UNRECOGNIZED,
                    )
                )
            item.order = len(filled) + 1
            filled.append(item)
            cursor = item.page_end + 1

        if cursor <= total_pages:
            filled.append(
                SegmentDraft(
                    order=len(filled) + 1,
                    page_start=cursor,
                    page_end=total_pages,
                    segment_type=PdfSplitSegmentType.UNRECOGNIZED,
                    filename=f"未识别材料_{cursor}-{total_pages}.pdf",
                    confidence=0.0,
                    source_method="gap_fill",
                    review_flag=PdfSplitReviewFlag.UNRECOGNIZED,
                )
            )
        return filled

    def _merge_adjacent_pack_segments(self, segments: list[SegmentDraft]) -> list[SegmentDraft]:
        if not segments:
            return []

        merged: list[SegmentDraft] = []
        mergeable_types = {PdfSplitSegmentType.PARTY_IDENTITY}
        for item in sorted(segments, key=lambda value: (value.page_start, value.page_end)):
            if (
                merged
                and item.segment_type in mergeable_types
                and merged[-1].segment_type == item.segment_type
                and item.page_start == merged[-1].page_end + 1
            ):
                previous = merged[-1]
                merged[-1] = SegmentDraft(
                    order=previous.order,
                    page_start=previous.page_start,
                    page_end=item.page_end,
                    segment_type=previous.segment_type,
                    filename=previous.filename,
                    confidence=max(previous.confidence, item.confidence),
                    source_method="rule_merged_adjacent",
                    review_flag=(
                        PdfSplitReviewFlag.LOW_CONFIDENCE
                        if PdfSplitReviewFlag.LOW_CONFIDENCE in {previous.review_flag, item.review_flag}
                        else previous.review_flag
                    ),
                )
                continue

            item.order = len(merged) + 1
            merged.append(item)
        return merged


# ↓↓ 由 SegmentDetector 下沉的模块级纯函数（四层架构静态方法棘轮）
def _normalize_title(value: str) -> str:
    return "".join(char for char in (value or "").casefold() if char.isalnum() or "\u4e00" <= char <= "\u9fff")


# ↓↓ 由 SegmentDetector 下沉的模块级纯函数（四层架构静态方法棘轮）
def _suggest_filename(candidate: dict[str, Any]) -> str:
    # 先判原始标题再清洗：sanitize_upload_filename("") 的兜底名是 "file"，
    # 直接清洗空标题会把所有无版面标题的段命名成 file.pdf（92 页真实材料实测踩中）
    raw_title = str(candidate.get("layout_title") or "").strip()
    if raw_title:
        title = sanitize_upload_filename(raw_title)
        if title:
            return f"{title}.pdf"
    return f"{get_default_filename(candidate['segment_type'])}.pdf"
