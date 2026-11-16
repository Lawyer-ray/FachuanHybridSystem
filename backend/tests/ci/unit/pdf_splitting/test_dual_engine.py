"""双引擎交叉校验（``compare_pages``）的判据单测。

全部测试数据都是虚构的：张三丰 / 李四 / 王五 / 示例机构 / 110101199001011234
（明显假号）。真实卷宗里的姓名与身份证号不得出现在测试里。

对应契约：只报分歧、不投票、不产出「最终文本」；排版差异（Markdown 标记、
全半角标点）不算分歧；身份证号邻域的单字分歧升级为 high。

⚠️ 本文件只放 ``compare_pages`` 的判据用例。引擎定位归一化（EngineBlock /
normalize_* / link_*）的用例在 ``test_dual_engine_blocks.py``——两者由不同实现
负责，混在一个文件里会互相覆盖。

⚠️ 「某页只有一个引擎有内容」**不产生** missing（见 ``test_single_engine_returns_empty``
的说明）：那是正常降级路径，逐页报 missing 会把真分歧淹掉。missing 只在
**同一页内**一个引擎整行多出/缺失时出现。
"""

from __future__ import annotations

from apps.pdf_splitting.services.split.dual_engine import (
    ENGINE_MINERU,
    ENGINE_PADDLEOCR_VL,
    ENGINE_TEXTIN,
    KIND_CHAR,
    KIND_LINE,
    KIND_MISSING,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    EngineDisagreement,
    compare_pages,
)

#: 虚构身份证号（110101 = 示例行政区划，证件号明显是假号）
FAKE_ID_CARD = "110101199001011234"


def _render(lines: list[str]) -> str:
    return "\n".join(lines)


def test_identical_engines_produce_no_disagreement() -> None:
    """两引擎逐字一致 → 0 条分歧（一致不是「没问题」的证明，但也没东西可报）。"""
    text = _render([f"第{page_no}页 张三丰 向 示例机构 借款" for page_no in range(1, 6)])
    pages = dict.fromkeys(range(1, 6), text)

    result = compare_pages({ENGINE_MINERU: pages, ENGINE_PADDLEOCR_VL: pages})

    assert result == []


def test_single_char_difference_is_medium_char() -> None:
    """同一行只差一个字（无锚点邻域）→ kind=char / severity=medium。"""
    mineru = _render(["借款人：张三丰", "保证人：李四"])
    vl = _render(["借款人：张三半", "保证人：李四"])

    result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

    assert len(result) == 1
    item = result[0]
    assert item.kind == KIND_CHAR
    assert item.severity == SEVERITY_MEDIUM
    assert item.page_no == 1
    assert item.anchor_hit is False
    assert 0.0 < item.similarity < 1.0
    assert {variant.text for variant in item.variants} == {"借款人：张三丰", "借款人：张三半"}


def test_single_char_difference_near_id_card_is_high() -> None:
    """单字分歧的邻域里有身份证号 → severity=high，anchor_hit=True。

    依据：姓名与身份证号在表单里常是相邻两格，这种位置错一个字就直接绑定到
    错误的自然人，不能和普通正文一样淹在 medium 里。
    """
    mineru = _render([f"姓名：张三丰 身份证号：{FAKE_ID_CARD}"])
    vl = _render([f"姓名：张三半 身份证号：{FAKE_ID_CARD}"])

    result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

    assert len(result) == 1
    item = result[0]
    assert item.kind == KIND_CHAR
    assert item.severity == SEVERITY_HIGH
    assert item.anchor_hit is True


def test_multiple_char_difference_is_high_line() -> None:
    """同一行差了两个以上字但整体相似 → kind=line / severity=high。"""
    mineru = _render(["借款人王五向示例机构借款人民币一万元"])
    vl = _render(["借款人李四向示例机构借款人民币一万元"])

    result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

    assert len(result) == 1
    item = result[0]
    assert item.kind == KIND_LINE
    assert item.severity == SEVERITY_HIGH
    assert item.similarity >= 0.5
    assert {variant.text for variant in item.variants} == {
        "借款人王五向示例机构借款人民币一万元",
        "借款人李四向示例机构借款人民币一万元",
    }


def test_markdown_markers_only_produce_nothing() -> None:
    """只差 Markdown 标记（# / | / * / 表格分隔行）→ 0 条：那是排版，不是认错字。"""
    mineru = _render(["# 借款合同", "张三丰 李四 王五", "示例机构"])
    vl = _render(
        [
            "| 姓名 | 姓名 | 姓名 |",
            "| --- | --- | --- |",
            "| 张三丰 | 李四 | 王五 |",
            "**示例机构**",
        ]
    )

    result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

    assert result == []


def test_fullwidth_and_halfwidth_punctuation_produce_nothing() -> None:
    """只差全半角标点（，vs , / ：vs : / （）vs ()）→ 0 条。"""
    mineru = _render(["借款人：张三丰，保证人：李四（王五）"])
    vl = _render(["借款人:张三丰,保证人:李四(王五)"])

    result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

    assert result == []


def test_extra_line_in_one_engine_is_low_missing() -> None:
    """一个引擎整行多出（另一个没有）→ kind=missing / severity=low。

    low 的理由：这多数是版面切分差异（VL 把这段并进上一段了），不是漏读。
    """
    mineru = _render(["借款人：张三丰", "保证人：李四", "示例机构盖章"])
    vl = _render(["借款人：张三丰", "保证人：李四"])

    result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

    assert len(result) == 1
    item = result[0]
    assert item.kind == KIND_MISSING
    assert item.severity == SEVERITY_LOW
    assert item.similarity == 0.0
    texts = {variant.engine: variant.text for variant in item.variants}
    assert texts[ENGINE_MINERU] == "示例机构盖章"
    assert texts[ENGINE_PADDLEOCR_VL] == ""


