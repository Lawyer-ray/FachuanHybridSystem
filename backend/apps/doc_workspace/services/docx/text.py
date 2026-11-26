"""docx 的「文本口径」与段落遍历——所有定位算法共用的唯一一套定义。

## 为什么口径必须只有一份

同一份合同里，`python-docx` 的 `paragraph.text`、Word 画布上显示的文本、
「接受全部修订后」的文本，三者并不相同：

- `paragraph.text` **看不见 `w:ins`**（修订插入的内容被整个跳过）；
- 它**看得见 `w:del` 之前被删掉的文本吗**？也看不见（`w:delText` 不是 `w:t`），
  但它会把 `w:ins` 漏掉，于是「改过一次的段落」永远定位失败。

所以定位必须用**现行文本**：直接 run 的 `w:t` + 修订插入的 `w:t`，不含 `w:delText`。
这与律师在画布里看到的（`reviewDisplay: markup` 下带痕迹的正文）一致，也与
「接受全部修订后」的文本一致。

`paragraph.text` 与 `visible_text` 一旦在两条链路里各算各的，就会出现
「AI 说改好了、画布上找不到原文」这种无法复现的偶发失败。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

from docx.document import Document as DocumentType
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

#: 段落里「有视觉内容但不是纯文本」的标签：这类 run 不能按字符切开
#: （切了就会丢制表符/换行/图片/脚注锚点），只能整块删除或整块保留。
_COMPLEX_RUN_TAGS = frozenset(
    {
        qn("w:tab"),
        qn("w:br"),
        qn("w:cr"),
        qn("w:drawing"),
        qn("w:pict"),
        qn("w:object"),
        qn("w:footnoteReference"),
        qn("w:endnoteReference"),
        qn("w:commentReference"),
        qn("w:sym"),
        qn("w:fldChar"),
        qn("w:instrText"),
    }
)

_WS_RE = re.compile(r"[\s\u00a0\u3000]+")


def normalize(text: str) -> str:
    """比对用归一化：折叠全半角 + 去掉所有空白。

    只用于**比对**，绝不用于写盘——落笔时必须用文档里的真实区间文本，
    否则删掉的和记录下来的对不上账。
    """
    return _WS_RE.sub("", unicodedata.normalize("NFKC", text or ""))


def run_text(run_element: object) -> str:
    """一个 `w:r` 的可见文本（忽略 `w:delText` 与复杂子元素）。"""
    parts: list[str] = []
    for t in run_element.findall(qn("w:t")):  # type: ignore[attr-defined]
        parts.append(t.text or "")
    return "".join(parts)


def run_has_complex_child(run_element: object) -> bool:
    """这个 run 里有没有「不能按字符切」的东西（制表符/图片/脚注锚点…）。"""
    for child in run_element:  # type: ignore[attr-defined]
        if child.tag in _COMPLEX_RUN_TAGS:
            return True
    return False


def visible_text(paragraph: Paragraph) -> str:
    """段落现行文本：直接 run + `w:ins` 内的 run，不含 `w:del`。"""
    parts: list[str] = []
    for child in paragraph._element:
        if child.tag == qn("w:r"):
            parts.append(run_text(child))
        elif child.tag == qn("w:ins"):
            for run in child.findall(qn("w:r")):
                parts.append(run_text(run))
    return "".join(parts)


def iter_paragraphs(doc: DocumentType) -> Iterator[Paragraph]:
    """遍历**全部**段落，含表格单元格与嵌套表格。

    **为什么不用 `doc.paragraphs`**：它只看 body 的直接子节点，看不到表格。
    而付款条款、金额、履行期限这些最需要 AI 审的内容恰恰最常放在表格里
    （`contract_review` 里已有两处踩过这个坑：`docx_revision_reader` 与
    `patch.service.docx_full_text` 都绕开了 `doc.paragraphs`）。
    """
    for p in doc.element.body.iter(qn("w:p")):
        parent_ok = True
        # `w:p` 也可能出现在文本框（w:txbxContent）里，那也是正文的一部分，照收
        if parent_ok:
            yield Paragraph(p, doc)


def full_text(doc: DocumentType) -> str:
    """整篇现行文本（段落间 `\\n`）——做区间冲突检测与 diff 用。"""
    return "\n".join(visible_text(p) for p in iter_paragraphs(doc))
