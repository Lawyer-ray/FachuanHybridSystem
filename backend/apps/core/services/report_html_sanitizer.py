"""报告 HTML 白名单消毒 — 跨 app 共享工具。

LLM 生成的 markdown 报告转 HTML 后、经模板 ``|safe`` 渲染前统一调用，
剥离脚本、事件属性、危险协议与注释。当前使用方：
- ``apps.legal_solution``：方案报告（生成落库前 + 渲染兜底双层消毒）
- ``apps.contract_review``：合同审查评估报告（admin report / report_pdf 视图）
"""

from __future__ import annotations

import bleach
from bleach.css_sanitizer import CSSSanitizer

# ── 报告 HTML 消毒白名单 ──────────────────────────────────────────────────────
# 覆盖 markdown（tables/fenced_code）输出与报告模板实际使用的全部合法标签：
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
    """报告 HTML 白名单消毒：剥离脚本/事件属性/危险协议/注释（strip 模式）。"""
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
