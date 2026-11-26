"""长正文注入（`\\a` 断段 + 私用区哨兵加粗）：真段落、真加粗、不给模型改结构的机会。

## 每条断言对应的真实后果

| 断言 | 不守会怎样 |
|---|---|
| 正文段落一律用 `\\a` 断 | `\\n` 只产出 `<w:br/>`（同一个 `<w:p>` 内的软换行），起诉状的 20 段事实缩成 1 段、只有首行缩进 2 字 |
| `\\f` / 输入自带的 `\\a` 被剥掉 | autoescape 拦不住控制符：模型输出一个 0x0C 就能把文书撕成两页、一个 0x07 就能自己断段 |
| 加粗只作用于哨兵区间 | 全量把 `**` 当加粗会吃掉「北京\\*\\*（某某市）律师事务所」这类律所名脱敏 |
| 无哨兵时返回原字节 | 33 个存量模板绝大多数不含长正文，它们不该被重新序列化一遍 |
| 长正文槽产生多段不触发骨架断言 | 一份 20 段起诉状会被自己人拦下来，功能直接不可用 |
| 固定段落被改/被删必须炸 | 模板是律所已验证的资产，模型开始重排条款时复核成本超过它省下的时间 |
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.oxml.ns import qn

from apps.doc_workspace.services import draft_service
from apps.documents.services.placeholders.long_text import (
    BOLD_CLOSE,
    BOLD_OPEN,
    apply_bold_sentinels,
    markdown_bold_to_sentinel,
    to_body_text,
)
from apps.documents.storage import get_public_docx_templates_root

_TEMPLATES: Path = Path(str(get_public_docx_templates_root()))
#: 真实起诉状：`{{事实与理由}}` 所在段落 firstLine=448 / 行距 360，段内 `numId=0`（走 `\a` 安全）
COMPLAINT = _TEMPLATES / "2-案件材料" / "1-起诉材料" / "1-起诉状和反诉答辩状" / "1-起诉状.docx"
#: 真实合同：全文段落带 `numId=1` 的自动编号，用来暴露「编号随 pPr 被逐段继承」这个边界
NUMBERED_CONTRACT = _TEMPLATES / "1-合同模板" / "专项合同.docx"

_COMPLAINT_VALUES = {
    "起诉状当事人信息": "原告：甲公司",
    "诉讼请求": "1. 判令被告支付货款。",
    "事实与理由": "",
    "审理机构": "某人民法院",
    "起诉状签名盖章信息": "具状人：甲公司",
}


def paragraphs(docx_bytes: bytes) -> list[Any]:
    """正文层段落（与 `Document.paragraphs` 同口径，表格内段落不在其中）。"""
    return list(Document(io.BytesIO(docx_bytes)).element.body.findall(qn("w:p")))


def text_of(paragraph: Any) -> str:
    return "".join(node.text or "" for node in paragraph.iter(qn("w:t")))


def first_line(paragraph: Any) -> str | None:
    p_pr = paragraph.find(qn("w:pPr"))
    ind = p_pr.find(qn("w:ind")) if p_pr is not None else None
    return ind.get(qn("w:firstLine")) if ind is not None else None


def num_id(paragraph: Any) -> str | None:
    p_pr = paragraph.find(qn("w:pPr"))
    num_pr = p_pr.find(qn("w:numPr")) if p_pr is not None else None
    num_id_elem = num_pr.find(qn("w:numId")) if num_pr is not None else None
    return num_id_elem.get(qn("w:val")) if num_id_elem is not None else None


def runs_of(paragraph: Any) -> list[tuple[bool, str]]:
    """[(是否加粗, run 文本)]，跳过空 run。`<w:b w:val="0"/>` 是显式不加粗。"""
    result: list[tuple[bool, str]] = []
    for run in paragraph.findall(qn("w:r")):
        r_pr = run.find(qn("w:rPr"))
        bold_elem = r_pr.find(qn("w:b")) if r_pr is not None else None
        is_bold = bold_elem is not None and bold_elem.get(qn("w:val")) not in ("0", "false")
        text = "".join(node.text or "" for node in run.findall(qn("w:t")))
        if text:
            result.append((is_bold, text))
    return result


def render_complaint(body: str) -> bytes:
    """把原始多行正文（`\\n` 分隔、可带 `**加粗**`）灌进真实起诉状的 `{{事实与理由}}`。

    这里**不**预调 `to_body_text`：`draft_service.render` 会对每个值做一次断段转换，
    预调一次就被转换两次——第二次会把已经断好的 `\\a` 当输入控制符剥掉，正文又压回一段。
    """
    values = dict(_COMPLAINT_VALUES)
    values["事实与理由"] = body
    return draft_service.render(COMPLAINT.read_bytes(), values, pending=[])


class TestBodyBreak:
    def test_newlines_become_real_paragraphs_with_template_indent(self) -> None:
        """`\\n` 是同一个 `<w:p>` 里的 `<w:br/>`，第二段起吃不到 `w:ind/@w:firstLine`。"""
        lines = [
            "**一、事实经过**",
            "2024年1月1日，原告与被告签订《供货合同》，约定被告分三期付款。",
            "被告仅支付第一期款项，余款至今未付。",
        ]
        body = "\n".join(lines)

        baseline = paragraphs(COMPLAINT.read_bytes())
        rendered = paragraphs(render_complaint(body))

        # 3 段正文替换掉原来承载占位符的那 1 段
        assert len(rendered) == len(baseline) + len(lines) - 1
        texts = [text_of(paragraph) for paragraph in rendered]
        for line in lines[1:]:
            paragraph = rendered[texts.index(line)]
            # 起诉状的缩进值是 448（办案小结是 480）：这里断言「继承」，不是断言某个魔数
            assert first_line(paragraph) == "448"
            assert paragraph.findall(".//" + qn("w:br")) == []

    def test_plain_string_newlines_are_paragraph_breaks(self) -> None:
        assert to_body_text("第一段\n第二段") == "第一段\a第二段"


class TestControlCharacters:
    def test_form_feed_and_foreign_body_break_are_stripped(self) -> None:
        body = to_body_text(["第一段\f撕页", "第二段\a模型自己断的段", "第三段"])
        assert "\f" not in body
        # 只剩我们自己插入的两个断段符，模型的 0x07 被剥掉后没有补回来
        assert body.count("\a") == 2
        assert "\n" not in body

    def test_tab_is_kept(self) -> None:
        assert to_body_text(["甲\t乙"]) == "甲\t乙"


class TestBoldSentinel:
    def test_bold_title_is_bold_and_body_is_not(self) -> None:
        body = "**一、事实经过**\n被告仅支付第一期款项，余款至今未付。"
        rendered = paragraphs(render_complaint(body))
        texts = [text_of(paragraph) for paragraph in rendered]

        assert runs_of(rendered[texts.index("一、事实经过")]) == [(True, "一、事实经过")]
        assert runs_of(rendered[texts.index("被告仅支付第一期款项，余款至今未付。")]) == [
            (False, "被告仅支付第一期款项，余款至今未付。")
        ]

    def test_inline_bold_splits_one_run_into_three(self) -> None:
        """句中局部加粗：一个 run 拆成「常规 + 加粗 + 常规」，且不丢模板的 `w:sz`。"""
        rendered = paragraphs(render_complaint("依据**《民法典》第五百七十七条**，应承担违约责任。"))
        paragraph = rendered[[text_of(p) for p in rendered].index("依据《民法典》第五百七十七条，应承担违约责任。")]

        assert runs_of(paragraph) == [
            (False, "依据"),
            (True, "《民法典》第五百七十七条"),
            (False, "，应承担违约责任。"),
        ]
        bold_run = next(
            run
            for run in paragraph.findall(qn("w:r"))
            if run.findall(qn("w:rPr")) is not None and run.find(qn("w:rPr")).find(qn("w:b")) is not None
        )
        tags = [child.tag for child in bold_run.find(qn("w:rPr"))]
        # CT_RPr 是 sequence：`w:b` 排在 `w:sz` 之前才合法，插到最前会被 Word 丢掉
        assert tags.index(qn("w:b")) < tags.index(qn("w:sz"))
        assert bold_run.find(qn("w:rPr")).find(qn("w:sz")).get(qn("w:val")) == "24"

    def test_sentinels_are_written_once_per_markdown_pair(self) -> None:
        assert markdown_bold_to_sentinel("**一、事实**") == f"{BOLD_OPEN}一、事实{BOLD_CLOSE}"
        # 单个星号是正文，不猜
        assert markdown_bold_to_sentinel("*一、事实*") == "*一、事实*"

    def test_sentinels_never_survive_the_postprocess(self) -> None:
        rendered = render_complaint("**粗标题**\n细正文")
        text = "".join(text_of(paragraph) for paragraph in paragraphs(rendered))
        assert BOLD_OPEN not in text
        assert BOLD_CLOSE not in text


class TestApplyBoldSentinels:
    def test_plain_docx_is_supported_without_renderer(self) -> None:
        document = Document()
        document.add_paragraph(f"依据{BOLD_OPEN}《民法典》第五百七十七条{BOLD_CLOSE}，应承担违约责任。")
        buffer = io.BytesIO()
        document.save(buffer)

        rendered = paragraphs(apply_bold_sentinels(buffer.getvalue()))

        assert runs_of(rendered[0]) == [
            (False, "依据"),
            (True, "《民法典》第五百七十七条"),
            (False, "，应承担违约责任。"),
        ]

    def test_bytes_are_returned_unchanged_when_no_sentinel(self) -> None:
        """没有哨兵就不重打包：33 个存量模板里绝大多数不含长正文。"""
        for template in (COMPLAINT, NUMBERED_CONTRACT):
            raw = template.read_bytes()
            assert apply_bold_sentinels(raw) == raw


class TestSkeleton:
    @staticmethod
    def _template() -> bytes:
        document = Document()
        document.add_paragraph("委托代理合同")
        document.add_paragraph("一、委托事项")
        document.add_paragraph("{{facts}}")
        document.add_paragraph("二、费用")
        document.add_paragraph("本合同一式两份，双方各执一份。")
        buffer = io.BytesIO()
        document.save(buffer)
        return buffer.getvalue()

    def test_long_text_slot_producing_extra_paragraphs_is_accepted(self) -> None:
        """长正文槽合法地 1 段变 N 段——段落数不再是骨架不变量。"""
        template = self._template()
        body = "2024年1月，双方签订委托代理合同。\n2024年2月，被告未按期付款。\n2024年3月，原告催告。"
        rendered = draft_service.render(template, {"facts": body}, pending=[])

        draft_service._assert_skeleton_intact(template, rendered)
        assert len(paragraphs(rendered)) == 7

    def test_rewritten_fixed_paragraph_raises(self) -> None:
        template = self._template()
        rendered = draft_service.render(template, {"facts": "2024年1月，双方签约。"}, pending=[])

        tampered = Document(io.BytesIO(rendered))
        tampered.paragraphs[4].text = "本合同一式三份，双方各执一份。"
        buffer = io.BytesIO()
        tampered.save(buffer)

        with pytest.raises(RuntimeError, match="不含槽位的段落"):
            draft_service._assert_skeleton_intact(template, buffer.getvalue())

    def test_removed_fixed_paragraph_raises(self) -> None:
        template = self._template()
        rendered = draft_service.render(template, {"facts": "2024年1月，双方签约。"}, pending=[])

        tampered = Document(io.BytesIO(rendered))
        tampered._element.body.remove(tampered.paragraphs[4]._element)
        buffer = io.BytesIO()
        tampered.save(buffer)

        with pytest.raises(RuntimeError, match="不含槽位的段落"):
            draft_service._assert_skeleton_intact(template, buffer.getvalue())


@pytest.mark.xfail(
    strict=False,
    reason="numId≠0 的占位符段落不能走 \\a：编号存在 w:numPr 里，断出的每一段都继承它，"
    "一段正文变成 1./2./3. 编号项（处置办法：调用方按 w:numId 白名单选择分隔符）",
)
def test_numbered_placeholder_paragraph_does_not_multiply_list_items() -> None:
    """`专项合同.docx` 的段落全带 `numId=1`：注入多段正文时，期望「编号项不增加」。

    现状会失败，这条 xfail 是那个边界的哨兵——修好（按 numId 白名单选分隔符）之后它会 XPASS，
    届时把本用例转成正常断言。
    """
    raw = NUMBERED_CONTRACT.read_bytes()
    baseline = sum(1 for paragraph in paragraphs(raw) if num_id(paragraph) not in (None, "0"))

    rendered = draft_service.render(raw, {"合同份数": "三\n四\n五"}, pending=[])
    after = sum(1 for paragraph in paragraphs(rendered) if num_id(paragraph) not in (None, "0"))

    assert after == baseline
