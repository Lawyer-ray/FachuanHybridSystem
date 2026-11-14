"""页面内容质量画像的单元测试（数据取自 576 真实版面块实测）。

真实背景：164 页银行卷宗里，p147 只有 6 字（宗地图）、p148 46 字（平面图），
文字少于 60 字的共 12 页（封面/身份证/图纸/盖章页）。这些页在 Markdown 里就是几行
零散字符，律师看不出那是图纸——而图纸恰恰是抵押案件的关键证据。

实测的每页块形态（类型, 字数）：

    p8   银行欠款明细表: table 587 + image 0 + image 0 + 若干短 text
    p23  身份证:         image 0 + text 13 + text 31
    p52  银行流水:       text 13 + 5 + 5 + table 10806 + header 6
    p116 合同首页:       7 个 text 块，共 71 字，有标题
    p147 宗地图:         table 6
    p148 平面图:         image 0 + text 0 + text 31 + text 15

所以每个 kind 都配正例和**反例**，反例专门用「看着像图形页的真表格 / 真证件」。
"""

from __future__ import annotations

import dataclasses

import pytest

from apps.pdf_splitting.services.split.page_quality import PageQuality, assess_page_quality


def _blocks(*specs: tuple[str, int]) -> dict:
    """按「(类型, 文本字数)」造一份 MinerU 形态的 layout。"""
    return {"blocks": [{"type": kind, "text": "文" * size} for kind, size in specs]}


#: 印章/核对套话：几乎每页都有，不剔除就会伪装成「这一页有成句中文」。
_STAMP = "已核对与原件相符  扫描件与留档资料相符  经办人：李四"

#: p116 合同首页形态：71 字、7 个 text 块、有标题，凑不出成句中文。
_CONTRACT_HEAD_TEXT = "个人购房借款" + "担保合同" * 12  # 6 + 60 = 66 字，全是短词拼接

#: p23 身份证形态：字段密集、句子少，且带 image 块（证件扫描件的边距图）。
_ID_CARD_TEXT = "姓名张三 性别男 民族汉\n住址某某省某某市\n公民身份号码 110101198001011234"

#: 200 字以上的正常正文页（合同条款）。
_BODY_TEXT = "5.4 借款人应在本合同签订后三十日内，向有关登记机关办理抵押登记手续，并将登记证明文件交由贷款人保管。" * 4

#: p23 **实测**形态：45 字，只有标题行 + 印章套话，姓名/身份证号/住址全丢。
#: 这是本功能要解决的原型——律师看到「内容较少」并不知道身份证号没读出来。
_P23_OCR_TEXT = "中华人民共和国\n居民身份证\n已核对与原件相符\n经办人：李四"

#: p42 身份证复印件形态：标题行读对了，但字段区被 OCR 认成一串字母乱码
#: （SINGCMIN / SIEAYOUO / DIEGYCUO），姓名/证号/住址**一个都没对**。
#: 乱码是虚构的字母串，姓名与证号也是虚构值。
_P42_GARBLED_TEXT = (
    "居民身份证复印件 中华人民共和国 居民身份证 "
    "姓名 张三 性别 男 民族 汉 住址 某某省某某市某某路1号 公民身份号码 110101199001011234 "
    + "SINGCMIN SIEAYOUO DIEGYCUO "
    * 4
)


