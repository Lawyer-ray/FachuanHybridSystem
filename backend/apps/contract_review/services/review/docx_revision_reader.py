"""从 docx 里把修订痕迹读回来（人工修订 → 清单）。

**为什么需要**：AI 的建议写进 `ReviewRevision` 表，律师在 OnlyOffice 里
自己改的内容写进 docx 的 `w:ins`/`w:del`。两条路各走各的，左栏清单就
看不见律师的手工修改——他改完一份合同，清单里还是「待决策 12 条」，
但实际已经改好的那些条目还挂着。

这里把 docx 的修订痕迹解析成与 AI 产出同构的 `ReviewResult`，再交给
`_persist_revisions` 以 `kind=MANUAL` 落库：同一份文档、同一个左栏、
同一套采纳/驳回，只是来源不同（AI 建议 / 律师手改）。

**配对规则**：Word 把一处修改存成相邻的 `<w:del>旧</w:del><w:ins>新</w:ins>`
（删除在前、插入在后，同一作者同一时间）。纯插入（只有 ins）与纯删除
（只有 del）也各自算一条——它们同样是「改动」，律师也需要确认。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from docx.document import Document as DocumentType
from lxml import etree

logger = logging.getLogger(__name__)

# OOXML 明细：删除的文本在 w:delText 里，插入的在 w:t 里
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _qn(tag: str) -> str:
    return f"{{{_W_NS}}}{tag}"


@dataclass(frozen=True)
class DocxRevision:
    """docx 里的一条修订痕迹。"""

    original: str
    suggested: str
    author: str
    paragraph_index: int


def _run_text(elem: etree._Element, *, is_delete: bool) -> str:
    """取一个 w:ins / w:del 里的全部文本。

    删除修订的文本在 `w:delText`，插入在 `w:t`；两者都要收，
    否则纯删除条目会读出空串而被当成无效修订丢掉。
    """
    tag = "delText" if is_delete else "t"
    parts: list[str] = []
    for node in elem.iter(_qn(tag)):
        if node.text:
            parts.append(node.text)
    return "".join(parts)


def _author_of(elem: etree._Element) -> str:
    return (elem.get(_qn("author")) or "").strip()


def _date_of(elem: etree._Element) -> str:
    return (elem.get(_qn("date")) or "").strip()


def extract_revisions(doc: DocumentType) -> list[DocxRevision]:
    """按段落顺序抽全部修订痕迹，相邻的 del+ins 配成一条修改。

    不依赖 `doc.paragraphs`（它看不到表格里的段落，而合同常把付款条款
    放在表格里）：直接遍历 body 下的所有 w:p。
    """
    body = doc.element.body
    results: list[DocxRevision] = []

    for idx, para in enumerate(body.iter(_qn("p"))):
        dels: list[tuple[str, str, str]] = []  # (text, author, date)
        inses: list[tuple[str, str, str]] = []
        for child in para:
            if child.tag == _qn("del"):
                dels.append((_run_text(child, is_delete=True), _author_of(child), _date_of(child)))
            elif child.tag == _qn("ins"):
                inses.append((_run_text(child, is_delete=False), _author_of(child), _date_of(child)))

        if not dels and not inses:
            continue

        # 相邻配对：删除在前、插入在后（Word 与 DocxRevisionTool 都是这个顺序）
        paired = min(len(dels), len(inses))
        for i in range(paired):
            d_text, d_author, _ = dels[i]
            i_text, i_author, _ = inses[i]
            results.append(
                DocxRevision(
                    original=d_text,
                    suggested=i_text,
                    author=i_author or d_author or "未知",
                    paragraph_index=idx,
                )
            )
        # 落单的删除（删了没补）与落单的插入（凭空加）各算一条
        for d_text, d_author, _ in dels[paired:]:
            if d_text.strip():
                results.append(
                    DocxRevision(original=d_text, suggested="", author=d_author or "未知", paragraph_index=idx)
                )
        for i_text, i_author, _ in inses[paired:]:
            if i_text.strip():
                results.append(
                    DocxRevision(original="", suggested=i_text, author=i_author or "未知", paragraph_index=idx)
                )

    return [r for r in results if (r.original or r.suggested)]
