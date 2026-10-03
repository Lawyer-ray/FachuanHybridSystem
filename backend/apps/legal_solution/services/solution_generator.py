from __future__ import annotations

import logging
import re
import time
from typing import Any

import bleach
from bleach.css_sanitizer import CSSSanitizer

from apps.core.interfaces import ServiceLocator
from apps.legal_solution.models import SectionStatus, SectionType, SolutionSection, SolutionTask
from apps.legal_solution.models.section import SECTION_ORDER, SECTION_TITLES
from apps.legal_solution.services.prompts import build_section_prompt

logger = logging.getLogger(__name__)

_MAX_TOKENS = 2400
_TIMEOUT = 120
_RETRY = 2

# ── 报告 HTML 消毒白名单 ──────────────────────────────────────────────────────
# 覆盖 markdown（tables/fenced_code）输出与 report.html 实际使用的全部合法标签：
# 标题 h1-h6、段落/换行/分隔线、加粗斜体/删除线/上下标、引用、行内代码与代码块、
# 有序/无序列表、链接、图片、表格。
ALLOWED_TAGS: tuple[str, ...] = (
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
)
# 属性白名单：a 的 href/title、img 的 src/alt（协议仅 http/https/mailto）；
# markdown tables 扩展的对齐语法（|:--|）在 th/td 产出 style="text-align: ..."，
# 经 CSSSanitizer 仅放行 text-align 一个 CSS 属性，其余 style 声明一律剥离。
ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    "a": ["href", "title"],
    "img": ["src", "alt"],
    "th": ["style"],
    "td": ["style"],
}
ALLOWED_PROTOCOLS: tuple[str, ...] = ("http", "https", "mailto")
_ALLOWED_CSS = CSSSanitizer(allowed_css_properties=["text-align"])


def sanitize_report_html(html: str) -> str:
    """报告 HTML 白名单消毒：剥离脚本/事件属性/危险协议/注释（strip 模式）。

    LLM 输出转 HTML 后、落库前统一调用；同 app 其他渲染链路复用同一函数。
    """
    return str(
        bleach.clean(
            html,
            tags=list(ALLOWED_TAGS),
            attributes=ALLOWED_ATTRIBUTES,
            protocols=list(ALLOWED_PROTOCOLS),
            css_sanitizer=_ALLOWED_CSS,
            strip=True,
            strip_comments=True,
        )
    )


def _fallback_md_to_html(text: str) -> str:
    """markdown 库不可用时的手动转换（先整体转义，输出天然无原始 HTML）。"""
    import html as _html

    text = _html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    lines = text.split("\n")
    out: list[str] = []
    in_ul = in_ol = False
    for line in lines:
        ol_m = re.match(r"^\d+[.、]\s+(.*)", line)
        ul_m = re.match(r"^[-*•]\s+(.*)", line)
        if ol_m:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{ol_m.group(1)}</li>")
        elif ul_m:
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{ul_m.group(1)}</li>")
        else:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if line.strip():
                out.append(f"<p>{line}</p>")
    if in_ul:
        out.append("</ul>")
    if in_ol:
        out.append("</ol>")
    return "\n".join(out)


def _md_to_html(text: str) -> str:
    """markdown → 消毒后 HTML，优先用 markdown 库，回退手动转换。"""
    try:
        import markdown

        html = str(markdown.markdown(text, extensions=["tables", "fenced_code"]))
    except ImportError:
        html = _fallback_md_to_html(text)
    return sanitize_report_html(html)


