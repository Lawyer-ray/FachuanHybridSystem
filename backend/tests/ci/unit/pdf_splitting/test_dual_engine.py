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
    """只差 Markdown 标记（# / * / 空白）→ 0 条：那是排版，不是认错字。

    ⚠️ 这里**不放**表格行。表格行（``| a | b |``）不参与逐字比对，会被行切分直接丢掉，
    表格的用例见 ``test_table_rows_are_not_compared_char_by_char``。
    """
    mineru = _render(["# 借款合同", "张三丰 李四 王五", "示例机构"])
    vl = _render(["## 借款合同", "张三丰  李四   王五", "**示例机构**"])

    result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

    assert result == []


def test_table_rows_are_not_compared_char_by_char() -> None:
    """表格内容**不参与**逐字比对：两边表格形态根本不同，逐字比对只会造 high 噪声。

    真实形态（这正是本次要修的问题）：

    · MinerU 的表格块是一整行——HTML 去标签 + 空白折叠，动辄 1000+ 字符；
    · PaddleOCR-VL 的表格是多行 GFM markdown，每行 ``|`` 分隔单元格。

    同一张表在两边必然整表判成 ``replace``，并且相似度够高 → 报 **high**。修复前
    表格块 ``text`` 恒为空、两边都被跳过；``parsed.text`` 开始含表格内容后若不同时
    堵住，每张表一条 high，真错字就淹了。所以这里要求：一张表都不报。
    """
    # MinerU：一整行的整表（空白已折叠、无换行、无 | 分隔）
    mineru_table_row = "客户名称 某某公司 保证人 张三丰 借款金额 1000000 借款期限 12个月 利率 4.35%"
    mineru = _render([mineru_table_row])
    # VL：同一张表的多行 markdown
    vl = _render(
        [
            "| 客户名称 | 某某公司 |",
            "| --- | --- |",
            "| 保证人 | 张三丰 |",
            "| 借款金额 | 1000000 |",
            "| 借款期限 | 12个月 |",
            "| 利率 | 4.35% |",
        ]
    )

    result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

    assert result == []


def test_html_table_block_is_never_reported() -> None:
    """VL 有时把整表输出成 ``<table>``：这种行同样算表格行，不参与比对。"""
    mineru = _render(["| 姓名 | 金额 |", "| --- | --- |", "| 张三丰 | 1000 |"])
    vl = _render(["<table><tr><td>姓名</td><td>金额</td></tr><tr><td>张三丰</td><td>1000</td></tr></table>"])

    assert compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}}) == []


def test_pipe_inside_plain_sentence_is_still_compared() -> None:
    """反例：正文里偶尔出现一个 ``|`` 不能当表格行——那会整片丢正文，才是真漏数据。"""
    mineru = _render([f"姓名：张三丰 身份证号：{FAKE_ID_CARD}"])
    vl = _render([f"姓名：张三半 | 身份证号：{FAKE_ID_CARD}"])

    result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

    assert len(result) == 1
    assert result[0].anchor_hit is True
    assert result[0].severity == SEVERITY_HIGH


def test_real_name_typo_still_detected_beside_tables() -> None:
    """关键回归：表格不参与比对，但真正的**人名错字**必须照旧被检出。

    数据虚构，形态照真实卷宗：MinerU 认成「曾某某」（正确），VL 认成「曾某木」（错字），
    姓名行就在表格下面。表格不该刷分歧，也不该把邻近的真错字挤掉——否则这次修复
    就是「把静默漏数据换成静默误判」：每张表一条 high，律师反而看不见人名错。
    """
    id_line = f"身份证号：{FAKE_ID_CARD}"
    body = ["借款人按合同约定用途使用借款资金、按期归还本息", "以上信息经核对无误"]
    # MinerU：整张表压成**一行**（HTML 去标签 + 空白折叠）；VL：同一张表是**多行** markdown。
    mineru_page = _render([f"姓名：曾某某 {id_line}", "客户名称 某某银行 借款金额 1000000 借款期限 12个月", *body])
    vl_page = _render(
        [
            "| 客户名称 | 某某银行 |",
            "| 借款金额 | 1000000 |",
            "| 借款期限 | 12个月 |",
            f"姓名：曾某木 {id_line}",
            *body,
        ]
    )

    result = compare_pages({ENGINE_MINERU: {1: mineru_page}, ENGINE_PADDLEOCR_VL: {1: vl_page}})

    # 只有那一条人名分歧：表格一条都不报
    assert len(result) == 1
    item = result[0]
    assert item.kind == KIND_CHAR
    # 姓名行和身份证号写在同一行，属于「绑定到具体人」的锚点邻域 → high
    assert item.anchor_hit is True
    assert item.severity == SEVERITY_HIGH
    assert {variant.text for variant in item.variants} == {
        f"姓名：曾某某 {id_line}",
        f"姓名：曾某木 {id_line}",
    }


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


