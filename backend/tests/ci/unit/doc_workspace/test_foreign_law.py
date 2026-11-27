"""域外法查明：引用抽取、结论分档、确定性注入。

## 每条断言对应的真实后果

| 断言 | 不守会怎样 |
|---|---|
| 中英双语引用都能抽出来 | 只抽中文 → 英文正本里的错法条一次都查不到 |
| 中国法引用不送去域外查明 | `《民法典》第470条` 被当成外国法去查，产出「查无此法」的假结论 |
| 法名没认准时不判「不存在」 | `Arbitration Act` 因为库内标题不同被判成编造，律师从此不信这个功能 |
| 条款切分不完整时不判「不存在」 | Labour Protection Act 只切出 4 条 → 第 118 条被误判为编造 |
| 查无此法 → 程序直接落结论 | 模型漏报时，清单上显示「AI 审过了，没问题」 |
| 查无此法的结论是 mandatory + list_only | 被条数闸丢掉，或被自动改写成律师没同意的文字 |
"""

from __future__ import annotations

import pytest

from apps.doc_workspace.models import Consequence, Delivery, Jurisdiction, RiskSource, RuleClass, Severity, SourceWeight
from apps.doc_workspace.services import foreign_law

pytestmark = pytest.mark.django_db


# ── 引用抽取 ────────────────────────────────────────────────────────────


def test_extracts_chinese_citation() -> None:
    text = "依据《泰国商业租赁法》第 42 条，租期可延长。"
    items = foreign_law.extract_citations(text)
    assert len(items) == 1
    assert items[0].law_name == "泰国商业租赁法"
    assert items[0].section_number == "42"


def test_extracts_english_citation_of_patterns() -> None:
    text = (
        "The duration shall be governed by Section 540 of the Civil and Commercial Code. "
        "Tax is payable under Section 77/1 of the Revenue Code."
    )
    items = foreign_law.extract_citations(text)
    names = {(i.law_name, i.section_number) for i in items}
    assert ("Civil and Commercial Code", "540") in names
    assert ("Revenue Code", "77/1") in names


def test_extracts_law_name_without_section() -> None:
    items = foreign_law.extract_citations("The operator shall obtain a licence under the Foreign Business Act.")
    assert [i.law_name for i in items] == ["Foreign Business Act"]
    assert items[0].section_number == ""


def test_skips_domestic_chinese_statutes() -> None:
    """中国法条不进域外查明：把它送去 BARLC 只会得到「查无此法」这种假结论。"""
    items = foreign_law.extract_citations("依据《民法典》第470条与《城市房地产管理法》第38条。")
    assert items == []


def test_keeps_chinese_named_foreign_statute() -> None:
    """中文写法不等于中国法：《泰国民商法典》必须照样去查。"""
    items = foreign_law.extract_citations("依据《泰国民商法典》第540条。")
    assert [i.law_name for i in items] == ["泰国民商法典"]


def test_dedupes_same_citation() -> None:
    text = "《泰国商业租赁法》第42条……再次强调《泰国商业租赁法》第42条。"
    assert len(foreign_law.extract_citations(text)) == 1


def test_law_name_variants_cover_translation_drift() -> None:
    """《泰国民商法典》在 BARLC 里的标题是「民商法典」——不多试几种写法就会把真法报成编造。"""
    variants = foreign_law.law_name_variants("泰国民商法典")
    assert "泰国民商法典" in variants
    assert "民商法典" in variants
    assert foreign_law.law_name_variants("外国商业法")[-1] == "外国商业法典"


def test_citation_count_is_bounded() -> None:
    text = "".join(f"《外国法律汇编第{i}卷》第{i}条。" for i in range(1, 40))
    assert len(foreign_law.extract_citations(text)) <= foreign_law.MAX_CITATIONS


# ── 结论分档（最容易误杀真实引用的地方）────────────────────────────────


def test_status_verified_when_section_text_present() -> None:
    status, _ = foreign_law.classify_status(
        section_text="Section 540. The duration of a hire of immovable property cannot exceed thirty years.",
        matched_by="exact",
        reason="已取到条文原文",
    )
    assert status == foreign_law.STATUS_VERIFIED


def test_status_unconfirmed_when_name_not_resolved() -> None:
    """`Arbitration Act` 在库里没有同名词条，但该法真实存在 —— 不许判死。"""
    status, _ = foreign_law.classify_status(section_text="", matched_by="", reason="未检索到该法律")
    assert status == foreign_law.STATUS_UNCONFIRMED


