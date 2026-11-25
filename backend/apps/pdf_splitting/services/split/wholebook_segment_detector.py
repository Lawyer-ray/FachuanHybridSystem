"""整本一次调用的语义分段：让模型**同时看见全书**再切分，而不是逐批判。

## 它和分批路径差在哪

`llm_segment_detector` 原来一次只喂一批（默认十来页）的**首尾摘要**
（`build_page_digests`：保留前后几行、中间标「中略 N 行」）。分批是为了绕开
Django-Q 的 worker 超时（164 页整本一次曾跑到 499s 被杀），代价是模型永远看不到全书：

- 一份起诉状跨 p22–p31，中间还有旋转页/表格页时，分批只看得到自己那一段；
- 「主体资格材料」这类**按类型归并**的倾向会被放大——模型看到营业执照、身份证、
  法代证明书分别属于不同的批，就更容易把它们并成一段（实测同一份正文上，
  分批路径稳定给出 7 段、整本路径稳定给出 9 段，差在 p3/p4 被并进主体资格）。

## 实测依据（同一份 37 页扫描卷宗）

| 路径 | 段数 | 与独立核验的 9 段边界比 |
|---|---|---|
| 分批 + 我方 LLM | 7 | 缺 p3、p4（并进主体资格） |
| 只把合并正文丢给一次 chat（DeepSeek） | **9** | 全对 |

差别不在模型，在**一次能不能看全**。

## 为什么这里不用「摘要」而用「全文（截断）」

摘要丢的正是判边界要的信息：一页的中间段落里往往藏着「综上」「此致」「落款」。
所以整本路径喂**逐页全文**，只在两个地方截断（都有理由）：

- 单页超 ``_PAGE_CHAR_LIMIT`` 截尾：银行流水一页能到 8000 字，会把上下文吃光，
  而流水页内部没有边界信号（本来就该是同一段）。
- 总量超 ``_TOTAL_CHAR_BUDGET`` 时，从**中间页开始退化成摘要**（首尾页保留全文）：
  边界最可能出现在开头与结尾；中间退化成摘要仍比整本都不给强。

超预算这件事必须写进日志与 summary——否则「这次怎么切得不如上次准」无从解释。
"""

from __future__ import annotations

import logging
from typing import Any

from .llm_segment_detector import (
    SYSTEM_PROMPT,
    LLMSegmentationError,
    LLMSegmentDetector,
    _digest_prefix,
    build_page_digests,
    parse_llm_segments,
)
from .split_models import PageDescriptor, SegmentDraft

logger = logging.getLogger("apps.pdf_splitting")

#: 单页正文上限（字符）。银行流水一页可达 8000 字，而流水页内部没有边界信号。
_PAGE_CHAR_LIMIT = 2000

#: 整本正文预算（字符）。37 页扫描件实测约 27k 字符；164 页约 110k。
#: 取 120k 意味着 ~37 页的卷宗全文喂入、164 页会进入「中间退化成摘要」档。
_TOTAL_CHAR_BUDGET = 120_000

#: 整本一次的输出去上限：分段 JSON 每段几十字，164 页最多几十段。
_MAX_OUTPUT_TOKENS = 16_000

#: 整本一次的墙钟：单次 LLM 调用超时与整体看门狗。
_REQUEST_TIMEOUT_SECONDS = 600
_WALL_TIMEOUT_SECONDS = 700


