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
        assert quality.reason == "内容较少，可能是封面/证件/表单，建议核对"
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
