"""长正文注入：`\\a` 断段 + 私用区哨兵加粗。

## 为什么需要这两步

模板里 `{{事实与理由}}` 所在的那一个 `w:p` 只有一份 `w:ind/@w:firstLine`，而 docxtpl
0.20.2 的 `resolve_listing()` 把值里的 `\\n` 换成 `<w:br/>`——软换行，仍在同一个 `w:p` 内，
于是长正文从第二行起就吃不到首行缩进：20 段事实缩成 1 段、只有第一行缩进 2 字。

同一个 `resolve_listing()` 还有第二条通道：`\\a`(0x07) 被换成
`</w:t></w:r></w:p><w:p>{原段 pPr}<w:r>{原 run rPr}<w:t>`，即**真断段且完整继承段落属性**。
所以正文段落一律用 `\\a` 连接（`to_body_text`），模板一个字都不用改。

加粗是这条通道的缺口：纯字符串带不了 `<w:b/>`。做法是把 `**x**` 改写成私用区哨兵
`\\ue000x\\ue001` 让 docxtpl 原样渲染（autoescape 只转义 XML 元字符，私用区字符不受影响），
渲染后由 `apply_bold_sentinels` 把哨兵区间拆成独立 run 并置粗，最后吃掉哨兵本身。

## 安全边界

`autoescape=True` 拦得住 `</w:t><w:fldSimple …>` 这类 OOXML 注入，但**拦不住 `\\a` 与 `\\f`**
——它们是有效控制符，不是 XML 元字符：`\\a` 能凭空断段、`\\f` 能凭空插分页，模型输出或
用户手填里出现一个 0x0C 就能把文书撕成两页。所以 `to_body_text` 先把输入里的 C0 全剥掉，
`\\a` 只由代码自己插入。

## 已知边界（调用方责任）

`numId≠0` 的占位符段落**不能**走 `\\a`：自动编号存在 `w:pPr/w:numPr` 里，`\\a` 断出的
每一段都继承它，一段正文变成 1./2./3./4. 编号项（`1-合同模板/专项合同.docx` 等 6 个模板
有这种段落，见 `test_long_text_injection.py` 里对应的 xfail）。调用方必须先确认目标占位符
段落的 `w:numPr` 缺失或 `w:numId` 为 0，再把值交给 `to_body_text`。本模块不做这项判断：
它只拿到值，拿不到模板。
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from copy import deepcopy
from io import BytesIO
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from lxml import etree

#: 加粗区间哨兵。Unicode 私用区：autoescape 不转义，模板与正文里都不会自然出现，
#: 因此「渲染后仍有哨兵」可以直接判成 bug。
BOLD_OPEN = "\ue000"
BOLD_CLOSE = "\ue001"

_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_W_P = qn("w:p")
_W_R = qn("w:r")
_W_T = qn("w:t")
_W_RPR = qn("w:rPr")
_W_B = qn("w:b")
_W_VAL = qn("w:val")
_DOCUMENT_PART = "word/document.xml"

#: C0 控制字符白名单之外的都剥掉：保留 \t(09) \n(0a)；\a(07) 断段、\f(0c) 分页、\v(0b)
#: 必须剥掉，\r(0d) 由 CRLF 归一先行消化，所以这里一并不留。
_C0_RE = re.compile(r"[\x00-\x08\x0b-\x1f]")
#: 成对星号才是加粗，单个 `*` 是正文。只作用于**值**，模板正文文案里的字面 `**`
#: （如律所名脱敏「某某（某某市）律师事务所」）不会经过这里。
_BOLD_MARKDOWN_RE = re.compile(r"\*\*(.+?)\*\*")
#: OOXML 的 `w:rPr` 是 sequence：`w:b` 必须排在 `w:rStyle`/`w:rFonts` 之后，写错顺序 Word 会
#: 丢掉这条 run 属性，所以不能简单 insert(0)。
_RPR_BEFORE_BOLD = frozenset({qn("w:rStyle"), qn("w:rFonts")})


def to_body_text(paragraphs: list[str] | str) -> str:
    """段落列表/带换行字符串 → 供 docxtpl 渲染的正文。

    段落之间用 `\\a`(0x07) 连接，docxtpl 的 `resolve_listing()` 会把它换成真 `<w:p>` 并继承
    占位符段落的 `w:pPr`/`w:rPr`，首行缩进、行距、对齐因此逐段生效。

    剥掉除 `\\t` `\\n` `\\r` 之外的全部 C0 控制字符：`\\f`(分页) 会撕页，输入里自带的 `\\a`
    会被当成断段——那是模型自己改结构，与「LLM 只能返回值」的边界冲突。所以**先剥再自己插**
    `\\a`；输入里的 `\\n` 一律转成 `\\a`（软换行不是段落）。

    注意 `numId≠0` 的占位符段落不适用：编号在 `w:pPr/w:numPr` 里会被每段继承，一段正文
    变成一串自动编号项。这项判断要读模板，属调用方责任。

    这个函数**不可重复调用**：已转好的正文里全是 `\\a`，再过一遍会被当成输入控制符剥掉，
    多段又压回一段。已统一的转换入口就不要再自己预调一次。
    """
    items = [paragraphs] if isinstance(paragraphs, str) else list(paragraphs)
    return "\a".join(_clean_paragraph(item) for item in items).replace("\n", "\a")


def markdown_bold_to_sentinel(text: str) -> str:
    """把 `**x**` 转成 `\\ue000x\\ue001`（私用区哨兵，autoescape 不会吃掉它）。

    加粗区间不跨行：`**` 配对必须落在同一行内，写歪了的 `**` 原样留着不猜。
    """
    return _BOLD_MARKDOWN_RE.sub(lambda match: f"{BOLD_OPEN}{match.group(1)}{BOLD_CLOSE}", text)


def apply_bold_sentinels(docx_bytes: bytes) -> bytes:
    """渲染后处理：只处理含哨兵的段落，把哨兵区间拆成独立 run 并置 `<w:b/>`，然后吃掉哨兵本身。

    没有哨兵时**原样返回入参 bytes**（不重打包，逐字节相同）：绝大多数模板不含长正文，
    它们不该经过一次 docx 重新序列化。
    """
    if not _sentinel_count(docx_bytes):
        return docx_bytes

    document = Document(BytesIO(docx_bytes))
    for paragraph in document.element.iter(_W_P):
        _apply_paragraph(paragraph)

    output = BytesIO()
    document.save(output)
    rendered = output.getvalue()

    leftover = _sentinel_count(rendered)
    if leftover:
        # 哨兵只可能由本模块写入。残留说明拆分逻辑漏了，此时宁可炸，也不把 U+E000 印进正式文书。
        raise RuntimeError(f"加粗哨兵残留 {leftover} 个，长正文注入器有 bug")

    return rendered


def _clean_paragraph(value: object) -> str:
    """单段清洗：CRLF 归一 → 剥 C0（含输入自带的 `\\a` 与 `\\f`）。"""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return _C0_RE.sub("", text)


def _sentinel_count(docx_bytes: bytes) -> int:
    """`word/document.xml` 里的哨兵字符数。

    只看正文部件：占位符的值只会落进正文，正文也是 `apply_bold_sentinels` 唯一处理的地方，
    两处口径必须一致，否则「无哨兵则原字节返回」会掩盖掉别的部件里的残留。
    """
    with zipfile.ZipFile(BytesIO(docx_bytes)) as archive:
        if _DOCUMENT_PART not in archive.namelist():
            raise ValueError("不是合法的 docx：缺 word/document.xml")
        xml = archive.read(_DOCUMENT_PART).decode("utf-8")
    return xml.count(BOLD_OPEN) + xml.count(BOLD_CLOSE)


def _apply_paragraph(paragraph: Any) -> None:
    """只重排含哨兵的 run。

    加粗状态在一段开头重置为 False：写得歪的 `**` 跨了 `\\a`（进而跨了 `<w:p>`）时，
    加粗不会溢出到下一个段落——溢出的排版事故比「加粗少半行」严重得多。
    """
    bold = False
    for run in _iter_runs(paragraph):
        if not _run_has_sentinel(run):
            continue
        segments, bold = _split_run(run, bold)
        _replace_run(run, segments)


def _iter_runs(container: Any) -> Iterator[Any]:
    """按文档顺序取出容器里的 run；不跨段（`w:hyperlink`/`w:ins` 这类容器照样下探）。"""
    for child in container:
        if child.tag == _W_R:
            yield child
        elif child.tag != _W_P:
            yield from _iter_runs(child)


def _run_has_sentinel(run: Any) -> bool:
    return any(BOLD_OPEN in (node.text or "") or BOLD_CLOSE in (node.text or "") for node in run.findall(_W_T))


def _split_run(run: Any, bold: bool) -> tuple[list[tuple[bool, list[Any]]], bool]:
    """把 run 按哨兵切成 `[(是否加粗, 子元素…), …]`，并返回出段时的加粗状态。

    `w:tab`/`w:br` 这类没有文本的子元素跟着它当前所在的片段走，不单独拆开。
    """
    segments: list[tuple[bool, list[Any]]] = []
    current: list[Any] = []
    for child in run:
        if child.tag == _W_RPR:
            continue
        text = child.text or ""
        if child.tag != _W_T or not (BOLD_OPEN in text or BOLD_CLOSE in text):
            current.append(child)
            continue
        for piece_bold, piece_text in _split_text(text, bold):
            if piece_bold != bold:
                if current:
                    segments.append((bold, current))
                current, bold = [], piece_bold
            if piece_text:
                current.append(_text_element(piece_text))
    if current:
        segments.append((bold, current))
    return segments, bold


def _split_text(text: str, bold: bool) -> list[tuple[bool, str]]:
    """按哨兵切文本。哨兵本身不进入结果（在边界处切出空片段，由调用方按需丢弃）。"""
    pieces: list[tuple[bool, str]] = []
    buffer: list[str] = []
    for char in text:
        if char in (BOLD_OPEN, BOLD_CLOSE):
            pieces.append((bold, "".join(buffer)))
            buffer, bold = [], char == BOLD_OPEN
        else:
            buffer.append(char)
    pieces.append((bold, "".join(buffer)))
    return pieces


def _text_element(text: str) -> Any:
    element = etree.Element(_W_T)
    element.set(_XML_SPACE, "preserve")
    element.text = text
    return element


def _replace_run(run: Any, segments: list[tuple[bool, list[Any]]]) -> None:
    """用分段结果替换原 run：`w:rPr` 整份复制（保住字号/字体），加粗段额外补 `<w:b/>`。"""
    parent = run.getparent()
    index = parent.index(run)
    shell = deepcopy(run)
    for child in list(shell):
        shell.remove(child)
    r_pr = run.find(_W_RPR)
    parent.remove(run)

    for offset, (is_bold, children) in enumerate(segments):
        new_run = deepcopy(shell)
        if r_pr is not None:
            new_run.append(deepcopy(r_pr))
        if is_bold:
            _set_bold(new_run)
        for child in children:
            new_run.append(child)
        parent.insert(index + offset, new_run)


def _set_bold(run: Any) -> None:
    """补 `<w:b/>`。复制来的 `w:rPr` 可能带着 `<w:b w:val="0"/>`（模板原本显式不加粗），
    必须把 val 摘掉而不是只加一个空 `<w:b/>`，否则加粗被原属性挡住。"""
    r_pr = run.find(_W_RPR)
    if r_pr is None:
        r_pr = etree.Element(_W_RPR)
        run.insert(0, r_pr)
    bold = r_pr.find(_W_B)
    if bold is None:
        bold = etree.Element(_W_B)
        insert_at = 0
        for offset, child in enumerate(r_pr):
            if child.tag in _RPR_BEFORE_BOLD:
                insert_at = offset + 1
        r_pr.insert(insert_at, bold)
    bold.attrib.pop(_W_VAL, None)