class TestBlank:
    def test_empty_text_without_layout_is_blank(self) -> None:
        quality = assess_page_quality(page_no=1, text="")
        assert quality.kind == "blank"
        assert quality.char_count == 0
        assert quality.reason == "空白页"
        assert quality.needs_visual_review is False

    def test_whitespace_only_text_is_blank(self) -> None:
        quality = assess_page_quality(page_no=2, text="   \n\t\r\n  ")
        assert quality.kind == "blank"

    def test_stamp_boilerplate_only_is_blank(self) -> None:
        # 真实形态：整页只有一个盖章页的核对套话，剔除后没有有效内容
        quality = assess_page_quality(page_no=3, text=_STAMP)
        assert quality.kind == "blank"
        assert quality.char_count == 0

    def test_blocks_without_text_are_not_blank(self) -> None:
        # 反例：版面说有块（哪怕块文本为空），说明这页有结构，不能当空白页吞掉
        quality = assess_page_quality(page_no=4, text="", layout=_blocks(("text", 0)))
        assert quality.kind != "blank"

    def test_body_text_is_not_blank(self) -> None:
        # 反例：正常正文页绝不能落进空白页
        assert assess_page_quality(page_no=5, text=_BODY_TEXT).kind == "text"


class TestGraphic:
    def test_p147_land_map_table_with_no_content(self) -> None:
        # p147 实况：[('table', 6)] —— 大图形被 MinerU 当成 table 块，抽不出字
        quality = assess_page_quality(page_no=147, text="宗地图", layout=_blocks(("table", 6)))
        assert quality.kind == "graphic"
        assert "请核对原图" in quality.reason
        assert quality.needs_visual_review is True

    def test_p147_with_stamp_boilerplate(self) -> None:
        # 宗地图页也带核对套话，剔除后仍是图形页（套话不能把它「救」成文本页）
        quality = assess_page_quality(page_no=147, text=f"宗地图 {_STAMP}", layout=_blocks(("table", 6)))
        assert quality.kind == "graphic"

    def test_p148_plan_stamp_boilerplate_plus_garbled(self) -> None:
        # p148 实况：[('image',0), ('text',0), ('text',31), ('text',15)]，无 table 块。
        # 剔除套话后有效字符只剩乱码（OCR 把图上文字认成「变形机…赔償自」），
        # 一个业务字段标签都没有——靠 image 块才认得出是图纸。
        # 关键：不剔套话的话字数会撑过 60，这页会被静默放成 sparse。
        text = f"（平面图）{_STAMP} 变形机空间文西陽山有禁賣保的比動人賠償自"
        quality = assess_page_quality(
            page_no=148,
            text=text,
            layout=_blocks(("image", 0), ("text", 0), ("text", 31), ("text", 15)),
        )
        assert quality.kind == "graphic"
        assert quality.needs_visual_review is True
        # reason 里点名「含图片块」，帮律师知道要看的是图
        assert "含图片块" in quality.reason

    def test_image_block_with_real_text_over_60_is_not_graphic(self) -> None:
        # 反例：[('image',0), ('text',50), ('text',40)]，剔除套话后仍有 80+ 字真正文
        # （带 logo 的通知/合同首页）——有 image 块不等于只有图，字数门槛挡住
        body = "本行已依照监管要求对贷款用途进行核查，借款人应按合同约定用途使用借款资金。" * 2
        quality = assess_page_quality(
            page_no=149,
            text=f"{body} {_STAMP}",
            layout=_blocks(("image", 0), ("text", 50), ("text", 40)),
        )
        assert quality.char_count >= 60
        assert quality.kind != "graphic"
        assert quality.needs_visual_review is False

    def test_text_basis_without_layout(self) -> None:
        # 本地 OCR 没有版面：只靠「字极少 + 凑不出成句中文」
        assert assess_page_quality(page_no=149, text="平面图 1:500").kind == "graphic"

    def test_p8_real_table_is_not_graphic(self) -> None:
        # 反例（关键）：[table 587] + 2 个 image 块 —— 银行欠款明细表是真表格。
        # 「有 image 块」太常见（页眉 logo、印章、表格截图），不能判图形页。
        quality = assess_page_quality(
            page_no=8,
            text="欠款明细" * 150,  # 600 字
            layout=_blocks(("table", 587), ("image", 0), ("image", 0), ("text", 7)),
        )
        assert quality.kind == "text"
        assert quality.needs_visual_review is False

    def test_p52_bank_statement_is_not_graphic(self) -> None:
        # 反例：table 10806 字的真流水
        quality = assess_page_quality(
            page_no=52,
            text="流水" * 5000,
            layout=_blocks(("text", 13), ("text", 5), ("text", 5), ("table", 10806), ("header", 6)),
        )
        assert quality.kind == "text"

    def test_p116_contract_head_is_not_graphic(self) -> None:
        # 反例：[('text',6) x7] 共 71 字，无 image 块、凑不出成句中文——但它是合同首页，
        # 只能是 sparse。字数 71 > 60，2b/2c 两条图形判据都挡得住。
        quality = assess_page_quality(
            page_no=116,
            text=_CONTRACT_HEAD_TEXT,
            layout=_blocks(*[("text", 10)] * 7),
        )
        assert quality.kind == "sparse"

    def test_short_sentence_is_not_graphic(self) -> None:
        # 反例：34 字但确实在说人话（合同首行），不能因为字少就让人去翻原图
        quality = assess_page_quality(page_no=117, text="某某银行抵押贷款合同 借款人：张三。合同编号：2024年0001号。")
        assert quality.kind == "sparse"