def test_status_unconfirmed_when_section_splitting_is_implausible() -> None:
    """Labour Protection Act 只切出 4 条 → 「第 118 条不存在」是切分失败的假结论。"""
    status, reason = foreign_law.classify_status(
        section_text="",
        matched_by="containment",
        reason="该法律正文中不存在第 118 条（共 4 条）",
        result="不存在该引用",
    )
    assert status == foreign_law.STATUS_UNCONFIRMED
    assert "切分仅 4 条" in reason


def test_status_missing_section_when_splitting_looks_sane() -> None:
    status, _ = foreign_law.classify_status(
        section_text="",
        matched_by="exact",
        reason="该法律正文中不存在第 999 条（共 240 条）",
        result="不存在该引用",
    )
    assert status == foreign_law.STATUS_MISSING_SECTION


def test_status_missing_section_when_count_unknown() -> None:
    status, _ = foreign_law.classify_status(
        section_text="", matched_by="exact", reason="条款切分完成但无该条", result="不存在该引用"
    )
    assert status == foreign_law.STATUS_MISSING_SECTION


def test_upstream_empty_result_is_unconfirmed_not_missing() -> None:
    """上游 `result==""` = 「没形成结论」，不是「不存在」。"""
    status, _ = foreign_law.classify_status(section_text="", matched_by="exact", reason="", result="")
    assert status == foreign_law.STATUS_UNCONFIRMED


def test_needs_human_never_becomes_missing() -> None:
    status, _ = foreign_law.classify_status(
        section_text="", matched_by="exact", reason="需人工复核", result="不存在该引用", needs_human=True
    )
    assert status == foreign_law.STATUS_UNCONFIRMED


def test_unextractable_fulltext_is_unconfirmed_not_missing() -> None:
    """判例法国家（SG/PH/MY/BN）成文法常常「库里只有标题页、没有可切分正文」。

    真机证据：`Arbitration Act 2005` 第 9 条 → 「该法律正文中不存在第 9 条（共 3 条）」，
    真相是 PDF 取了但切不出条款。判成 missing_section 会把一条正经引用报成
    「引用了不存在的法」，律师第一次就会关掉这个功能。
    """
    status, _ = foreign_law.classify_status(
        section_text="",
        matched_by="exact",
        reason="正文已取到但未能切分出条款（可能是图片版 PDF…）",
        result="",
        needs_human=True,
    )
    assert status == foreign_law.STATUS_UNCONFIRMED


def test_no_readable_fulltext_is_unconfirmed() -> None:
    status, _ = foreign_law.classify_status(
        section_text="",
        matched_by="exact",
        reason="该法律在数据库中无可读正文，无法作为引用依据",
        result="不存在该引用",
    )
    assert status == foreign_law.STATUS_UNCONFIRMED


def test_law_only_citation_is_verified_once_name_resolved() -> None:
    """只引法名（不引条号）：名称已定位到具体法，就是「法存在」这个结论。"""
    status, _ = foreign_law.classify_status(
        section_text="",
        matched_by="exact",
        reason="未指定条款号，仅确认法律存在",
        result="原文未提及",
        has_section_number=False,
    )
    assert status == foreign_law.STATUS_VERIFIED


# ── gather：无引用时零成本、失败不抛 ─────────────────────────────────────


def test_gather_skips_without_citations() -> None:
    evidence = foreign_law.gather(text="这是一份纯中国法合同，依据《民法典》第470条。", jurisdiction=Jurisdiction.CN)
    assert evidence.items == []
    assert evidence.skipped
    assert evidence.to_prompt_block() == ""


def test_gather_skips_uncovered_jurisdiction_instead_of_cross_country_lookup() -> None:
    """东帝汶没有 BARLC 国别码：**不许**退回「跨东盟全域检索」，那会拿邻国同名法冒充。"""

    def _boom(citation: foreign_law.Citation, *, country_code: str) -> foreign_law.CitationEvidence:
        raise AssertionError("不该调用核验器")

    evidence = foreign_law.gather(text="依据《帝汶投资法》第3条。", jurisdiction=Jurisdiction.TL, verifier=_boom)
    assert evidence.items == []
    assert "不覆盖" in evidence.skipped


def test_gather_reports_skipped_when_plugin_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(foreign_law, "default_verifier", lambda: None)
    evidence = foreign_law.gather(text="依据《泰国商业租赁法》第42条。", jurisdiction=Jurisdiction.TH)
    assert evidence.items == []
    assert "未接入" in evidence.skipped


