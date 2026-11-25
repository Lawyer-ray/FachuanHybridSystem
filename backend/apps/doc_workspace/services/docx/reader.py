"""读出 docx 里**已有的**修订痕迹与批注。

## 为什么 AI 需要这个

律师问「这份合同现在有哪些未处理的修改」，模型必须能看见**文档里已经有的**修订
（包括他自己之前落的、律师手工改的）。否则它会把同一件事再提一遍，或者把已经被
接受/拒绝的痕迹当成现行文本去改。

配对口径与 Word 的显示一致：同一段落里按出现顺序把 `w:del` 与 `w:ins` 配成一条
修改；落单的 `w:del` 视为「删除」、落单的 `w:ins` 视为「插入」。
"""

from __future__ import annotations

from dataclasses import dataclass

from docx.document import Document as DocumentType
from docx.oxml.ns import qn

from .text import iter_paragraphs

_W_INS = qn("w:ins")
_W_DEL = qn("w:del")
_W_T = qn("w:t")
_W_DELTEXT = qn("w:delText")
_W_AUTHOR = qn("w:author")
_W_ID = qn("w:id")


@dataclass(frozen=True)
class ExistingRevision:
    """文档里一条已有的修订。"""

    paragraph_index: int
    author: str
    original: str
    """被删掉的文本（纯插入时为空串）"""

    suggested: str
    """插入的文本（纯删除时为空串）"""

    rev_ids: tuple[int, ...]
    """这条修改对应的 `w:ins`/`w:del` 的 id（按结论撤回时要用）"""


def _text_of(elem: object) -> str:
    parts: list[str] = []
    for t in elem.iter(_W_T, _W_DELTEXT):  # type: ignore[attr-defined]
        parts.append(t.text or "")
    return "".join(parts)


def _author_of(elem: object) -> str:
    return str(elem.get(_W_AUTHOR) or "")  # type: ignore[attr-defined]


def _id_of(elem: object) -> int | None:
    raw = elem.get(_W_ID)  # type: ignore[attr-defined]
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def read_revisions(doc: DocumentType) -> list[ExistingRevision]:
    """按段落收集修订，同段内 del/ins 顺序配对。"""
    out: list[ExistingRevision] = []
    for index, paragraph in enumerate(iter_paragraphs(doc)):
        dels = list(paragraph._element.iter(_W_DEL))
        inss = list(paragraph._element.iter(_W_INS))
        if not dels and not inss:
            continue
        for i in range(max(len(dels), len(inss))):
            dele = dels[i] if i < len(dels) else None
            inse = inss[i] if i < len(inss) else None
            rev_ids = tuple(
                x
                for x in (_id_of(dele) if dele is not None else None, _id_of(inse) if inse is not None else None)
                if x is not None
            )
            out.append(
                ExistingRevision(
                    paragraph_index=index,
                    # 优先取插入的作者：纯删除时插入为空，取删除的作者
                    author=_author_of(inse) if inse is not None else _author_of(dele),
                    original=_text_of(dele) if dele is not None else "",
                    suggested=_text_of(inse) if inse is not None else "",
                    rev_ids=rev_ids,
                )
            )
    return out


def count_revisions(doc: DocumentType) -> int:
    return len(read_revisions(doc))


__all__ = ["ExistingRevision", "count_revisions", "read_revisions"]
