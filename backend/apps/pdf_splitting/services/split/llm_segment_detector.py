"""LLM 段落检测：逐页取字摘要 → 律所 LLM 输出结构化分段。

背景（2026-10-16 方案二落地）：关键词规则引擎 SegmentDetector 在真实移交
材料上大量 unrecognized（近 30 任务实测 2/3 未识别、平均置信度 0.13）——
「这一页属于哪份材料、上一份在哪页结束」本质是语义分类，正是 LLM 强项。

边界约定：
- 本模块只替换「检测」环节。取字（云端解析 / 本地 OCR）与结果校验
  （页码钳位、去重叠、gap 补片）仍走既有管线，LLM 输出过同一道闸门；
- segment_type 仍是模板枚举的封闭集（不动 DB 模型），超出枚举的材料
  type=other、开放命名落在 filename（API 再经 segment_label 透出）；
- 任何失败（无供给 / 超时 / 输出非法）抛 LLMSegmentationError，
  由 PdfSplitService 降级回规则引擎，不阻断任务。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.core.llm.structured_output import parse_json_content
from apps.core.services.storage_service import sanitize_upload_filename
from apps.pdf_splitting.models import PdfSplitReviewFlag, PdfSplitSegmentType
from apps.pdf_splitting.services.template_registry import get_template_definition

from .segment_detector import SegmentDetector
from .split_models import PageDescriptor, SegmentDraft

logger = logging.getLogger("apps.pdf_splitting")

# 每页进入 prompt 的摘要窗口：开头 + 结尾双窗口。材料边界的关键证据在
# 「上一页的末几句 + 下一页的头几句」（落款 / 日期 / 签名 vs 新标题），
# 只给开头会漏掉「此致」「具状人」这类结束信号
_PAGE_HEAD_CHARS = 150
_PAGE_TAIL_CHARS = 110
_PAGE_DIGEST_OMIT_MARK = "……（中略）……"
# 输出上限：300 页封顶的 PDF 按每段 ~30 token 估算，100 段以内绰绰有余
_MAX_OUTPUT_TOKENS = 8000
_TEMPERATURE = 0.1

SYSTEM_PROMPT = """\
你是诉讼立案材料整理助手。用户给你一份扫描 PDF 的逐页文字摘要（每页只截取开头与结尾两段，中间内容省略），\
任务是把整份 PDF 划分成若干「份材料」：判断每页属于哪份材料、材料类型并命名。

判断规则：
1. 同一份材料的连续页归为一段（page_start..page_end）；内容主题切换（如从起诉状到证据清单）即新开一段。
2. 材料首页通常有标题（如「民事起诉状」「证据清单」「送达地址确认书」）；无标题的续页跟随前一份材料。
3. 判断衔接重点看边界两侧：上一页结尾出现落款、日期、签名、「此致」「具状人」「合议庭」等收尾信号，\
而下一页开头出现新的文件标题——两页之间大概率是两份材料；反之结尾是未完的句子或表格行、下一页开头无标题，则多为同一份的续页。
4. 银行流水、发票、送货单等多页清单，中间没有明显换材料信号时保持同一段。
5. 「未取到文字」的页多为身份证复印件、盖章页或纯图片：按前后文判断归属，拿不准就单独成段并给低置信度。
6. type 只能取给定的键名之一；都不贴切时用 "other"，并在 label 写准确的材料名（如 借条、转账凭证、聊天记录、判决书、调解书、送达回证、证据材料）。
7. label 是给人看的材料名，优先取材料自身的标题，不要杜撰；confidence 为 0 到 1 的把握值。