class TestSparse:
    def test_p23_id_card_with_image_block(self) -> None:
        # 关键反例：p23 实况 [('image',0), ('text',13), ('text',31)]——与 p148 平面图
        # 在块形状、字数上完全同类（无 table、有 image、远低于 60 字），只看形状会把
        # 身份证判成「请核对原图」。分界在内容：这页剩「中华人民共和国居民身份证」。
        quality = assess_page_quality(
            page_no=23,
            text="中华人民共和国居民身份证张某某",
            layout=_blocks(("image", 0), ("text", 13), ("text", 31)),
        )
        assert quality.kind == "sparse"
        # 认得出是身份证就不再给泛泛的「内容较少」：这页剩下的只有标题行，
        # 姓名/身份证号/住址一个都没读到，提示必须点名这三个字段（见 doc_type.py）。
        assert quality.doc_hint == "id_card"
        assert "身份证" in quality.reason
        assert quality.needs_visual_review is False

    def test_p41_interview_record_with_image_block(self) -> None:
        # 关键反例：p41 面谈笔录 18 字 + image 块，同样不能判图形页（命中「面谈笔录」）
        quality = assess_page_quality(
            page_no=41,
            text="张某某罗向交通银行个人贷款面谈笔录表",
            layout=_blocks(("image", 0), ("text", 13), ("text", 31)),
        )
        assert quality.kind == "sparse"

    def test_id_card_text_with_image_block(self) -> None:
        # 反例：字段密集的身份证正文 + image 块，字数不足 60 也不能判图形页
        quality = assess_page_quality(
            page_no=24,
            text=_ID_CARD_TEXT,
            layout=_blocks(("image", 0), ("text", 13), ("text", 31)),
        )
        assert quality.kind == "sparse"

    def test_cover_page(self) -> None:
        quality = assess_page_quality(page_no=20, text="个人购房借款/担保合同\n某某银行某某支行\n2024年")
        assert quality.kind == "sparse"

    def test_boundary_60_chars_is_sparse(self) -> None:
        # 边界：恰好 60 字不进备用图形判据
        quality = assess_page_quality(page_no=22, text="抵" * 60)
        assert quality.char_count == 60
        assert quality.kind == "sparse"

    def test_id_card_without_layout_is_not_graphic(self) -> None:
        # 反例：同一条身份证文本，断行把字段拆开时不能因为字少判图形页
        quality = assess_page_quality(page_no=21, text=_ID_CARD_TEXT)
        assert quality.kind == "sparse"

    def test_blank_page_is_not_sparse(self) -> None:
        # 反例：0 字不是「内容较少」，是空白页——结论完全不同
        assert assess_page_quality(page_no=24, text="").kind == "blank"

    def test_body_text_is_not_sparse(self) -> None:
        # 反例：正常正文页不能落进 sparse，否则整份卷宗每页都提示「建议核对」
        assert assess_page_quality(page_no=25, text=_BODY_TEXT).kind == "text"


