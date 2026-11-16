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
import re
import threading
from typing import Any

from apps.core.llm.structured_output import parse_json_content
from apps.core.services.storage_service import sanitize_upload_filename
from apps.pdf_splitting.models import PdfSplitReviewFlag, PdfSplitSegmentType
from apps.pdf_splitting.services.template_registry import get_template_definition

from .segment_detector import SegmentDetector
from .split_models import PageDescriptor, SegmentDraft

logger = logging.getLogger("apps.pdf_splitting")

# 每页进入 prompt 的摘要窗口：按**行**取首尾，保留换行。
#
# 为什么按行不按字：system prompt 规则 3 要看「落款 / 此致 / 具状人」这类
# **行级**收尾信号，而 normalized_text 把换行全剥光，落款与正文粘成一个字块，
# 判据先天不足。改用 page.text 的非空行。
#
# 行数依据（164 页真实卷宗只读实测）：非空行数 p50=7、p90=21、max=61。
# 首 10 + 尾 6 行让过半页面整页进 prompt，p90 页保留 76% 的行。
# 尾窗取 6 而不是 3：云端解析页的最后 3 行常是印章核验语（「已核对与原件相符 /
# 扫描件与留档资料相符 / 经办人：…」，文本层/兜底页已由 clean_unstructured_page_text
# 清掉，云端页没有），只给 3 行等于把收尾信号全喂成噪声。
# 实测效果：尾窗里的收尾信号行 31 条全部保住、0 条丢失；摘要总字符 39331 → 57300
# （1.46x），单页最大 316 → 934，41 页窗口合计约 8.7K 字符。
_PAGE_HEAD_LINES = 10
_PAGE_TAIL_LINES = 6
# 单行字数上限：引擎会把整张表拍平成一行（实测某页单行 18516 字），
# 不设上限一行就能吃掉整批预算。120 字够看清标题 / 落款 / 表头。
_PAGE_LINE_CHARS = 120
_LINE_TRUNC_MARK = "…"
# 摘要里的 HTML 标签不是正文证据（实测 10/45 段有 <img>/<div> 泄漏），
# 剥掉后为空的行直接不进窗口，免得占掉宝贵的尾窗行数。
_HTML_TAG_RE = re.compile(r"<[^>]{1,200}>")
# 输出上限：1000 页封顶的 PDF 按每段 ~30 token 估算，100 段以内绰绰有余
_MAX_OUTPUT_TOKENS = 8000
_TEMPERATURE = 0.1
# 单次 HTTP 请求时限（秒）：供给网关半开 / 挂流时按层兜住
_REQUEST_TIMEOUT_SECONDS = 420
# 整条调用的硬时限墙（秒）：key 池轮换 × OpenAI SDK 内建重试 × 连接超时会
# 层层相乘（本机实测律所网关离线时能挂 25 分钟以上），不设墙会把 Q 任务拖死。
# 健康网关下 92 页分段实测约 3-5 分钟，8 分钟墙留足余量（前端轮询窗口 14 分钟）
_WALL_TIMEOUT_SECONDS = 480

# ── 边界二审（P2-9a）────────────────────────────────────────────
# 只读边界两侧整页全文，输出一个动作，所以预算比主分段小一个量级。
# 单侧全文上限：实测页字符数 p50=590、p90=3373、max=18516（被拍平的表格页）。
# 4000 字覆盖 p90 以上，再长就截尾——二审看的是衔接处，不是整页每一行。
_BOUNDARY_REVIEW_PAGE_CHARS = 4000
_BOUNDARY_REVIEW_MAX_TOKENS = 600
_BOUNDARY_REVIEW_REQUEST_SECONDS = 60
_BOUNDARY_REVIEW_WALL_SECONDS = 90
_BOUNDARY_REVIEW_ACTIONS = ("keep", "merge", "move_left", "move_right")