def test_gather_keeps_going_when_one_citation_explodes() -> None:
    def _verifier(citation: foreign_law.Citation, *, country_code: str) -> foreign_law.CitationEvidence:
        if "崩" in citation.law_name:
            raise RuntimeError("上游炸了")
        return foreign_law.CitationEvidence(citation=citation, status=foreign_law.STATUS_MISSING_LAW, reason="检索不到")

    evidence = foreign_law.gather(
        text="《崩坏法》第1条 与 《泰国商业租赁法》第42条",
        jurisdiction=Jurisdiction.TH,
        verifier=_verifier,
    )
    statuses = sorted(i.status for i in evidence.items)
    assert statuses == [foreign_law.STATUS_MISSING_LAW, foreign_law.STATUS_UNAVAILABLE]


# ── 确定性注入：模型漏报也要出现在清单上 ────────────────────────────────


def _evidence_with(*statuses: str) -> foreign_law.ForeignLawEvidence:
    items = [
        foreign_law.CitationEvidence(
            citation=foreign_law.Citation(law_name=f"某外国法{index}", section_number=str(42 + index), raw="原文片段"),
            status=status,
            reason="BARLC 该国库中检索不到该法律名称",
        )
        for index, status in enumerate(statuses)
    ]
    return foreign_law.ForeignLawEvidence(items=items, jurisdiction=Jurisdiction.TH)


def test_deterministic_finding_for_missing_law_is_mandatory_and_list_only() -> None:
    items = foreign_law.deterministic_findings(_evidence_with(foreign_law.STATUS_MISSING_LAW))
    assert len(items) == 1
    item = items[0]
    assert item["rule_key"] == "foreign_law.citation_invalid"
    assert item["rule_class"] == RuleClass.MANDATORY
    assert item["severity"] == Severity.HIGH
    assert item["risk_source"] == RiskSource.STATUTE
    assert item["source_weight"] == SourceWeight.CORE
    assert item["consequence"] == Consequence.UNEFFECTIVE
    # 不自动改正文：换成哪一部法只有律师知道
    assert item["delivery"] == Delivery.LIST_ONLY
    assert item["suggestion_replacement"] == ""


def test_unconfirmed_citation_is_medium_not_high() -> None:
    items = foreign_law.deterministic_findings(_evidence_with(foreign_law.STATUS_UNCONFIRMED))
    assert items[0]["rule_key"] == "foreign_law.citation_unconfirmed"
    assert items[0]["severity"] == Severity.MEDIUM


def test_verified_citation_produces_no_deterministic_finding() -> None:
    assert foreign_law.deterministic_findings(_evidence_with(foreign_law.STATUS_VERIFIED)) == []


def test_escalates_model_finding_that_mentions_a_missing_law() -> None:
    """模型把「引用了不存在的法」写成 medium 的措辞问题时，必须升到 mandatory。"""
    model_items = [
        {
            "rule_key": "th.lease_term_limit",
            "rule_class": RuleClass.CONTRACTUAL,
            "severity": Severity.MEDIUM,
            "legal_basis": "《某外国法0》第42条",
            "reason": "引用不规范",
            "title": "",
            "quote": "",
        }
    ]
    escalated = foreign_law.escalate_model_citations(model_items, _evidence_with(foreign_law.STATUS_MISSING_LAW))
    assert escalated == 1
    assert model_items[0]["rule_class"] == RuleClass.MANDATORY
    assert model_items[0]["severity"] == Severity.HIGH


def test_escalation_ignores_findings_about_other_laws() -> None:
    model_items = [
        {
            "rule_key": "th.vat_rate",
            "rule_class": RuleClass.CONTRACTUAL,
            "severity": Severity.MEDIUM,
            "legal_basis": "Revenue Code Section 77/1",
            "reason": "税率写错",
            "title": "",
            "quote": "",
        }
    ]
    assert foreign_law.escalate_model_citations(model_items, _evidence_with(foreign_law.STATUS_MISSING_LAW)) == 0
    assert model_items[0]["rule_class"] == RuleClass.CONTRACTUAL


def test_prompt_block_states_the_three_hard_rules() -> None:
    block = _evidence_with(foreign_law.STATUS_MISSING_LAW, foreign_law.STATUS_VERIFIED).to_prompt_block()
    assert "域外法查明结果" in block
    assert "查无此法" in block
    assert "只能引用本节列出的法条" in block


def test_extracts_name_first_citation() -> None:
    """`Arbitration Act Section 99` 这种法名在前的写法也要抽出来（真机漏抽过一次）。"""
    items = foreign_law.extract_citations("依据 Arbitration Act Section 99，裁决为终局。")
    assert [(i.law_name, i.section_number) for i in items] == [("Arbitration Act", "99")]


def test_extracts_both_orders_without_duplicates() -> None:
    text = "Section 118 of the Labour Protection Act …… 依据 Labour Protection Act, Section 118。"
    items = [i for i in foreign_law.extract_citations(text) if i.law_name == "Labour Protection Act"]
    assert len(items) == 1
    assert items[0].section_number == "118"
