"""证件/材料的类型识别 + 关键字段缺失检测：把「内容较少」换成律师看得懂的一句话。

## 为什么需要这一层

页面质量画像（``page_quality``）只会说「内容较少，可能是封面/证件/表单，建议核对」。
576 实测里这句话恰好落在最要紧的两页上：

| 页 | Markdown 实测 | 真相 |
|---|---|---|
| p23 | 45 字，只有「中华人民共和国 / 居民身份证 / 已核对与原件相符 / 经办人：…」 | 身份证，**姓名/身份证号/住址全丢** |
| p42 | 343 字，但满是乱码（SINGCMIN / SIEAYOUO / DIEGYCUO） | 身份证复印件，同样读不出字段 |

律师看到「内容较少」并不知道自己最关心的身份证号根本没读出来。所以这一层多做两件事：
**认出这页是什么证件**，再**点名哪几个字段没读到**——他看一行字就知道要翻原图抄什么。

``这页是身份证，但姓名 / 身份证号 / 住址 均未读出，请人工录入或核对原图``

## 为什么关键词而不是模型

判据必须能在取字阶段对 164 页逐页跑、还要能被 pipeline / job API / 前端复核入口
反复调用，所以纯函数、只用 stdlib、无 Django 依赖。证件的版式关键词（「居民身份证」
「常住人口登记卡」「不动产权证书」）本身就是最稳定的信号，比 OCR 置信度可靠。

## 为什么只在 sparse / graphic 时用

正常文本页（>=200 字）不需要「这是什么证件」的提示：内容读全了，律师自己看得见。
多给一句提示只会稀释真正需要翻原图的那几页。调用方负责这个门（见 ``page_quality``）。
"""

from __future__ import annotations

import re

#: 材料类型 → 该类型的标题关键词。按**顺序**匹配，先命中者胜出；顺序即特异性：
#: 「居民身份证」必须先于「身份证」类泛词，「不动产权证书」先于「证书」。
#: 实测 p23 的标题块就是「中华人民共和国 / 居民身份证」。
_DOC_KEYWORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("id_card", re.compile(r"居民身份证|公民身份号码|身份证复印")),
    ("household", re.compile(r"户口簿|户口本|常住人口登记卡")),
    ("marriage", re.compile(r"结婚证")),
    ("property_cert", re.compile(r"不动产权证书|不动产权证")),
    ("license", re.compile(r"营业执照")),
    ("income_proof", re.compile(r"收入证明")),
)

#: 每种材料的**预期字段**：(字段名, 命中就说明读到了的正则)。
#:
#: 正则刻意宽松——只要页面上出现过「姓名」两个字就算读到，不做「姓名后面必须跟
#: 2～4 个汉字」的强校验。理由：这一层的产出是**提示**而不是校验，宁可说「读到过」
#: 也不要把「读到了但被 OCR 拆行」误报成缺失，否则律师会因为频繁误报而无视提示。
#: 身份证号取 18 位形态（末位可以是 X）：15 位旧号已停用，不纳入。
_EXPECTED_FIELDS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "id_card": (
        ("姓名", re.compile(r"姓\s*名")),
        ("身份证号", re.compile(r"\d{17}[\dXx]")),
        ("住址", re.compile(r"住\s*址|地址")),
    ),
    "household": (
        ("姓名", re.compile(r"姓\s*名")),
        ("身份证号", re.compile(r"\d{17}[\dXx]")),
    ),
    "property_cert": (
        ("权利人", re.compile(r"权利人")),
        ("权证号", re.compile(r"不动产单元号|编号")),
    ),
    "marriage": (("姓名", re.compile(r"姓\s*名")),),
}

#: 材料类型 → 一句话说明。给律师看的，不写「可能是」——关键词命中就是要说死，
#: 说不死的地方（没有关键词）走 ``None``，不给提示。
_DOC_LABELS: dict[str, str] = {
    "id_card": "身份证",
    "household": "户口簿",
    "marriage": "结婚证",
    "property_cert": "不动产权证",
    "license": "营业执照",
    "income_proof": "收入证明",
}


def detect_doc_hint(text: str) -> str | None:
    """认出这页是什么材料；认不出返回 ``None``（不猜）。

    只给一个 ``str`` 而不是 ``PageQuality``：类型识别与页面质量判定是两件事，
    后者还要看字数/版面块，混在一个函数里会让两边都难改。
    """
    for doc_hint, pattern in _DOC_KEYWORDS:
        if pattern.search(text):
            return doc_hint
    return None


def doc_hint_label(doc_hint: str) -> str:
    """材料类型的中文名（``id_card`` → 「身份证」）。

    未知类型原样返回：调用方传了没登记的类型时至少不会崩，也不会凭空造一个中文名。
    """
    return _DOC_LABELS.get(doc_hint, doc_hint)


def missing_expected_fields(doc_hint: str, text: str) -> list[str]:
    """该材料应当有、但这页一个都没读到的字段名；没有预期清单的材料返回空表。"""
    return [name for name, pattern in _EXPECTED_FIELDS.get(doc_hint, ()) if not pattern.search(text)]


def describe_doc_page(doc_hint: str, text: str, *, char_count: int) -> str:
    """证件页的提示语：先说是哪份材料，再点名缺了哪些字段。

    两种形态（``char_count`` 是剔除印章套话后的有效字数，与判据口径一致）：

    - 全部预期字段都没读到 → 「这页是身份证，但姓名 / 身份证号 / 住址 均未读出，
      请人工录入或核对原图」（p23 实测形态：45 字，字段全丢）
    - 只缺一部分 → 「这页是身份证（有效 45 字），但住址未读出，请核对原图」

    一个字都没有的证件页（``char_count == 0``）**不列举字段**：那时缺的是整页，
    说「字段均未读出」反而把范围说小了。
    """
    label = doc_hint_label(doc_hint)
    expected = [name for name, _ in _EXPECTED_FIELDS.get(doc_hint, ())]
    missing = missing_expected_fields(doc_hint, text)

    if char_count == 0:
        return f"这页是{label}，但文本未读出，请核对原图"
    if not missing:
        return f"这页是{label}（有效 {char_count} 字），字段是否完整请核对原图"
    if len(missing) == len(expected):
        return f"这页是{label}，但{' / '.join(missing)} 均未读出，请人工录入或核对原图"
    return f"这页是{label}（有效 {char_count} 字），但{' / '.join(missing)}未读出，请核对原图"