BOUNDARY_REVIEW_SYSTEM_PROMPT = """\
你是诉讼卷宗分段复核员。用户给你一条**已存在的分段边界**两侧的两页全文（左页是前一段的末页，\
右页是后一段的首页），只判断这一条边界对不对，不要重新分段整份 PDF。

可选动作只有四个：
- keep：边界正确，两页分属两份材料。
- merge：右页开始的那一段整体是左页所属材料的续页（同一份材料被从中间切开），应并成一段。
- move_left：左页其实属于右页那一份（边界应左移一页）。
- move_right：右页其实属于左页那一份（边界应右移一页）。

判据（按可靠性排序）：
1. 左页结尾是**未完的句子**（半句话、被切断的条款），右页开头接着这半句 → 同一份材料，倾向 merge。
2. 左页结尾有落款/签名/日期/「此致」「具状人」等收尾信号，右页开头是**新的文件标题** → keep。
3. 右页开头重复了左页所属材料的标题与当事人抬头（同一份材料从头再印一遍）→ 那是**重复件**，keep，不要 merge。
4. 条款/编号序号连续推进且右页无新标题 → merge；序号回退或换了编号体系 → keep。
5. 「已核对与原件相符」「扫描件与留档资料相符」「经办人：…」是印章核验语，不是收尾信号，忽略后再判断。

拿不准就 keep——错误合并会把两份材料粘在一起，比多切一段更难发现。
只输出 JSON，不要解释或代码块标记：{"action": "keep", "reason": "不超过 40 字的依据"}"""

# ⚠️ prompt 里**不能写死具体场景**（「立案材料」）。
# 早先这里写的是「你是诉讼立案材料整理助手」，后果：把二审答辩包交给它拆时，
# 模型看到「立案材料」这个身份预设，认为判决书/上诉状/答辩状不属于本场景，
# 一律回 other → 全部落 unrecognized（实测 5 段只认出 1 段）。
# 而模板注册表（template_registry）才是「本场景有哪些材料类型」的唯一来源，
# 已经把可用 type 键名逐条列进 user prompt 了。
# 所以 system prompt 只描述**怎么分段**，不描述**这份 PDF 是什么场景**。
SYSTEM_PROMPT = """\
你是诉讼卷宗整理助手。用户给你一份扫描 PDF 的逐页文字摘要（每页保留原始行结构，只截取开头若干行与结尾若干行，\
中间省略的行会标注「中略 N 行」），任务是把整份 PDF 划分成若干「份材料」：判断每页属于哪份材料、材料类型并命名。

当前场景可用的材料类型以 user 消息里列出的 type 键名为准 —— 那是本场景的完整清单，\
**不要用你自己对「这类案子一般有哪些材料」的预设去否定它**：清单里列了判决书，\
就说明本案确实可能有判决书；列了答辩状，就说明要拆的是答辩材料。

user 消息可能标出开头若干页为「上下文页」：它们只供你判断边界（看上一份材料有没有收尾），\
**不要为上下文页产出分段**，只为用户指明负责的那些页产出分段。

判断规则：
1. 同一份材料的连续页归为一段（page_start..page_end）；内容主题切换（如从起诉状到证据清单）即新开一段。
2. 材料首页通常有标题（如「民事起诉状」「证据清单」「送达地址确认书」）；无标题的续页跟随前一份材料。
3. 判断衔接重点看边界两侧的**行**：上一页结尾出现落款、日期、签名、「此致」「具状人」「合议庭」等收尾信号，\
而下一页开头出现新的文件标题——两页之间大概率是两份材料；反之结尾是未完的句子或表格行、下一页开头无标题，则多为同一份的续页。\
注意「已核对与原件相符」「扫描件与留档资料相符」「经办人：…」这类印章核验语不是材料收尾信号，忽略它们再判断。
4. 银行流水、发票、送货单等多页清单，中间没有明显换材料信号时保持同一段。
5. 「未取到文字」的页多为身份证复印件、盖章页或纯图片：按前后文判断归属，拿不准就单独成段并给低置信度。
6. type 优先取 user 消息里给定的键名，语义贴切就用它，不要因为「这不像本场景的材料」就退回 "other"。\
但**贴切才用**：键名与材料实际性质不符时（例如把「转账回单」塞进「放款凭证」、把「借条」塞进「借款合同」），\
宁可回 "other" 并在 label 写准确材料名，也不要硬塞一个语义不对的键名——错标类型比开放命名更难被发现。
7. label 是给人看的材料名，优先取材料自身的标题，不要杜撰；confidence 为 0 到 1 的把握值。

只输出 JSON，不要任何解释或代码块标记，格式：
{"segments": [{"page_start": 1, "page_end": 3, "type": "complaint", "label": "起诉状", "confidence": 0.95}]}"""

