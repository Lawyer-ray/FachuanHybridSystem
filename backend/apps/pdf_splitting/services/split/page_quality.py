"""页面内容质量画像：判定一页是正常文本页、图形页，还是低质量页。

## 为什么需要这一层

一份 164 页银行卷宗实测每页 OCR 字符数：正常文本页 1000–6000 字，而 p147 只有
**6 字**（宗地图）、p148 **47 字**（平面图）；文字少于 60 字的共 12 页，是封面、
身份证、图纸、盖章页。这些页在 Markdown 里就是几行零散字符，**律师看不出那是图纸**，
而图纸恰恰是抵押案件的关键证据。

所以这里只说一句话：这一页的文本里**看不全内容**，建议核对原图。系统从不假装
「这页没有内容」——「看不出」必须显式说出来。

## 判据与顺序（按 576 真实版面数据定，先命中者胜出）

``blank`` → ``graphic`` → ``sparse`` → ``text``。

**为什么不用 image 块判图形页**：MinerU 输出里 image 块太常见了——页眉 logo、印章、
表格截图都会给 image 块。真实反证：

| 页 | 块（类型, 字数） | 真相 |
|---|---|---|
| p8 | ``table 587`` + 2×``image 0`` | 银行欠款明细表，**真表格** |
| p23 | ``image 0`` + ``text 13`` + ``text 31`` | 身份证，**有真实内容** |
| p148 | ``image 0`` + ``text 0`` + ``text 31`` + ``text 15`` | 平面图 |

「有 image 块」因此**完全不参与判定**，只用来补 reason 文案。

**真正可靠的图形信号是「有表格结构、没有表格内容」**：

| 页 | table 块字数 | 真相 |
|---|---|---|
| p147 宗地图 | 6 | 大图形被当成 table 块，抽不出字 |
| p8 明细表 | 587 | 真表格 |
| p52 银行流水 | 10806 | 真表格 |

MinerU 遇到大面积图形（宗地图/平面图/表格截图）时会给 table 块却抽不出字，
所以「table 块字数 < 50」是比 image 块强得多的判据。

**image 块只在「没有 table 块」时才作为判据**：p148 平面图
``[image 0, text 0, text 31, text 15]`` 没有 table 块，31/15 字全是印章套话，剔除套话后
有效字符 27，加上 image 块才认得出是图纸；而 p8 有 table 587 字，以表格为准。

这条 image 判据还要排除**业务字段标签**：p23 身份证 ``[image 0, text 13, text 31]``
与 p148 在块形状/字数上完全同类，只看形状会把身份证也判成「请核对原图」。
分界在内容——p23 剩「居民身份证」，p148 剔除套话后只剩乱码（见 ``_B2_FIELD_LABEL_RE``）。

**为什么不按字数直接判图形页**：身份证字段密集（姓名/性别/住址/公民身份号码），
整页 45 字且几乎没有完整句子；合同首页（p116，71 字，7 个 text 块）同样凑不出
成句中文。仅凭字数或仅凭「没有句子」都会把它们误判成图纸。所以文本启发只在
**没有 table 块**时才启用，且要求字数 < 60。

纯函数、无 Django 依赖、只用 stdlib：同一份判定要能被 pipeline、job API、
前端复核入口反复调用，不能因为调用方没起 Django 就不可用。

## 证件页要说出「这是什么、缺了什么」

只说「内容较少」对律师没用：p23 身份证 45 字、姓名/身份证号/住址全丢，他看到的是
一句「可能是封面/证件/表单」。所以 sparse / graphic 两类页在判完之后再过一道
:mod:`doc_type`：认出材料类型（``doc_hint``）并点名缺失的关键字段，替换掉泛泛的
reason。正常文本页不参与——内容读全了，律师自己看得见，多一句话只会稀释提示。
判据本身在 ``doc_type.py``（本文件已接近行数红线），这里只做接入。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from .doc_type import describe_doc_page, detect_doc_hint

#: 「table 块无内容」的字数上界（不含）。p147 宗地图的 table 块 6 字，
#: 而真表格 p8 是 587 字、p52 是 10806 字——50 落在这个悬殊的空档中间。
_TABLE_EMPTY_MAX_CHARS = 50

#: 备用图形判据的字数上界（不含）：没有 table 块时，字极少 + 没有成句中文。
#: p148 平面图 46 字；p116 合同首页 71 字不在其内，会落进 sparse。
_GRAPHIC_MAX_CHARS = 60

#: 「sparse」的上界（不含）。60～200 字是封面、证件、合同首页、表单的实际区间：
#: 内容真实但不足以自证是什么材料，需要律师核对。
_SPARSE_MAX_CHARS = 200

#: 认不出材料类型时的 sparse 文案；认得出就换成 ``doc_type.describe_doc_page`` 的
#: 具体说法（“这页是身份证，但姓名 / 身份证号 / 住址 均未读出”）。
_SPARSE_REASON = "内容较少，可能是封面/证件/表单，建议核对"

#: 跨页高频的印章/核对套话。**必须先剔除再统计**，否则每一页都能从中读出
#: 「已核对与原件相符」这种成句中文，图形页的文本启发就永远不成立。
_STAMP_BOILERPLATE_RE = re.compile(
    r"(?:已核对与原件相符|扫描件与留档资料相符|与原件核[对符]|经办人[:：][^\n]*|编号\s*NOD[0-9A-Za-z\-]*)"
)

#: 一页「在写成句的话」的最短中文片段长度。6 字以下多是字段标签、印章文字、
#: 图注（「不动产权证书号」「民政局」），不构成一句叙述。
_SENTENCE_MIN_CHARS = 6

#: 连续中文片段。只认 CJK 统一表意文字（U+4E00–U+9FFF）：数字、ASCII、标点、
#: 全角空格都会切断片段，OCR 把字段挤成一行也不会拼成句子。
_CN_RUN_RE = re.compile(r"[\u4e00-\u9fff]{%d,}" % _SENTENCE_MIN_CHARS)

#: 「字段密集」的排布：一行里挤着多个字段标签，中间没有标点、只有空格或竖线。
#: 身份证 / 户口本 OCR 的典型形态（``姓名 张三 性别 男 民族 汉``）。
_FIELD_LABEL_RE = re.compile(r"(?:姓名|性别|民族|出生|住址|签发机关|有效期限|公民身份号码)")
_FIELD_RUN_MIN = 3

#: b2 用的**业务字段标签**白名单：有这些词就说明这页是证件/笔录/单据，不是图纸。
#: 口径刻意收敛（不用「任意 2 字中文」）——取向是「宁可漏判 graphic，也不误伤证件页」：
#: 图纸被标成 sparse 只少一条提示，身份证被标成「请核对原图」会让律师每次都翻一眼，
#: 很快就无视所有提示。实测：p23「居民身份证」、p41「面谈笔录表」命中；
#: p148 平面图剔除套话后只剩乱码，一个都不命中。
_B2_FIELD_LABEL_RE = re.compile(
    r"姓名|身份证|居民|户口|公司|银行|支行|分行|合同|协议|凭证|发票|"
    r"日期|金额|编号|账号|单位|地址|电话|证书|报告|清单|笔录|申请书|证明"
)

#: 字段名与分隔符之后的 6 字以上中文取值。用它把字段页拆成一段段短值，
#: 否则身份证的住址（20+ 字连写）会冒充「成句中文」。
_FIELD_VALUE_RE = re.compile(
    r"(?:姓名|性别|民族|出生|住址|签发机关|有效期限|公民身份号码)[\s|:：]*([\u4e00-\u9fff]{6,})"
)

#: 块类型词汇：与 document_parsing 的块词汇表对齐，内联一份以守住「纯 stdlib」。
_TABLE_BLOCK_TYPES = frozenset({"table"})
_IMAGE_BLOCK_TYPES = frozenset({"image", "figure", "picture", "inline_object", "inlineimage"})

PageKind = Literal["text", "sparse", "graphic", "blank"]


@dataclass(frozen=True)
class PageQuality:
    """单页内容质量画像。``reason`` 直接给律师看，不做二次加工。"""

    page_no: int
    char_count: int
    kind: PageKind
    reason: str
    needs_visual_review: bool
    #: 认出的材料类型（``id_card`` / ``household`` / ``property_cert`` …），认不出为 None。
    #: 只在 ``sparse`` / ``graphic`` 时填：正常文本页不需要「这是什么证件」的提示。
    doc_hint: str | None = None


def assess_page_quality(*, page_no: int, text: str, layout: dict | None = None) -> PageQuality:
    """判定一页的内容形态。

    ``text`` 是这一页的取字结果（OCR / 文本层即可，不必清洗）。
    ``layout`` 是该页的版面结构（可含 ``blocks`` 列表）；拿不到就传 None，
    此时只用文本启发——缺 layout 只会让判定更保守，不会让页面凭空变成图形页。
    ``char_count`` 是剔除印章套话后的有效字数，与判据口径一致。
    """
    raw = text if isinstance(text, str) else ""
    effective = _strip_stamp_boilerplate(raw)
    char_count = len(effective.strip())
    blocks = _layout_blocks(layout)
    table_chars = _table_block_char_counts(blocks)

    # 1) blank：剔除套话后一个可见字符都没有，且版面里也没有任何块。
    #    为什么要求「无 layout 块」：扫描件页若解析器给了块，它其实是一张图或一张
    #    空表，按空白页处理会把图纸吞掉；那种情况属于 graphic。
    if char_count == 0 and not blocks:
        return PageQuality(page_no, char_count, "blank", "空白页", False)

    # 证件识别只在 sparse / graphic 里用得上（见模块注释）；同步算一次，给两个分支共用。
    doc_hint = detect_doc_hint(effective)

    # 2a) graphic 主判据：有 table 块，但没有一个 table 块装得下内容（<50 字）。
    #     真实数据：p147 宗地图 table 块 6 字；p8 明细表 587 字、p52 流水 10806 字。
    #     「有表格结构、无表格内容」= 大图形被 MinerU 当成了 table 块。
    if table_chars and max(table_chars) < _TABLE_EMPTY_MAX_CHARS:
        return _graphic_page(page_no, char_count, "表格", blocks, doc_hint, effective)

    # 2b) graphic 备用判据（只在没有 table 块时）：字极少（<60）且凑不出成句的中文。
    #     p148 平面图：image 块 + 46 字图注，中文被数字切断。
    #     为什么不能放宽到 60 字以上：p116 合同首页 71 字、7 个 text 块，同样凑不出
    #     成句中文，但它是真实首页，应当只提示 sparse。
    if not table_chars and char_count < _GRAPHIC_MAX_CHARS and not _has_cn_sentence(effective):
        return _graphic_page(page_no, char_count, "文本", blocks, doc_hint, effective)

    # 2c) graphic 版面判据（同样只在没有 table 块时）：有 image 块 + 有效字符 <60。
    #     补的是 2b 够不到的形态——p148 平面图 ``[image 0, text 0, text 31, text 15]``，
    #     那 31/15 字是「已核对与原件相符」这类印章套话，剔除后有效字符只有 27。
    #     为什么必须「无 table 块」：p8 明细表 table 587 字 + 2 个 image 块，有 table
    #     时以 table 字数（2a）为准，image 块不能把它拉回图形页。
    #     为什么仍卡 60 字：p116 合同首页 71 字、无 image 块，两道都好地挡住；
    #     有 image + 真正文的页（如带 logo 的通知）也不会被误判。
    #     为什么还要排除业务字段标签（``_has_business_label``）：p23 身份证页
    #     ``[image 0, text 13, text 31]`` 与 p148 平面图在块形状和字数上完全同类
    #     （都无 table、都有 image、都远低于 60 字），只看形状必然把身份证也判成图纸。
    #     两者唯一的分界在内容：身份证剩「居民身份证」，平面图剔除套话后只剩乱码。
    if (
        not table_chars
        and char_count < _GRAPHIC_MAX_CHARS
        and _has_image_block(blocks)
        and not _has_business_label(effective)
    ):
        return _graphic_page(page_no, char_count, "图片", blocks, doc_hint, effective)

    # 3) sparse：<200 字。内容是真的，但不足以自证是什么材料——封面、证件
    #    （p23 身份证 45 字）、合同首页（p116 71 字）都落在这里。有字可读，
    #    律师看 Markdown 就能判断，所以不强制翻原图。
    if char_count < _SPARSE_MAX_CHARS:
        reason = describe_doc_page(doc_hint, effective, char_count=char_count) if doc_hint else _SPARSE_REASON
        return PageQuality(page_no, char_count, "sparse", reason, False, doc_hint)

    # 4) text：>=200 字，按正常文本页处理，不给任何提示。依据是实测：正文页
    #    1000–6000 字与几十字的碎片页之间有明显空档，200 落在空档里，正常页不受打扰。
    #    p8（617 字）、p52（10832 字）都走这里——它们是真表格/真流水。
    return PageQuality(page_no, char_count, "text", "正常文本页", False)


def _strip_stamp_boilerplate(text: str) -> str:
    """剔除跨页重复的印章/核对套话，避免它们伪装成「这一页有成句中文」。"""
    return _STAMP_BOILERPLATE_RE.sub(" ", text)


def _layout_blocks(layout: dict | None) -> list[dict[str, Any]]:
    """取 layout 里的块列表；结构不对就当没有版面（宁可少判，不猜）。"""
    if not isinstance(layout, dict):
        return []
    blocks = layout.get("blocks")
    if not isinstance(blocks, list):
        return []
    # 只保留 dict（非 dict 的块读不出 type，留着只会让后续判定多一层防御）
    return [block for block in blocks if isinstance(block, dict)]


def _block_type(block: dict[str, Any]) -> str:
    """块类型统一小写比较：MinerU 给 ``image``，Textin 给 ``Inline_Object``。"""
    return str(block.get("type") or "").strip().lower()


def _table_block_char_counts(blocks: list[dict[str, Any]]) -> list[int]:
    """每个 table 块的文本字数（已去掉空白）。

    块文本优先取 ``text``；MinerU 的表格正文也可能落在 ``table_body``（HTML）里，
    两者都取不到才算 0 字——这正好是「有表格结构、无表格内容」的信号。
    """
    counts: list[int] = []
    for block in blocks:
        if _block_type(block) not in _TABLE_BLOCK_TYPES:
            continue
        content = " ".join(str(block.get(key) or "") for key in ("text", "table_body"))
        counts.append(len("".join(content.split())))
    return counts


def _has_business_label(text: str) -> bool:
    """有效文本里是否出现业务字段标签（证件/笔录/单据的特征词）。

    b2 靠它区分「证件页」和「图纸页」——见 ``_B2_FIELD_LABEL_RE`` 的收敛说明。
    """
    return bool(_B2_FIELD_LABEL_RE.search(text))


def _has_image_block(blocks: list[dict[str, Any]]) -> bool:
    """版面里是否有 image 类块（只看有/无，不参与 2a 的表格判定）。"""
    return any(_block_type(block) in _IMAGE_BLOCK_TYPES for block in blocks)


def _graphic_reason(basis: str, blocks: list[dict[str, Any]]) -> str:
    """图形页文案；有 image 块就补一句「含图片」，帮律师定位要看什么。"""
    if _has_image_block(blocks):
        return f"疑似图形页（图纸/印章/照片，含图片块·判定依据：{basis}），请核对原图"
    return "疑似图形页（图纸/印章/照片），请核对原图"


def _graphic_page(
    page_no: int,
    char_count: int,
    basis: str,
    blocks: list[dict[str, Any]],
    doc_hint: str | None,
    text: str,
) -> PageQuality:
    """图形页画像：认得出是证件就按证件说（缺哪几个字段），否则给通用图纸文案。

    为什么证件文案要盖过「疑似图形页」：p147 宗地图被标成图形页是**有用**的提示，
    但同样判成图形页的身份证复印件（p42 满页乱码），律师需要知道的是「身份证号没读到」，
    而不是「这可能是图纸」。判定 kind 不变，只换一句更具体的 reason。
    """
    if doc_hint:
        reason = describe_doc_page(doc_hint, text, char_count=char_count)
        return PageQuality(page_no, char_count, "graphic", reason, True, doc_hint)
    return PageQuality(page_no, char_count, "graphic", _graphic_reason(basis, blocks), True)


def _has_cn_sentence(text: str) -> bool:
    """文本里是否有「成句的中文」：至少 1 段 6 字以上的连续中文。

    这是把 p147 宗地图（``宗地图`` 3 字、``面积 12.35 平方米`` 被数字切断）和
    p116 合同首页（71 字，含成句标题）分开的那把尺子。字段密集页先按字段标签切开
    再数：``姓名 张三 性别 男`` 的中文被标签和空格切碎，本就不该算成句，但也不能
    反过来让整段住址（20+ 字连写）冒充一句叙述。
    """
    if len(_FIELD_LABEL_RE.findall(text)) >= _FIELD_RUN_MIN:
        text = " ".join(_FIELD_VALUE_RE.findall(text))
    return bool(_CN_RUN_RE.search(text))