class TestText:
    def test_body_page_is_text(self) -> None:
        quality = assess_page_quality(page_no=30, text=_BODY_TEXT)
        assert quality.kind == "text"
        assert quality.reason == "正常文本页"
        assert quality.needs_visual_review is False

    def test_boundary_200_chars_is_text(self) -> None:
        quality = assess_page_quality(page_no=31, text="抵" * 200)
        assert quality.kind == "text"

    def test_199_chars_is_sparse(self) -> None:
        # 反例边界：199 与 200 差 1 字，不能判成正常正文
        assert assess_page_quality(page_no=32, text="抵" * 199).kind == "sparse"

    def test_sparse_page_is_not_text(self) -> None:
        # 反例：只有封面的短文本不能被当正常正文页，否则律师永远看不到提示
        assert assess_page_quality(page_no=33, text="个人购房借款/担保合同").kind != "text"


class TestContract:
    def test_result_is_frozen(self) -> None:
        quality = assess_page_quality(page_no=1, text="宗地图")
        assert isinstance(quality, PageQuality)
        # frozen dataclass：改字段会抛 FrozenInstanceError
        with pytest.raises(dataclasses.FrozenInstanceError):
            quality.kind = "text"  # type: ignore[misc]

    def test_page_no_is_passed_through(self) -> None:
        assert assess_page_quality(page_no=147, text="宗地图").page_no == 147

    def test_char_count_excludes_stamp_boilerplate(self) -> None:
        # 统计口径与判据一致：套话不算字数，否则「有效字符为 0」永远不成立
        quality = assess_page_quality(page_no=5, text=f"宗地图 {_STAMP}")
        assert quality.char_count == 3

    def test_broken_layout_is_ignored(self) -> None:
        # layout 结构不对（blocks 不是列表）时按无版面处理，不抛异常
        assert assess_page_quality(page_no=6, text="", layout={"blocks": "not-a-list"}).kind == "blank"

    def test_table_body_html_counts_as_table_content(self) -> None:
        # MinerU 的表格正文可能在 table_body 里，取不到才算「空表」
        layout = {"blocks": [{"type": "table", "text": "", "table_body": "<td>金额</td>" * 200}]}
        assert assess_page_quality(page_no=7, text=_BODY_TEXT, layout=layout).kind == "text"

    def test_table_type_is_case_insensitive(self) -> None:
        layout = {"blocks": [{"type": "Table", "text": ""}]}
        assert assess_page_quality(page_no=8, text="宗地图", layout=layout).kind == "graphic"