_CALLER = "pdf_splitting"


class LLMSegmentationError(RuntimeError):
    """LLM 分段失败（供给不可用 / 输出非法），调用方降级规则引擎。"""


class LLMSegmentDetector:
    """把逐页 PageDescriptor 交给律所 LLM 做语义分段。"""

    def __init__(self, llm_service: Any | None = None, wall_timeout_seconds: float = _WALL_TIMEOUT_SECONDS) -> None:
        # 不在构造期解析 LLM 服务：ServiceLocator 触发 DB 访问，
        # 无 django_db 标记的单测会被阻断（照 vlm_ocr_service 的懒加载模式）
        self._llm_service = llm_service
        self._wall_timeout_seconds = wall_timeout_seconds
        # 懒加载用的锁：分段已改成多批并行，多个线程会同时读 _llm_service
        self._service_lock = threading.Lock()

    def detect(
        self,
        pages: list[PageDescriptor],
        *,
        template_key: str,
        context_pages: int = 0,
    ) -> list[SegmentDraft]:
        """语义分段。`context_pages` 是切片开头「仅供上下文、不产出分段」的页数。

        分批路径（`segment_batch.detect_in_batches`）会传它；整本一次调用时
        没有上下文页，保持 0。
        """
        if not pages:
            raise LLMSegmentationError("没有可分析的页面")

        response = self._chat_with_wall(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(pages, template_key=template_key, context_pages=context_pages),
                },
            ],
            temperature=_TEMPERATURE,
            max_tokens=_MAX_OUTPUT_TOKENS,
            timeout_seconds=_REQUEST_TIMEOUT_SECONDS,
            caller=_CALLER,
        )
        raw = str(getattr(response, "content", "") or "")
        drafts = parse_llm_segments(raw, total_pages=len(pages), template_key=template_key)
        logger.info(
            "pdf_split_llm_segments_done",
            extra={
                "action": "llm_segment_detect",
                "pages": len(pages),
                "context_pages": context_pages,
                "segments": len(drafts),
                "recognized": len([d for d in drafts if d.segment_type != PdfSplitSegmentType.UNRECOGNIZED]),
            },
        )
        return drafts

    def review_boundary(
        self,
        *,
        left_page: int,
        right_page: int,
        left_text: str,
        right_text: str,
    ) -> str | None:
        """边界二审：给边界两侧**整页全文**，问这条边界该不该动。

        返回 `keep` / `merge` / `move_left` / `move_right`；**任何失败或非法
        输出一律返回 None**（= 未复核，调用方保持原边界并标疑点）。二审是
        锦上添花，绝不能因为它挂掉就把本来正确的边界乱切。

        为什么单独设一套更短的时限：分段主调用墙钟 480s，二审若沿用，
        4 次串行就能吃掉 32 分钟，远超 segment 阶段预算。二审只读两页、
        只输出一个动作，90s 墙足够，且并行跑。
        """
        try:
            response = self._chat_with_wall(
                messages=[
                    {"role": "system", "content": BOUNDARY_REVIEW_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_boundary_review_prompt(
                            left_page=left_page,
                            right_page=right_page,
                            left_text=left_text,
                            right_text=right_text,
                        ),
                    },
                ],
                temperature=_TEMPERATURE,
                max_tokens=_BOUNDARY_REVIEW_MAX_TOKENS,
                timeout_seconds=_BOUNDARY_REVIEW_REQUEST_SECONDS,
                caller=_CALLER,
                wall_timeout_seconds=_BOUNDARY_REVIEW_WALL_SECONDS,
            )
        except Exception as exc:
            logger.warning(
                "pdf_split_boundary_review_failed",
                extra={
                    "left_page": left_page,
                    "right_page": right_page,
                    "error": f"{type(exc).__name__}: {str(exc)[:120]}",
                },
            )
            return None

        raw = str(getattr(response, "content", "") or "")
        action = parse_boundary_verdict(raw)
        logger.info(
            "pdf_split_boundary_review_done",
            extra={"left_page": left_page, "right_page": right_page, "action": action or "invalid"},
        )
        return action

    def _get_llm_service(self) -> Any:
        """懒加载 LLM 服务（线程安全）。

        为何要加锁：分段已改为**多批并行**（`segment_batch` 用
        ThreadPoolExecutor），多个线程可能同时首次进入这里。不加锁的话
        会各自调一次 `get_llm_service()`——轻则重复建连接，重则拿到两个
        不同实例导致配置不一致。
        """
        if self._llm_service is not None:
            return self._llm_service
        with self._service_lock:
            if self._llm_service is None:
                from apps.core.services.wiring import get_llm_service

                self._llm_service = get_llm_service()
            return self._llm_service

    def _chat_with_wall(self, *, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        """带硬时限墙的 LLM 调用：到点抛 LLMSegmentationError，由上层降级规则引擎。

        守护线程执行（超时后线程残留但进程退出不受阻），result 字典回传响应或异常。
        `wall_timeout_seconds` 是本方法的参数、**不转发给 chat()**：二审要用
        比主分段短得多的墙，其余调用沿用构造期的值。
        """
        wall = float(kwargs.pop("wall_timeout_seconds", self._wall_timeout_seconds))
        outcome: dict[str, Any] = {}

        def _run() -> None:
            try:
                outcome["response"] = self._get_llm_service().chat(messages=messages, **kwargs)
            except Exception as exc:  # 原样回传调用方；只捕 Exception，KI/SystemExit 让线程自然结束走超时路径
                outcome["error"] = exc

        worker = threading.Thread(target=_run, daemon=True, name="pdf-split-llm-wall")
        worker.start()
        worker.join(wall)
        if worker.is_alive():
            raise LLMSegmentationError(f"LLM 分段超过 {wall}s 未返回，已按超时处理")
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("response")


# ↓↓ 模块级纯函数（四层架构静态方法棘轮；不触 DB / 网络，单测直打）


def build_page_digests(pages: list[PageDescriptor], *, context_pages: int = 0) -> list[str]:
    """逐页摘要：标题行优先 + 正文**首尾若干行**（保留换行），OCR 失败页显式标注。

    `context_pages` 是开头「仅供上下文」的页数，逐页标出来让模型知道
    不要为它们产出分段（分批路径的左上下文）。
    """
    digests: list[str] = []
    for index, page in enumerate(pages):
        prefix = _digest_prefix(page, is_context=index < context_pages)
        if page.ocr_failed or not page.normalized_text:
            digests.append(f"{prefix}（未取到文字）")
            continue
        digests.append(f"{prefix}\n{_digest_body(page.text)}")
    return digests


def _digest_prefix(page: PageDescriptor, *, is_context: bool) -> str:
    scope = "·上下文" if is_context else ""
    title = (page.layout_title or "").strip()
    if title:
        return f"【第{page.page_no}页{scope}｜标题：{title}】"
    return f"【第{page.page_no}页{scope}】"


def _digest_lines(text: str) -> list[str]:
    """取非空行并剥掉 HTML 标签；剥完为空的行（纯图片/排版标记）不进窗口。"""
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = _HTML_TAG_RE.sub("", raw).strip()
        if line:
            lines.append(line)
    return lines


def _clip_line(line: str, *, keep_tail: bool) -> str:
    if len(line) <= _PAGE_LINE_CHARS:
        return line
    if keep_tail:
        return f"{_LINE_TRUNC_MARK}{line[-_PAGE_LINE_CHARS:]}"
    return f"{line[:_PAGE_LINE_CHARS]}{_LINE_TRUNC_MARK}"


def _digest_body(text: str) -> str:
    """首 N 行 + 尾 M 行，中间标注省略了多少行。

    尾窗里的长行保**行尾**、首窗里的长行保**行头**：边界证据分别是
    「这一页怎么结束的」（落款/未完句）与「这一页怎么开始的」（标题）。
    被拍平成一行的表格页两端都能看到，而不是只看到开头。
    """
    lines = _digest_lines(text)
    if not lines:
        return ""
    keep = _PAGE_HEAD_LINES + _PAGE_TAIL_LINES
    if len(lines) <= keep:
        first_tail_index = max(0, len(lines) - _PAGE_TAIL_LINES)
        return "\n".join(_clip_line(line, keep_tail=i >= first_tail_index) for i, line in enumerate(lines))
    head = "\n".join(_clip_line(line, keep_tail=False) for line in lines[:_PAGE_HEAD_LINES])
    tail = "\n".join(_clip_line(line, keep_tail=True) for line in lines[-_PAGE_TAIL_LINES:])
    omitted = len(lines) - keep
    return f"{head}\n……（中略 {omitted} 行）……\n{tail}"


def build_user_prompt(pages: list[PageDescriptor], *, template_key: str, context_pages: int = 0) -> str:
    template = get_template_definition(template_key)
    type_lines = [f"- {rule.segment_type}：{rule.label}" for rule in template.rules]
    type_lines.append("- other：其他材料（在 label 写准确名称）")
    hints = template.open_label_hints
    if hints:
        type_lines.append(f"  常见需要走 other 的材料：{'、'.join(hints)}")
    digests = build_page_digests(pages, context_pages=context_pages)
    return (
        _prompt_scope_line(len(pages), context_pages=context_pages)
        + "可用的 type 键名：\n"
        + "\n".join(type_lines)
        + "\n\n逐页摘要：\n"
        + "\n".join(digests)
        + "\n\n请输出分段 JSON。"
    )


def _prompt_scope_line(total: int, *, context_pages: int) -> str:
    if context_pages <= 0:
        return f"这份 PDF 共 {total} 页。"
    return (
        f"本次送来 {total} 页，其中第 1 到第 {context_pages} 页标为「上下文页」，"
        f"只供你判断边界，**不要为它们产出分段**；"
        f"你负责的是第 {context_pages + 1} 页到第 {total} 页，分段只覆盖这个区间。\n"
    )


def build_boundary_review_prompt(*, left_page: int, right_page: int, left_text: str, right_text: str) -> str:
    """二审 user prompt：边界两侧整页全文（超长截尾，保留行结构）。"""
    return (
        f"当前边界：前一段到第 {left_page} 页结束，后一段从第 {right_page} 页开始。\n\n"
        f"===== 左页（第 {left_page} 页，前一段末页）全文 =====\n"
        f"{_review_page_text(left_text)}\n\n"
        f"===== 右页（第 {right_page} 页，后一段首页）全文 =====\n"
        f"{_review_page_text(right_text)}\n\n"
        "请只输出这条边界的动作 JSON。"
    )


def _review_page_text(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return "（未取到文字）"
    if len(body) <= _BOUNDARY_REVIEW_PAGE_CHARS:
        return body
    return f"{body[:_BOUNDARY_REVIEW_PAGE_CHARS]}\n……（本页过长，后续省略）……"


def parse_boundary_verdict(raw_text: str) -> str | None:
    """解析二审输出；非法 JSON / 未知动作一律 None（调用方保持原边界）。"""
    try:
        payload = parse_json_content(raw_text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action") or "").strip().lower()
    return action if action in _BOUNDARY_REVIEW_ACTIONS else None


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