def test_three_engines_report_each_disagreement_once() -> None:
    """三引擎同一处（同一行两种写法）只报一条，不按引擎对重复刷。"""
    mineru = _render(["借款人：张三丰"])
    vl = _render(["借款人：张三半"])
    textin = _render(["借款人：张三半"])

    result = compare_pages(
        {
            ENGINE_MINERU: {1: mineru},
            ENGINE_PADDLEOCR_VL: {1: vl},
            ENGINE_TEXTIN: {1: textin},
        }
    )

    assert len(result) == 1
    item = result[0]
    assert item.kind == KIND_CHAR
    # 去重键是 {kind, 归一化后的变体集合}：三引擎那两种写法只产生一组
    assert {variant.text for variant in item.variants} == {"借款人：张三丰", "借款人：张三半"}


def test_single_engine_returns_empty() -> None:
    """只有一个引擎 → 没有可比对象，返回空（不是「全页没问题」）。"""
    only = {ENGINE_MINERU: {1: _render(["借款人：张三丰"])}}

    assert compare_pages(only) == []
    # 另一个引擎给了空页字典，同样不足以比对
    assert compare_pages({ENGINE_MINERU: {1: "张三丰"}, ENGINE_PADDLEOCR_VL: {}}) == []
    # 某页只有一侧有内容（另一侧这页漏了/跳过了）也**不报 missing**：
    # 单引擎覆盖单页是正常降级路径，逐页报 low 会把真分歧淹掉。
    # missing 只在**同一页内**一个引擎整行多出/缺失时才出现（见上面的用例）。
    assert (
        compare_pages(
            {ENGINE_MINERU: {1: "借款人：张三丰", 2: "示例机构盖章"}, ENGINE_PADDLEOCR_VL: {1: "借款人：张三丰"}}
        )
        == []
    )


def test_min_severity_filters_lower_levels() -> None:
    """min_severity 生效：medium 门槛滤掉 low 的 missing，high 门槛再滤掉 medium。"""
    mineru = _render(["借款人：张三丰", "保证人：李四", "示例机构盖章"])
    vl = _render(["借款人：张三半", "保证人：李四"])

    engine_pages = {ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}}

    all_items = compare_pages(engine_pages)
    assert {item.severity for item in all_items} == {SEVERITY_MEDIUM, SEVERITY_LOW}

    medium_and_up = compare_pages(engine_pages, min_severity=SEVERITY_MEDIUM)
    assert [item.severity for item in medium_and_up] == [SEVERITY_MEDIUM]

    high_only = compare_pages(engine_pages, min_severity=SEVERITY_HIGH)
    assert high_only == []


def test_empty_text_and_empty_dict_do_not_crash() -> None:
    """空文本 / 空 dict / 全是空白的页：不崩，也不报分歧。"""
    assert compare_pages({}) == []
    assert compare_pages({ENGINE_MINERU: {}, ENGINE_PADDLEOCR_VL: {}}) == []
    assert compare_pages({ENGINE_MINERU: {1: ""}, ENGINE_PADDLEOCR_VL: {1: ""}}) == []
    assert compare_pages({ENGINE_MINERU: {1: "   \n\n"}, ENGINE_PADDLEOCR_VL: {1: "  "}}) == []
    # 一侧有内容、一侧空白：不算分歧（单引擎页是正常降级路径）
    assert compare_pages({ENGINE_MINERU: {1: "借款人：张三丰"}, ENGINE_PADDLEOCR_VL: {1: ""}}) == []


def test_results_sorted_by_severity_high_first() -> None:
    """排序：severity 高的在前；同级内按页码升序。

    三种等级必须都出现在**同一页有内容的两引擎**之间，否则测不到排序：
    · 第 1 页差 1 字 → medium
    · 第 2 页 MinerU 多出整整一行 → low missing（同页行级差异，不是整页缺失）
    · 第 3 页锚点邻域差 1 字 → high
    """
    mineru_pages = {
        1: _render(["借款人：张三丰"]),
        2: _render(["保证人：李四", "示例机构盖章"]),
        3: _render([f"姓名：张三丰 身份证号：{FAKE_ID_CARD}"]),
    }
    vl_pages = {
        1: _render(["借款人：张三半"]),
        2: _render(["保证人：李四"]),
        3: _render([f"姓名：张三半 身份证号：{FAKE_ID_CARD}"]),
    }

    result = compare_pages({ENGINE_MINERU: mineru_pages, ENGINE_PADDLEOCR_VL: vl_pages})

    assert [item.severity for item in result] == [SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW]
    assert [item.page_no for item in result] == [3, 1, 2]
    assert all(isinstance(item, EngineDisagreement) for item in result)


def test_truncate_decodes_literal_backslash_n() -> None:
    """字面量 ``\\n``（反斜杠 + n）必须解码成空格。

    PaddleOCR-VL 会把换行写进字符串时留下转义序列而不是真 0x0A，不转掉的话
    律师看到的是「逾期本金:\\n654.52元」，会以为那是识别出来的字符。
    实测 164 页卷宗的 12 条带此噪声的分歧**全部**被判成了 high。
    """
    from apps.pdf_splitting.services.split.dual_engine import _truncate

    assert _truncate("逾期本金:\\n654.52元") == "逾期本金: 654.52元"
    assert _truncate("甲\\t乙") == "甲 乙"
    # 正常文本不受影响
    assert _truncate("客户姓名：曾某某") == "客户姓名：曾某某"