class TestDocHint:
    """证件识别 + 关键字段缺失：把「内容较少」换成律师看得懂的一句话。

    原痛点（576 实测）：p23 身份证 45 字、姓名/身份证号/住址全丢，律师看到的却是
    「内容较少，可能是封面/证件/表单」——他不知道自己最关心的身份证号根本没读出来。
    所以这里锁两件事：**认得出是什么材料**，且**缺的字段被点名**。
    测试数据一律虚构（张三/李四 + 全 1 结尾的样例号码），不对应任何真实证件。
    """

    def test_p23_身份证页点名缺哪三个字段(self) -> None:
        # p23 实况：45 字，只剩标题行 + 印章套话；姓名、身份证号、住址一个都没有
        quality = assess_page_quality(
            page_no=23,
            text=_P23_OCR_TEXT,
            layout=_blocks(("image", 0), ("text", 13), ("text", 31)),
        )
        assert quality.kind == "sparse"
        assert quality.doc_hint == "id_card"
        assert "身份证" in quality.reason
        assert "姓名" in quality.reason
        assert "身份证号" in quality.reason
        assert "住址" in quality.reason
        # 提示里必须有「去翻原图/人工录入」这条动作，否则律师知道缺了也不会补
        assert "核对原图" in quality.reason or "人工录入" in quality.reason

    def test_p42_乱码身份证复印件也要挂上证件提示(self) -> None:
        # p42 实况：343 字，正文满是乱码，律师看不清哪里是姓名哪里是证号。
        # 与 p23 的区别只在于它落进哪一档：只要不是正常文本页，doc_hint 与证件文案都得在，
        # 否则律师会以为自己在读一份普通文书。
        quality = assess_page_quality(page_no=42, text=_P42_GARBLED_TEXT)
        assert quality.kind in {"sparse", "graphic"}
        assert quality.doc_hint == "id_card"
        assert "身份证" in quality.reason
        assert "核对原图" in quality.reason

    def test_身份证字段齐全时只提醒核对不再说均未读出(self) -> None:
        # 反例：姓名/证号/住址都读到了，不能还说「均未读出」——那是假话
        quality = assess_page_quality(page_no=24, text=_ID_CARD_TEXT)
        assert quality.doc_hint == "id_card"
        assert "均未读出" not in quality.reason

    def test_户口簿与结婚证分别识别(self) -> None:
        assert assess_page_quality(page_no=60, text="常住人口登记卡\n姓名 王某某").doc_hint == "household"
        assert assess_page_quality(page_no=61, text="结婚证\n持证人 王某某").doc_hint == "marriage"

    def test_权证缺编号时点名权证号(self) -> None:
        # 权利人读到了、权证号没读到：提示里只能点名权证号，不能说「权利人也没有」
        quality = assess_page_quality(page_no=62, text="不动产权证书\n权利人 某某公司")
        assert quality.doc_hint == "property_cert"
        assert "权证号" in quality.reason
        assert "权利人" not in quality.reason.split("但", 1)[-1]

    def test_营业执照与收入证明只识别不给字段清单(self) -> None:
        license_page = assess_page_quality(page_no=63, text="营业执照\n统一社会信用代码 91AAAA")
        income_page = assess_page_quality(page_no=64, text="收入证明\n兹证明王某某")
        assert license_page.doc_hint == "license"
        assert income_page.doc_hint == "income_proof"
        # 没登记预期字段的材料只说是什么，不编造缺失清单
        assert "营业执照" in license_page.reason
        assert "未读出" not in license_page.reason

    def test_p8真表格不误报doc_hint(self) -> None:
        # 关键反例：617 字真表格里出现「身份证」类字样也不能挂 doc_hint——
        # 正常文本页不需要「这是什么证件」的提示，多一句话只会稀释真正的提示
        text = ("欠款明细 客户姓名 证件号码 " + "金额1234.56元 " * 40) + "身份证复印件存档"
        quality = assess_page_quality(
            page_no=8,
            text=text,
            layout=_blocks(("table", 587), ("image", 0), ("image", 0), ("text", 7)),
        )
        assert quality.kind == "text"
        assert quality.doc_hint is None
        assert quality.reason == "正常文本页"

    def test_正常文本页doc_hint为None(self) -> None:
        # 正文页即使提到「身份证」，也不该挂提示（kind=text）
        quality = assess_page_quality(page_no=30, text=_BODY_TEXT + "原件与身份证核对无误。")
        assert quality.kind == "text"
        assert quality.doc_hint is None

    def test_默认doc_hint为None保持向后兼容(self) -> None:
        # 老构造方式（不传 doc_hint）必须继续可用：落盘/回放旧产物时用得上
        quality = PageQuality(page_no=1, char_count=3, kind="sparse", reason="r", needs_visual_review=False)
        assert quality.doc_hint is None

    def test_认不出的短页给回原来的通用文案(self) -> None:
        # 反例：封面页没有任何证件关键词，就还是「内容较少」——不能被新文案污染
        quality = assess_page_quality(page_no=20, text="个人购房借款/担保合同\n某某银行某某支行\n2024年")
        assert quality.doc_hint is None
        assert quality.reason == "内容较少，可能是封面/证件/表单，建议核对"
