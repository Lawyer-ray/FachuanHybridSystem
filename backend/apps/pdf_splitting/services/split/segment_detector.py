"""段落检测与评分算法。"""

from __future__ import annotations

import logging
from typing import Any

from apps.pdf_splitting.models import (
    PdfSplitReviewFlag,
    PdfSplitSegmentType,
)

from .split_models import (
    _NON_WORD_RE,
    _TEXT_MIN_LENGTH,
    PageDescriptor,
    SegmentDraft,
    _levenshtein_distance,
)
from apps.pdf_splitting.services.template_registry import (
    SegmentTemplateRule,
    get_default_filename,
    get_template_definition,
)

logger = logging.getLogger("apps.pdf_splitting")


class SegmentDetector:
    """段落检测、评分、上下文推理、补全未识别区间。"""

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

    def fuzzy_contains_keyword(self, haystack: str, keyword: str) -> tuple[bool, float]:
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
        candidates: list[dict[str, Any]] = []
        for rule in template.rules:
            score = 0.0
            matched_strong: list[str] = []
            matched_weak: list[str] = []

            strong_score = 0.0
            for kw in rule.strong_keywords:
                hit, decay = self.fuzzy_contains_keyword(normalized_text, kw)
                if hit:
                    matched_strong.append(kw)
                    strong_score += (0.4 + 0.18) * decay
            score += min(0.75, strong_score)

            for kw in rule.weak_keywords:
                hit, _decay = self.fuzzy_contains_keyword(normalized_text, kw)
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
        for page in pages:
            if not page.top_candidates:
                continue
            top = page.top_candidates[0]
            start_candidates.append(
                {
                    "page_no": page.page_no,
                    "segment_type": top["segment_type"],
                    "score": float(top["score"]),
                    "weak_only": bool(top.get("weak_only", False)),
                }
            )

        inferred = self._infer_continuation_pages(pages, start_candidates, template_key=template_key)
        candidate_page_set = {c["page_no"] for c in start_candidates}
        all_candidates = start_candidates + [c for c in inferred if c["page_no"] not in candidate_page_set]
        all_candidates.sort(key=lambda c: c["page_no"])

        segments: list[SegmentDraft] = []
        for index, start in enumerate(all_candidates):
            if start.get("source") == "context_infer":
                continue

            next_start_page = len(pages) + 1
            for future in all_candidates[index + 1 :]:
                if future.get("source") != "context_infer":
                    next_start_page = future["page_no"]
                    break

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

            if start.get("weak_only"):
                review_flag = PdfSplitReviewFlag.LOW_CONFIDENCE
                source_method = "rule_weak_only"

            prev_real = [c for c in all_candidates[:index] if c.get("source") != "context_infer"]
            if prev_real and prev_real[-1]["page_no"] == start["page_no"] - 1:
                if prev_real[-1]["segment_type"] == start["segment_type"]:
                    review_flag = PdfSplitReviewFlag.LOW_CONFIDENCE
                    source_method = "rule_adjacent_start"
                    confidence = min(confidence, 0.55)

            segments.append(
                SegmentDraft(
                    order=len(segments) + 1,
                    page_start=start["page_no"],
                    page_end=max(start["page_no"], end_page),
                    segment_type=start["segment_type"],
                    filename=f"{get_default_filename(start['segment_type'])}.pdf",
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

    def _infer_continuation_pages(
        self,
        pages: list[PageDescriptor],
        start_candidates: list[dict[str, Any]],
        *,
        template_key: str,
    ) -> list[dict[str, Any]]:
        """
        跨页上下文推理：将无候选但包含 continuation_keywords 的页面归入前一高置信度段落。

        仅当前一候选 score >= 0.5 时触发，且段落页数不超过 30 页。
        """
        template = get_template_definition(template_key)
        candidate_page_set = {c["page_no"] for c in start_candidates}
        inferred: list[dict[str, Any]] = []

        all_known: list[dict[str, Any]] = list(start_candidates)

        for page in pages:
            if page.page_no in candidate_page_set:
                continue

            prev_candidate: dict[str, Any] | None = None
            for c in reversed(all_known):
                if c["page_no"] < page.page_no:
                    prev_candidate = c
                    break

            if prev_candidate is None or float(prev_candidate.get("score", 0.0)) < 0.5:
                continue

            span_start: int = int(prev_candidate.get("span_start", prev_candidate["page_no"]))
            if page.page_no - span_start >= 30:
                continue

            rule = next(
                (r for r in template.rules if r.segment_type == prev_candidate["segment_type"]),
                None,
            )
            if rule is None or not rule.continuation_keywords:
                continue

            has_continuation = any(
                self.contains_keyword(page.normalized_text, kw) for kw in rule.continuation_keywords
            )
            if has_continuation:
                entry: dict[str, Any] = {
                    "page_no": page.page_no,
                    "segment_type": prev_candidate["segment_type"],
                    "score": round(float(prev_candidate["score"]) * 0.9, 3),
                    "source": "context_infer",
                    "span_start": span_start,
                    "weak_only": False,
                }
                inferred.append(entry)
                all_known.append(entry)
                all_known.sort(key=lambda c: c["page_no"])

        return inferred

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

            has_continuation = any(
                self.contains_keyword(page.normalized_text, kw) for kw in rule.continuation_keywords
            )
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