def build_wholebook_prompt(pages: list[PageDescriptor], *, template_key: str) -> tuple[str, dict[str, Any]]:
    """整本 prompt + 预算统计（``{"truncated_pages": [...], "digest_pages": [...]}``）。"""
    from apps.pdf_splitting.services.template_registry import get_template_definition

    template = get_template_definition(template_key)
    type_lines = [f"- {rule.segment_type}：{rule.label}" for rule in template.rules]
    type_lines.append("- other：其他材料（在 label 写准确名称）")
    hints = template.open_label_hints
    if hints:
        type_lines.append(f"  常见需要走 other 的材料：{'、'.join(hints)}")

    digests = build_page_digests(pages)
    total_full = sum(len(page.text or "") for page in pages)
    use_full = total_full <= _TOTAL_CHAR_BUDGET

    blocks: list[str] = []
    truncated: list[int] = []
    degraded: list[int] = []
    for index, page in enumerate(pages):
        if page.ocr_failed or not (page.text or "").strip():
            blocks.append(f"{_digest_prefix(page, is_context=False)}（未取到文字）")
            continue
        if not use_full and 0 < index < len(pages) - 1:
            # 超预算时中间页退化成摘要；首尾页仍给全文（边界最可能出现在两头）
            degraded.append(page.page_no)
            blocks.append(digests[index])
            continue
        body = (page.text or "").strip()
        if len(body) > _PAGE_CHAR_LIMIT:
            truncated.append(page.page_no)
            body = body[:_PAGE_CHAR_LIMIT] + f"\n（本页正文过长，已截断，共 {len(page.text or '')} 字）"
        blocks.append(f"{_digest_prefix(page, is_context=False)}\n{body}")

    budget_note = ""
    if not use_full:
        budget_note = (
            f"\n注意：本次正文超过 {_TOTAL_CHAR_BUDGET} 字预算，"
            f"中间 {len(degraded)} 页只给了首尾摘要（已在本页标注），首尾页给的是全文。\n"
        )
    prompt = (
        f"这份 PDF 共 {len(pages)} 页，下面是**逐页正文**（不是摘要）。{budget_note}\n"
        "可用的 type 键名：\n"
        + "\n".join(type_lines)
        + "\n\n逐页正文：\n"
        + "\n\n".join(blocks)
        + "\n\n请输出分段 JSON。"
    )
    return prompt, {"truncated_pages": truncated, "digest_pages": degraded, "full_text": use_full}


class WholeBookSegmentDetector(LLMSegmentDetector):
    """整本一次调用（见模块头）。接口与 `LLMSegmentDetector.detect` 完全一致。"""

    def __init__(self, llm_service: Any | None = None, wall_timeout_seconds: float = _WALL_TIMEOUT_SECONDS) -> None:
        super().__init__(llm_service=llm_service, wall_timeout_seconds=wall_timeout_seconds)
        self.last_budget: dict[str, Any] = {}

    def detect(
        self,
        pages: list[PageDescriptor],
        *,
        template_key: str,
        context_pages: int = 0,
    ) -> list[SegmentDraft]:
        """整本一次分段。

        ``context_pages`` 只为兼容既有接口而保留：整本路径没有「上下文页」这个概念
        （所有页都要产出分段）。传非 0 会被忽略并告警，而不是静默地少切几页。
        """
        if not pages:
            raise LLMSegmentationError("没有可分析的页面")
        if context_pages:
            logger.warning("wholebook 忽略 context_pages=%s（整本路径没有上下文页）", context_pages)

        prompt, budget = build_wholebook_prompt(pages, template_key=template_key)
        self.last_budget = budget
        logger.info(
            "pdf_split_wholebook_prompt",
            extra={
                "pages": len(pages),
                "prompt_chars": len(prompt),
                "truncated_pages": len(budget["truncated_pages"]),
                "digest_pages": len(budget["digest_pages"]),
            },
        )
        response = self._chat_with_wall(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.replace("逐页文字摘要", "逐页正文")},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=_MAX_OUTPUT_TOKENS,
            timeout_seconds=_REQUEST_TIMEOUT_SECONDS,
            caller="pdf_splitting_wholebook",
        )
        raw = str(getattr(response, "content", "") or "")
        drafts = parse_llm_segments(raw, total_pages=len(pages), template_key=template_key)
        logger.info(
            "pdf_split_wholebook_segments_done",
            extra={"pages": len(pages), "segments": len(drafts)},
        )
        return drafts
