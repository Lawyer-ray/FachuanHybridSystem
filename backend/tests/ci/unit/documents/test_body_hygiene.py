"""模型正文洁净度闸（D1）与比率/合计闸（D3）的回归测试。

覆盖：
- 真机泄漏样本（2026-11-26 案卷 489，A_trunc 的「事实与理由」原文）判成推演、不写进成稿
- 正常起诉状正文（含偶发一个「注意：」和「综上，被告……」）不被误杀
- 每日 3% 报反常、每日 0.3% 不报；同段混用 ‰/% 报核对；分项合计不符报核对
- resolve_slot_values 的 warnings 参数：传列表能收到、传 None 与不传完全一致
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.documents.models import DocumentSpec, DocumentTemplate
from apps.documents.models.document_spec import SlotSource
from apps.documents.services.draft.spec_service import resolve_slot_values
from apps.documents.services.placeholders.body_hygiene import (
    check_numeric_sanity,
    looks_like_reasoning,
    sanitize_llm_body,
    strip_reasoning,
)

COMPLAINT_TEMPLATE_PATH = "2-案件材料/1-起诉材料/1-起诉状和反诉答辩状/1-起诉状.docx"

#: 真机泄漏样本原文（A_trunc.txt 第 11-12 行，逐字照抄）：
#: 模型把「只写本节正文」的系统提示连自己的推演一起当成正文交回。
REAL_LEAK_SAMPLE = (
    "我们需要起草“事实与理由”部分，用于起诉状。只写本节正文，不写标题、不加序号、不重复小标题。只能使用"
    "给定事实中能推出的信息，不能编造金额、日期、主体名称。需要分段陈述，每段单独一行，按时间顺序或争议焦"
    "点组织。\n"
    "我们需要考虑起诉状的事实与理由通常包括：合同签订情况、合同主要内容、原告履行情况（交付土地"
    "）、被告违约事实（未付款项）、催告情况、违约后果、诉讼请求依据（合同条款、法律依据）。但只能使用给定"
    "事实。给定事实包括律师函和合同扫描件前2000字。涉案金额440000.00，但律师函列欠款合计404221.00，"
    "保证金1061814.25。注意涉案金额440000.00可能包括欠款+其他？不能编造。事实与理由应围绕欠费展开。"
    "律师函载明欠款合计404221.00元，但涉案金额440000.00。"
)

#: 报告里引用的伪条目（合同 OCR 第 558 行）：模型把「行号 + 原文」当成正文抄进推演。
REAL_LEAK_OCR_ECHO = "\n".join(
    [
        "558: 乙方（受让方）：受让人甲",
        "559: 身份证：4406**********31X",
        "560: 详细地址：某地址（已脱敏）",
    ]
)

#: 正常起诉状正文：只夹一个「注意：」，同时带着 D3 需要放过的正确合计。
NORMAL_COMPLAINT_BODY = (
    "2026年5月8日，原告与被告签订《土地分包合同书》，约定被告承包案涉地块，承包期限自2026年6月1日起"
    "至2044年11月23日止。\n"
    "合同签订后，被告未按约支付承包金。截至2026年11月16日，被告拖欠承包金384277.00元、水费1661.00元、"
    "水费1589.00元、管理维护费16694.00元，合计404221.00元。\n"
    "注意：上述欠款均已逾期超过一个月。\n"
    "综上，被告的行为已构成根本性违约，依法应承担继续履行、支付滞纳金及赔偿损失等违约责任。"
)


class TestLooksLikeReasoning:
    def test_real_leak_sample_is_reasoning(self) -> None:
        assert looks_like_reasoning(REAL_LEAK_SAMPLE) is True

    def test_ocr_echo_lines_are_pseudo_entries(self) -> None:
        """连续 3 条「行号 + 原文」才算推演：单条编号列表在正文里是正常格式。"""
        assert looks_like_reasoning(REAL_LEAK_OCR_ECHO) is True
        assert looks_like_reasoning("558: 乙方（受让方）：受让人甲") is False

    def test_ocr_echo_quoted_from_material_is_not_reasoning(self) -> None:
        material = (
            "乙方（受让方）：受让人甲\n身份证：4406**********31X\n详细地址：某省某市某区某路 1 号"
        )
        assert looks_like_reasoning(REAL_LEAK_OCR_ECHO, material=material) is False

    def test_normal_complaint_body_is_not_killed(self) -> None:
        assert looks_like_reasoning(NORMAL_COMPLAINT_BODY) is False

    def test_single_incidental_marker_is_below_threshold(self) -> None:
        assert looks_like_reasoning("注意：被告的付款期限已经届满。") is False

    def test_self_question_variant_is_recognized(self) -> None:
        """真机样本里写的是「能推出吗？」（少一个「来」），不能只认报告里的写法。"""
        assert looks_like_reasoning("能推出吗？给定事实没有说被告未履行，注意：不能编造。") is True


class TestStripReasoning:
    def test_real_leak_sample_has_no_deliverable_body(self) -> None:
        assert strip_reasoning(REAL_LEAK_SAMPLE) == ""
        assert strip_reasoning(REAL_LEAK_SAMPLE + "\n" + REAL_LEAK_OCR_ECHO) == ""

    def test_clean_sentences_are_salvaged_when_they_dominate(self) -> None:
        """夹花回收的判据是**占比**：干净正文够多才回收，否则整段转未决。

        真机第二轮（run1）就是夹花形态：合同条款陈述与「需要按时间顺序：」交替出现。
        整段丢弃太浪费，逐句全收又会让规划句漏进成稿，所以按 35% 占比取中间那一档。
        """
        recovered = (
            "原告与被告于2026年5月8日签订《土地分包合同书》，约定被告分包绿茵路42号地块。"
            "合同约定首个承包年度承包金384277元，应于2026年5月8日前缴交。"
            "被告未按约支付，原告委托律师发出律师函催告，被告至今未履行付款义务。"
        )
        text = f"{recovered}\n{REAL_LEAK_SAMPLE}"
        cleaned = strip_reasoning(text)
        # 保干净正文、且**不留元话语**是硬约束；回收结果允许带上样本里那两句
        # 「涉案金额 440000 与 404221 差多少」式的材料陈述（它们本身不是元话语）。
        assert cleaned.replace("\n", "").startswith(recovered)
        assert "需要" not in cleaned
        assert "给定事实" not in cleaned

    def test_short_clean_fragment_below_ratio_is_dropped(self) -> None:
        """只捞回一句半成品不算成果：整段转未决，让上游重试或标 `<待填写>`。"""
        text = f"{REAL_LEAK_SAMPLE}\n\n被告未按约支付承包金。"
        assert strip_reasoning(text) == ""

    def test_normal_body_is_returned_unchanged(self) -> None:
        assert strip_reasoning(NORMAL_COMPLAINT_BODY) == NORMAL_COMPLAINT_BODY


class TestNumericSanity:
    def test_daily_three_percent_is_flagged(self) -> None:
        warnings = check_numeric_sanity("逾期不缴清的，按欠缴金额每日3%支付滞纳金。")
        assert len(warnings) == 1
        assert "3%" in warnings[0]
        assert "1095%" in warnings[0]

    def test_daily_point_three_percent_is_not_flagged(self) -> None:
        assert check_numeric_sanity("逾期不缴清的，按欠缴金额每日0.3%支付滞纳金。") == []

    def test_mixed_permille_and_percent_is_flagged(self) -> None:
        warnings = check_numeric_sanity("承包金按每日3‰计息；逾期部分另按20%加收违约金。")
        assert len(warnings) == 1
        assert "‰" in warnings[0] and "%" in warnings[0]

    def test_itemized_amounts_matching_total_are_not_flagged(self) -> None:
        assert check_numeric_sanity(NORMAL_COMPLAINT_BODY) == []

    def test_itemized_amounts_not_matching_total_are_flagged(self) -> None:
        text = "被告拖欠承包款384277.00元、水费1661.00元、管理维护费16694.00元，合计：404221.00元。"
        warnings = check_numeric_sanity(text)
        assert len(warnings) == 1
        assert "402632.00" in warnings[0]
        assert "404221.00" in warnings[0]

    def test_sanitize_returns_clean_body_with_numeric_warning(self) -> None:
        body, warnings = sanitize_llm_body("判令被告按每日3%支付逾期付款滞纳金至实际清偿之日止。")
        assert body == "判令被告按每日3%支付逾期付款滞纳金至实际清偿之日止。"
        assert any("3%" in warning for warning in warnings)

    def test_sanitize_drops_reasoning_entirely(self) -> None:
        assert sanitize_llm_body(REAL_LEAK_SAMPLE) == ("", [])


@pytest.fixture
def complaint_template(db: Any) -> DocumentTemplate:
    return DocumentTemplate.objects.create(
        name="起诉状",
        template_type="case",
        case_types=["all"],
        file_path=COMPLAINT_TEMPLATE_PATH,
    )


def make_llm_claim_spec(template: DocumentTemplate) -> DocumentSpec:
    """只让请求段走 LLM：事实段走 slot 且没有事实，避免同一个替身被调用两次。"""
    return DocumentSpec.objects.create(
        doc_type="unit_body_hygiene",
        display_name="单元测试文书",
        skeleton_template=template,
        claim_source=SlotSource.LLM,
        claim_slot_key="诉讼请求",
        facts_source=SlotSource.SLOT,
        facts_slot_key="事实与理由",
    )


class TestResolveSlotValuesWarnings:
    def test_reasoning_body_becomes_pending_and_is_reported(self, complaint_template: DocumentTemplate) -> None:
        spec = make_llm_claim_spec(complaint_template)
        warnings: list[str] = []
        context, pending = resolve_slot_values(spec, llm_caller=lambda _messages: REAL_LEAK_SAMPLE, warnings=warnings)
        assert "诉讼请求" not in context
        assert "诉讼请求" in pending
        assert any("思维链" in warning for warning in warnings)

    def test_numeric_warning_is_forwarded(self, complaint_template: DocumentTemplate) -> None:
        spec = make_llm_claim_spec(complaint_template)
        body = "判令被告以欠付承包款为基数，按每日3%支付滞纳金至实际清偿之日止。"
        warnings: list[str] = []
        context, _ = resolve_slot_values(spec, llm_caller=lambda _messages: body, warnings=warnings)
        assert context["诉讼请求"] == body
        assert any("3%" in warning for warning in warnings)

    def test_warnings_none_is_identical_to_omitting_it(self, complaint_template: DocumentTemplate) -> None:
        spec = make_llm_claim_spec(complaint_template)

        def caller(_messages: list[dict[str, str]]) -> str:
            return "判令被告返还借款。"

        without_warnings = resolve_slot_values(spec, llm_caller=caller)
        with_none = resolve_slot_values(spec, llm_caller=caller, warnings=None)
        assert without_warnings == with_none
