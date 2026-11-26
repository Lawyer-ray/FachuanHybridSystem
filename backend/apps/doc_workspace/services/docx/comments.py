"""把「不宜改正文的意见」写成 Word 原生批注（`comments.xml` + `w:commentRange*`）。

## 为什么必须有批注这一路

审查结论分成两类，硬塞进同一类会出事：

| 结论 | 正确载体 | 塞错会怎样 |
|---|---|---|
| 有确定改法（"订金"→"定金"） | 修订 `w:ins/w:del` | —— |
| 只有风险/商业判断（"违约金无上限，是否接受取决于谈判地位"） | **批注** | 强行给改法 = 替律师做商业决定 |
| 缺失项、无法定位（"建议补一份保密协议作为附件"） | **批注** | 锚不到就没地方放，结论直接丢掉 |
| 起草未决项（"付款节点待商业确认"） | **批注** | 起草稿看不出「为什么这里空着」 |

没有批注通道时，这些结论只能留在侧栏清单里——律师一旦导出 docx 交给客户，
意见就丢了。

## 锚点为什么落在「整段」而不是精确到字

精确到字要在 `w:r` 边界做切分，而一旦选中范围跨越 `w:ins`（别人刚插入的修订）
就会产生 `w:commentRangeStart` 落在 `w:ins` 内部的非法结构。整段锚定不会切坏
任何 run，Word/WPS/LO 全都能正确展开，代价只是批注框挂在段落上而不是某几个字上。

**这个代价是可接受的**：批注正文里第一条就写着被评论的原文（`【原文】…`），
律师看到的是「这段文字下的这条意见」，而不是「这句话里这几个字下的意见」。
真要精确到字，走画布内的 DS 插件 `AddComment({QuoteText})`——那是 DS 自己解析锚点。
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from docx.opc.constants import CONTENT_TYPE as CT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from .revision import _document_root, resolve_ai_author

logger = logging.getLogger(__name__)

_W_COMMENTS = qn("w:comments")
_W_COMMENT = qn("w:comment")
_W_P = qn("w:p")
_W_R = qn("w:r")
_W_T = qn("w:t")
_W_ID = qn("w:id")
_W_AUTHOR = qn("w:author")
_W_DATE = qn("w:date")
_W_INITIALS = qn("w:initials")
_W_RANGE_START = qn("w:commentRangeStart")
_W_RANGE_END = qn("w:commentRangeEnd")
_W_REFERENCE = qn("w:commentReference")
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_COMMENTS_PARTNAME = "/word/comments.xml"


class _CommentsPart(Part):
    """可变的 comments part。

    python-docx 没有 comments 的一等支持，`Part.blob` 是只读属性。这里持一棵
    lxml 树、在 `blob` 里现序列化，避免反复「解字节 → 改 → 序列化回字节」。
    """

    def __init__(self, partname: PackURI, content_type: str, element: Any, package: Any) -> None:
        super().__init__(partname, content_type, b"", package)
        self._element = element

    @property
    def element(self) -> Any:
        return self._element

    @property
    def blob(self) -> bytes:
        from lxml import etree

        return bytes(etree.tostring(self._element, xml_declaration=True, encoding="UTF-8", standalone=True))


def _comments_part(doc: Any) -> _CommentsPart:
    """取（或建）comments part，并保证 document 有一条 COMMENTS 关系。"""
    document_part = doc.part
    for rel in document_part.rels.values():
        if rel.reltype == RT.COMMENTS:
            target = rel.target_part
            if isinstance(target, _CommentsPart):
                return target
            # 已有但类型不认识：包一层，保住原有 XML
            from lxml import etree

            element = etree.fromstring(target.blob)
            wrapped = _CommentsPart(target.partname, CT.WML_COMMENTS, element, document_part.package)
            return wrapped

    element = OxmlElement("w:comments")
    part = _CommentsPart(
        PackURI(_COMMENTS_PARTNAME),
        CT.WML_COMMENTS,
        element,
        document_part.package,
    )
    document_part.relate_to(part, RT.COMMENTS)
    return part


def _next_comment_id(root: Any) -> int:
    biggest = 0
    for elem in root.iter(_W_COMMENT):
        raw = elem.get(_W_ID)
        if raw is None:
            continue
        try:
            biggest = max(biggest, int(raw))
        except ValueError:
            continue
    return biggest + 1


def _now_stamp() -> str:
    """批注时间：**本地时间 + 显式时区偏移**（如 `2026-11-26T14:41:53+08:00`）。

    ## 为什么不是 `...Z`（真 UTC）

    存成 UTC 是 OOXML 的标准做法，Word 会按本机时区换算后显示，没问题。但
    **OnlyOffice 修订/批注栏按原样显示**：实测一条 `06:41:53Z` 的批注在 DS 里就写成
    06:41，而当时本地是 14:41 —— 律师看到「批注是凌晨留的」，自然会怀疑是别人改的。

    ## 为什么也不是「本地时间 + Z」

    那个更糟：`revision.py` 记着踩过的坑——本地时间冒充 UTC，Word 换算后整整偏 8 小时。

    带偏移的 xsd:dateTime 是标准写法（`+08:00`），Word 换算成同一时刻显示，DS 原样显示
    也是本地钟点，两端都对。
    """
    from django.utils import timezone

    return timezone.localtime().isoformat(timespec="seconds")


def _comment_body(text: str, quote: str) -> Any:
    """一条批注的内容：第一行标出被评论的原文，再写意见本身。"""
    p = OxmlElement("w:p")
    if quote:
        first = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.text = f"【原文】{quote}"
        t.set(_XML_SPACE, "preserve")
        first.append(t)
        p.append(first)
        para_break = OxmlElement("w:r")
        para_break.append(OxmlElement("w:br"))
        p.append(para_break)
    body = OxmlElement("w:r")
    t2 = OxmlElement("w:t")
    t2.text = text
    t2.set(_XML_SPACE, "preserve")
    body.append(t2)
    p.append(body)
    return p


@dataclass(frozen=True)
class CommentResult:
    ok: bool
    reason: str = ""
    comment_id: int = 0


def add_comment(
    paragraph: Paragraph,
    *,
    text: str,
    quote: str = "",
    author: str | None = None,
    initials: str = "",
    date: str | None = None,
) -> CommentResult:
    """给整段挂一条批注。

    `quote` 只进批注正文（让律师知道具体在说哪句话），不参与锚定。
    """
    if not (text or "").strip():
        return CommentResult(ok=False, reason="批注内容为空")

    # `paragraph.part` 在 python-docx 的 stub 里被标成 StoryPart（没有 .document），
    # 但运行时它就是 DocumentPart，`.document` 可用
    doc = paragraph.part.document  # type: ignore[attr-defined]
    part = _comments_part(doc)
    comment_id = _next_comment_id(part.element)

    resolved_author = (author or "").strip() or resolve_ai_author()
    # 缩写取署名首两字：空 initials 在 Word 里会画成一个空白头像块
    resolved_initials = (initials or "").strip() or resolved_author[:2]

    comment = OxmlElement("w:comment")
    comment.set(_W_ID, str(comment_id))
    comment.set(_W_AUTHOR, resolved_author)
    comment.set(_W_INITIALS, resolved_initials)
    comment.set(_W_DATE, date or _now_stamp())
    comment.append(_comment_body(text.strip(), quote.strip()))
    part.element.append(comment)

    # 锚点落在整段：start 放段首，end + reference 放段尾
    start = OxmlElement("w:commentRangeStart")
    start.set(_W_ID, str(comment_id))
    end = OxmlElement("w:commentRangeEnd")
    end.set(_W_ID, str(comment_id))
    reference_run = OxmlElement("w:r")
    reference = OxmlElement("w:commentReference")
    reference.set(_W_ID, str(comment_id))
    reference_run.append(reference)

    element = paragraph._element
    element.insert(0, start)
    element.append(end)
    element.append(reference_run)
    return CommentResult(ok=True, comment_id=comment_id)


def add_comments(
    doc: Any,
    targets: list[tuple[Paragraph, str, str]],
    *,
    author: str | None = None,
) -> list[CommentResult]:
    """批量加批注。单条失败不影响其他条（批注不改变正文，没有「部分写入更危险」的问题）。"""
    out: list[CommentResult] = []
    for paragraph, text, quote in targets:
        out.append(add_comment(paragraph, text=text, quote=quote, author=author))
    return out


def count_comments(doc: Any) -> int:
    """文档里有几条批注（测试与审计用）。"""
    try:
        return len(_comments_part(doc).element.findall(_W_COMMENT))
    except (OSError, ValueError, KeyError, AttributeError):
        # 没有 comments part / 文档结构异常时按 0 条算——这是诊断用计数，不该让调用方炸
        return 0


__all__ = ["CommentResult", "add_comment", "add_comments", "count_comments", "copy"]