只输出 JSON，不要任何解释或代码块标记，格式：
{"segments": [{"page_start": 1, "page_end": 3, "type": "complaint", "label": "起诉状", "confidence": 0.95}]}"""

_CALLER = "pdf_splitting"


class LLMSegmentationError(RuntimeError):
    """LLM 分段失败（供给不可用 / 输出非法），调用方降级规则引擎。"""


class LLMSegmentDetector:
    """把逐页 PageDescriptor 交给律所 LLM 做语义分段。"""

    def __init__(self, llm_service: Any | None = None) -> None:
        # 不在构造期解析 LLM 服务：ServiceLocator 触发 DB 访问，
        # 无 django_db 标记的单测会被阻断（照 vlm_ocr_service 的懒加载模式）
        self._llm_service = llm_service

    def detect(self, pages: list[PageDescriptor], *, template_key: str) -> list[SegmentDraft]:
        if not pages:
            raise LLMSegmentationError("没有可分析的页面")

        response = self._get_llm_service().chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(pages, template_key=template_key)},
            ],
            temperature=_TEMPERATURE,
            max_tokens=_MAX_OUTPUT_TOKENS,
            caller=_CALLER,
        )
        raw = str(getattr(response, "content", "") or "")
        drafts = parse_llm_segments(raw, total_pages=len(pages), template_key=template_key)
        logger.info(
            "pdf_split_llm_segments_done",
            extra={
                "action": "llm_segment_detect",
                "pages": len(pages),
                "segments": len(drafts),
                "recognized": len([d for d in drafts if d.segment_type != PdfSplitSegmentType.UNRECOGNIZED]),
            },
        )
        return drafts

    def _get_llm_service(self) -> Any:
        if self._llm_service is None:
            from apps.core.services.wiring import get_llm_service

            self._llm_service = get_llm_service()
        return self._llm_service


# ↓↓ 模块级纯函数（四层架构静态方法棘轮；不触 DB / 网络，单测直打）


def build_page_digests(pages: list[PageDescriptor]) -> list[str]:
    """逐页摘要：标题行优先 + 正文开头/结尾双窗口，OCR 失败页显式标注。"""
    digests: list[str] = []
    for page in pages:
        if page.ocr_failed or not page.normalized_text:
            digests.append(f"【第{page.page_no}页】（未取到文字）")
            continue
        title = (page.layout_title or "").strip()
        prefix = f"【第{page.page_no}页｜标题：{title}】" if title else f"【第{page.page_no}页】"
        digests.append(f"{prefix}{_digest_body(page.normalized_text)}")
    return digests


def _digest_body(normalized_text: str) -> str:
    full = normalized_text or ""
    if len(full) <= _PAGE_HEAD_CHARS + _PAGE_TAIL_CHARS + 60:
        return full
    return f"{full[:_PAGE_HEAD_CHARS]}{_PAGE_DIGEST_OMIT_MARK}{full[-_PAGE_TAIL_CHARS:]}"


def build_user_prompt(pages: list[PageDescriptor], *, template_key: str) -> str:
    template = get_template_definition(template_key)
    type_lines = [f"- {rule.segment_type}：{rule.label}" for rule in template.rules]
    type_lines.append("- other：其他材料（在 label 写准确名称）")
    digests = build_page_digests(pages)
    return (
        f"这份 PDF 共 {len(pages)} 页。可用的 type 键名：\n"
        + "\n".join(type_lines)
        + "\n\n逐页摘要：\n"
        + "\n".join(digests)
        + "\n\n请输出分段 JSON。"
    )


def parse_llm_segments(raw_text: str, *, total_pages: int, template_key: str) -> list[SegmentDraft]:
    """解析并校验 LLM 输出：页码钳位、去重叠、gap 补片，产出与规则引擎同构的 SegmentDraft。

    输出非法或没有任何可用段时抛 ValueError——调用方据此降级规则引擎，
    而不是拿着残缺分段去覆盖页面。
    """
    try:
        payload = parse_json_content(raw_text)
    except ValueError as exc:
        raise ValueError(f"LLM 输出不是合法 JSON: {str(exc)[:120]}") from exc

    items = payload.get("segments") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not items:
        raise ValueError("LLM 输出缺少 segments 数组")

    template = get_template_definition(template_key)
    type_map = {rule.segment_type: rule for rule in template.rules}
    drafts: list[SegmentDraft] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        draft = _build_draft(raw, total_pages=total_pages, type_map=type_map)
        if draft is not None:
            drafts.append(draft)
    if not drafts:
        raise ValueError("LLM 输出没有任何可用分段")

    return _normalize_coverage(drafts, total_pages=total_pages)


def _build_draft(
    raw: dict[str, Any],
    *,
    total_pages: int,
    type_map: dict[str, Any],
) -> SegmentDraft | None:
    raw_start: Any = raw.get("page_start")
    raw_end: Any = raw.get("page_end")
    try:
        page_start = max(1, int(raw_start))
        page_end = min(total_pages, int(raw_end))
    except (TypeError, ValueError):
        return None
    if page_start > page_end:
        return None

    segment_type = str(raw.get("type") or "").strip()
    raw_label = str(raw.get("label") or "").strip()
    confidence = _clamp_confidence(raw.get("confidence"))

    known_rule = type_map.get(segment_type)
    if known_rule is not None:
        final_label = raw_label or known_rule.label
    else:
        # 超出模板枚举（other / 未知名）：类型记 unrecognized，命名落在 filename，
        # API 经 segment_label 透出给前端当类型胶囊展示
        segment_type = PdfSplitSegmentType.UNRECOGNIZED
        final_label = raw_label
    if not final_label:
        final_label = f"材料_{page_start}-{page_end}"
    final_label = sanitize_upload_filename(final_label)
    review_flag = (
        PdfSplitReviewFlag.LOW_CONFIDENCE
        if segment_type == PdfSplitSegmentType.UNRECOGNIZED or confidence < 0.6
        else PdfSplitReviewFlag.NORMAL
    )
    return SegmentDraft(
        order=0,
        page_start=page_start,
        page_end=page_end,
        segment_type=segment_type,
        filename=f"{final_label}.pdf",
        confidence=confidence,
        source_method="llm",
        review_flag=review_flag,
    )


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = round(float(value), 3)
    except (TypeError, ValueError):
        return 0.5
    return min(max(confidence, 0.0), 1.0)


def _normalize_coverage(drafts: list[SegmentDraft], *, total_pages: int) -> list[SegmentDraft]:
    """按页序去重叠（后段起点钳到前段末页 +1），再复用规则引擎的 gap 补片保证整覆盖。"""
    ordered = sorted(drafts, key=lambda item: (item.page_start, item.page_end))
    resolved: list[SegmentDraft] = []
    cursor = 0
    for item in ordered:
        start = max(item.page_start, cursor + 1)
        if start > item.page_end:
            continue
        resolved.append(
            SegmentDraft(
                order=0,
                page_start=start,
                page_end=item.page_end,
                segment_type=item.segment_type,
                filename=item.filename,
                confidence=item.confidence,
                source_method=item.source_method,
                review_flag=item.review_flag,
            )
        )
        cursor = item.page_end
    return SegmentDetector().fill_unrecognized_gaps(segments=resolved, total_pages=total_pages)