class SolutionGenerator:
    def __init__(self) -> None:
        self._llm = ServiceLocator.get_llm_service()

    def generate(self, task: SolutionTask) -> None:
        """分段生成所有 section，单段失败不中断整体。"""
        research_results = self._load_research_results(task)
        existing: dict[str, str] = {}

        for i, section_type in enumerate(SECTION_ORDER):
            section = self._get_or_create_section(task, section_type, order=i)
            if section.status == SectionStatus.COMPLETED:
                existing[section_type] = section.content
                continue
            self._generate_section(task, section, research_results, existing)
            if section.status == SectionStatus.COMPLETED:
                existing[section_type] = section.content

            # 更新任务进度
            task.progress = int((i + 1) / len(SECTION_ORDER) * 100)
            task.message = f"正在生成：{section.title}（{i + 1}/{len(SECTION_ORDER)}）"
            task.save(update_fields=["progress", "message", "updated_at"])

    def regenerate_section(self, section: SolutionSection, feedback: str) -> None:
        """用户要求调整某段。"""
        task = section.task
        research_results = self._load_research_results(task)
        existing = self._get_existing_sections(task, exclude=section.section_type)
        section.user_feedback = feedback
        section.version += 1
        self._generate_section(task, section, research_results, existing, feedback=feedback)

    def _generate_section(
        self,
        task: SolutionTask,
        section: SolutionSection,
        research_results: str,
        existing: dict[str, str],
        feedback: str = "",
    ) -> None:  # pragma: no cover
        messages = build_section_prompt(
            section_type=section.section_type,
            case_summary=task.case_summary,
            research_results=research_results,
            existing_sections=existing,
            feedback=feedback,
        )
        section.prompt_used = str(messages)
        section.status = SectionStatus.GENERATING
        section.save(update_fields=["prompt_used", "status", "user_feedback", "version", "updated_at"])

        for attempt in range(1, _RETRY + 1):
            try:
                response = self._llm.chat(
                    messages=messages,
                    model=(task.llm_model or None),
                    fallback=True,
                    temperature=0.4,
                    max_tokens=_MAX_TOKENS,
                    timeout_seconds=_TIMEOUT,
                )
                content = str(getattr(response, "content", "") or "").strip()
                if not content:
                    raise ValueError("LLM 返回空内容")
                section.content = content
                section.html_content = _md_to_html(content)
                if not task.llm_model and getattr(response, "model", False):
                    task.llm_model = response.model
                    task.save(update_fields=["llm_model", "updated_at"])
                section.status = SectionStatus.COMPLETED
                section.save(update_fields=["content", "html_content", "status", "updated_at"])
                return
            except Exception as exc:
                logger.warning("段落生成失败 attempt=%d section=%s: %s", attempt, section.section_type, exc)
                if attempt < _RETRY:
                    time.sleep(1.5)

        section.status = SectionStatus.FAILED
        section.save(update_fields=["status", "updated_at"])

    @staticmethod
    def _get_or_create_section(task: SolutionTask, section_type: str, order: int) -> SolutionSection:
        section, _ = SolutionSection.objects.get_or_create(
            task=task,
            section_type=section_type,
            defaults={
                "order": order,
                "title": SECTION_TITLES.get(section_type, section_type),  # type: ignore[call-overload]
                "status": SectionStatus.PENDING,
            },
        )
        return section

    @staticmethod
    def _load_research_results(task: SolutionTask) -> str:
        if task.research_task_id is None:
            return ""
        results = list(
            task.research_task.results.filter()  # type: ignore[union-attr]
            .order_by("rank")
            .values(
                "rank", "title", "document_number", "court_text", "judgment_date", "case_digest", "similarity_score"
            )
        )
        if not results:
            return "未检索到类案。"
        lines: list[str] = []
        for r in results:
            lines.append(
                f"【案例{r['rank']}】{r['title']}\n"
                f"案号：{r['document_number']} | 法院：{r['court_text']} | 日期：{r['judgment_date']} | 相似度：{r['similarity_score']:.0%}\n"
                f"摘要：{r['case_digest'][:300]}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _get_existing_sections(task: SolutionTask, exclude: str = "") -> dict[str, str]:
        qs = task.sections.filter(status=SectionStatus.COMPLETED).order_by("order")
        if exclude:
            qs = qs.exclude(section_type=exclude)
        return {s.section_type: s.content for s in qs}