class TestPresentationOnlyDiffIsLow:
    """严重度校准：差异只剩标点/装饰符时降 low，实质差异一律不降。

    真实基线（164 页银行档案，332 条分歧）：high 233 条里有 20 条两侧的字与数字
    **完全一样**，差的只是句末句点、逗号、冒号、``▲`` 项目符号重复、``/`` 残笔。
    律师面对 233 条 high 会告警疲劳，真错字被淹掉。

    但「差异是标点」不等于「差异是排版」：``146.75`` vs ``14675`` 也差一个句点，
    那是小数点——金额差一百倍。所以判据带数字夹逼守卫，且刻意不把勾选框/运算符
    当呈现符（``☒仲裁`` vs ``☑诉讼`` 是意思表示分歧）。
    """

    def test_fullwidth_halfwidth_colon_only_is_not_reported_at_all(self) -> None:
        """仅全角/半角冒号差异 → 归一化后相等，整条不报（比 low 更安静）。

        这是既有契约（``test_fullwidth_and_halfwidth_punctuation_produce_nothing``），
        校准严重度**不改**它：能归一化掉的差异不该占用清单条目。这里额外钉死
        「绝不能是 high/medium」，防止将来有人把归一化判据放宽成报 low 时顺手抬级。
        """
        mineru = _render(["借款人：测试甲", "保证人：测试乙"])
        vl = _render(["借款人:测试甲", "保证人:测试乙"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert result == []
        assert not [item for item in result if item.severity in {SEVERITY_HIGH, SEVERITY_MEDIUM}]

    def test_sentence_final_period_diff_is_low(self) -> None:
        """句末句点一侧有一侧无 → low（字与数字全同）。"""
        mineru = _render(["借款人应按约定用途使用借款资金。"])
        vl = _render(["借款人应按约定用途使用借款资金"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert len(result) == 1
        assert result[0].severity == SEVERITY_LOW
        assert result[0].kind == KIND_LINE

    def test_colon_vs_period_after_label_is_low_char(self) -> None:
        """字段标签后 ``:`` vs ``.`` → 仍是单字差异，但降 low。"""
        mineru = _render(["登记号:123"])
        vl = _render(["登记号.123"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert len(result) == 1
        assert result[0].kind == KIND_CHAR
        assert result[0].severity == SEVERITY_LOW

    def test_decorative_bullet_duplication_is_low(self) -> None:
        """``▲▲`` vs ``▲``：银行合同用它标条款，重复一个不改语义 → low。"""
        mineru = _render(["▲▲借款人应按期归还本息"])
        vl = _render(["▲借款人应按期归还本息"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert len(result) == 1
        assert result[0].severity == SEVERITY_LOW

    def test_presentation_only_diff_stays_low_even_near_anchor(self) -> None:
        """账号本身一字未变、只少了个冒号 → 锚点也不能把它抬回 high。"""
        account = "6200000000000000000"
        mineru = _render([f"账号:{account}"])
        vl = _render([f"账号{account}"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert len(result) == 1
        assert result[0].anchor_hit is True
        assert result[0].severity == SEVERITY_LOW

    def test_decimal_point_diff_stays_high(self) -> None:
        """``146.75`` vs ``14675``：差的是小数点，金额差一百倍 → 必须仍 high。"""
        mineru = _render(["逾期本金146.75元"])
        vl = _render(["逾期本金14675元"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert len(result) == 1
        assert result[0].severity == SEVERITY_HIGH

    def test_thousands_separator_diff_stays_high(self) -> None:
        """``1,000`` vs ``1000``：千分位被数字夹逼，同样不许降级。"""
        mineru = _render(["借款金额1,000元"])
        vl = _render(["借款金额1000元"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert len(result) == 1
        assert result[0].severity == SEVERITY_HIGH

    def test_share_fraction_slash_diff_stays_high(self) -> None:
        """``1/2`` vs ``12``：共有份额的斜线被数字夹逼，不是排版。"""
        mineru = _render(["共有份额1/2"])
        vl = _render(["共有份额12"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert len(result) == 1
        assert result[0].severity == SEVERITY_HIGH

    def test_checkbox_state_diff_near_anchor_stays_high(self) -> None:
        """``☒`` vs ``☑``：勾选态是意思表示（仲裁/诉讼二选一），不许当呈现符。"""
        mineru = _render([f"争议解决☒仲裁 身份证号{FAKE_ID_CARD}"])
        vl = _render([f"争议解决☑仲裁 身份证号{FAKE_ID_CARD}"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert len(result) == 1
        assert result[0].severity == SEVERITY_HIGH

    def test_formula_operator_diff_stays_high(self) -> None:
        """利息公式里的 ``×`` 一侧被漏认 → 运算符不是装饰符，仍 high。"""
        mineru = _render(["利息本金×利率×期限"])
        vl = _render(["利息本金利率期限"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert len(result) == 1
        assert result[0].severity == SEVERITY_HIGH

    def test_percent_sign_diff_stays_high(self) -> None:
        """``4.35%`` vs ``4.35``：百分号是单位，丢了就不知道是利率还是倍数。"""
        mineru = _render(["年利率4.35%"])
        vl = _render(["年利率4.35"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert len(result) == 1
        assert result[0].severity == SEVERITY_HIGH

    def test_real_name_diff_not_masked_by_punctuation_noise(self) -> None:
        """同一行里既有全半角标点差异又有真人名错字 → 仍按人名错字定级（high）。

        这是校准最大的风险：把「整行有标点差异」当成「整行只是排版差异」，
        真错字就被静默降级。判据必须逐字符看差异，不能按行整体印象判。
        """
        mineru = _render([f"借款人：测试甲，身份证号：{FAKE_ID_CARD}"])
        vl = _render([f"借款人:测试丙,身份证号:{FAKE_ID_CARD}"])

        result = compare_pages({ENGINE_MINERU: {1: mineru}, ENGINE_PADDLEOCR_VL: {1: vl}})

        assert len(result) == 1
        assert result[0].kind == KIND_CHAR
        assert result[0].severity == SEVERITY_HIGH
        assert result[0].anchor_hit is True
