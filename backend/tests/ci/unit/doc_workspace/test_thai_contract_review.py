"""泰国（域外）合同审查端到端：法域路由 + 域外法查明 + 结论注入。

自检语料：`fixtures/thai_land_lease_zh_en.md`（中英双语泰国土地租赁合同，埋了 10 处泰国法错误）。

## 这组用例回答的问题

1. 传 `jurisdiction="TH"` 时，用的是**泰国**标准库而不是中国标准库吗？
2. 合同里「《泰国商业租赁法》第 42 条」这种**根本不存在的法**，查得出来吗？
3. 模型**漏报**时，清单上还会有这条结论吗？（这是最关键的：AI 审过了 ≠ 没问题）
4. 查到的条文原文进提示词了吗？（不让模型凭记忆判断，而是拿原文比对）
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from docx import Document

from apps.doc_workspace.models import Delivery, Jurisdiction, RiskSource, RuleClass, Severity, Stance
from apps.doc_workspace.services import foreign_law, playbook_service, review_pipeline

pytestmark = pytest.mark.django_db

FIXTURE = Path(__file__).parent / "fixtures" / "thai_land_lease_zh_en.md"
KIND = "contract"
OWNER_ID = 977
SUBPATH = "1-合同/泰国春武里土地租赁.docx"

#: 合同里那处**编造**的引用（泰国没有这部法）
FAKE_LAW = "泰国商业租赁法"

#: CCC 第 540 条的真实原文（BARLC 查到的内容，用于喂给模型比对）
CCC_540_TEXT = (
    "Section 540. The duration of a hire of immovable property cannot exceed thirty years. "
    "If it is made for a longer period, such period shall be reduced to thirty years."
)


def _contract_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _docx_bytes(text: str) -> bytes:
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def thai_verifier() -> Any:
    """模拟 BARLC 的查明结果：编造的那部法查无此法，CCC 540 能取到原文。"""

    def _verify(citation: foreign_law.Citation, *, country_code: str) -> foreign_law.CitationEvidence:
        assert country_code == "LAWCOUNTRYTG", "泰国合同必须用 BARLC 的泰国国别码，不是 ISO 缩写"
        if FAKE_LAW in citation.law_name:
            return foreign_law.CitationEvidence(
                citation=citation,
                status=foreign_law.STATUS_MISSING_LAW,
                reason="BARLC 该国库中检索不到该法律名称",
            )
        if "540" in citation.section_number or "民商法典" in citation.law_name:
            return foreign_law.CitationEvidence(
                citation=citation,
                status=foreign_law.STATUS_VERIFIED,
                law_title="Civil and Commercial Code",
                section_text=CCC_540_TEXT,
                matched_by="exact",
                reason="已取到条文原文",
            )
        return foreign_law.CitationEvidence(
            citation=citation,
            status=foreign_law.STATUS_UNCONFIRMED,
            reason="法名只是近似命中，需人工核对",
        )

    foreign_law.register_verifier(_verify)
    yield _verify
    foreign_law.register_verifier(None)


def _llm_returning(payload: dict[str, Any]) -> Any:
    captured: dict[str, Any] = {}

    def _caller(messages: list[dict[str, str]]) -> str:
        captured["messages"] = messages
        return "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"

    _caller.captured = captured  # type: ignore[attr-defined]
    return _caller


def _lease_year_payload() -> dict[str, Any]:
    """模型只报了「租期超上限」这一条，**故意不报**编造的引用。"""
    return {
        "subject_profile": ["泰国春武里府带酒店的商业地块", "承租方为中国法人"],
        "relations": [
            {"relation": "泰国土地厅", "why": "租赁登记与土地过户", "risk": "未登记则超 3 年部分不能诉请履行"}
        ],
        "findings": [
            {
                "rule_key": "th.lease_term_limit",
                "verdict": "deviation",
                "severity": "high",
                "risk_source": "statute",
                "source_weight": "core",
                "quote": "租赁期限为 50 年",
                "title": "租期 50 年超过泰国法上限 30 年，超出部分无效",
                "reason": "Civil and Commercial Code Section 540 规定不动产租赁不得超过 30 年",
                "impact": "后 20 年对双方没有约束力，乙方无法主张继续占有，酒店投资回收期落空",
                "suggestion_original": "租赁期限为 50 年",
                "suggestion_replacement": "租赁期限为 30 年，期满按本合同第 3.4 条续期",
                "suggestion_note": "",
            }
        ],
    }


# ── 法域路由 ────────────────────────────────────────────────────────────


def test_thai_playbook_uses_thai_statutes_not_chinese_ones() -> None:
    rules = playbook_service.rules_for(contract_type="土地租赁", jurisdiction=Jurisdiction.TH)
    keys = {r["rule_key"] for r in rules}
    assert "th.lease_term_limit" in keys
    assert "th.land_ownership_foreigner" in keys
    assert "th.condo_foreign_quota" in keys
    assert "foreign_law.citation_invalid" in keys
    # 中国法条一条都不许出现在泰国标准库里
    assert not any("《民法典》" in str(r.get("legal_basis") or "") for r in rules)


def test_chinese_playbook_still_carries_citation_integrity_rules() -> None:
    keys = {r["rule_key"] for r in playbook_service.rules_for(contract_type="买卖", jurisdiction=Jurisdiction.CN)}
    assert "foreign_law.citation_invalid" in keys
    assert "th.lease_term_limit" not in keys


def test_resolve_does_not_fall_back_across_jurisdictions() -> None:
    """泰国合同找不到标准库时不能回落成中国法标准——那会把「审错法」伪装成正常结果。"""
    book = playbook_service.resolve(contract_type="土地租赁", stance=Stance.NEUTRAL, jurisdiction=Jurisdiction.TH)
    assert book.jurisdiction == Jurisdiction.TH
    assert "泰国" in book.name


def test_bump_version_keeps_rule_class_stage_and_consequence() -> None:
    """改一版标准不能把 mandatory 静默降级成可谈条款（v27.25.8 字段漏拷的真实事故）。"""
    book = playbook_service.resolve(contract_type="", stance=Stance.NEUTRAL, jurisdiction=Jurisdiction.TH)
    bumped = playbook_service.bump_version(book, note="测试改版")
    before = {r.rule_key: r for r in book.rules.all()}
    for rule in bumped.rules.all():
        assert rule.rule_class == before[rule.rule_key].rule_class
        assert rule.stage == before[rule.rule_key].stage
        assert rule.consequence == before[rule.rule_key].consequence


# ── 端到端 ──────────────────────────────────────────────────────────────


def test_thai_review_flags_fabricated_statute_even_when_model_misses_it(thai_verifier: Any) -> None:
    text = _contract_text()
    caller = _llm_returning(_lease_year_payload())

    run = review_pipeline.run_review(
        kind=KIND,
        owner_id=OWNER_ID,
        subpath=SUBPATH,
        stance=Stance.PARTY_B,
        contract_type="土地租赁",
        jurisdiction=Jurisdiction.TH,
        raw_bytes=_docx_bytes(text),
        text=text,
        caller=caller,
    )

    assert run.status == "done", run.error_message
    assert run.jurisdiction == Jurisdiction.TH
    assert ":TH:" in run.playbook_key

    by_rule = {f.rule_key: f for f in run.findings.all()}
    # ① 模型报的那条在
    assert "th.lease_term_limit" in by_rule
    # ② 模型**没报**的编造引用，程序自己落了一条（这是这组用例的核心断言）
    fabricated = [f for f in run.findings.all() if f.rule_key == "foreign_law.citation_invalid"]
    assert fabricated, "查无此法的引用必须由程序落结论，不能指望模型"
    assert FAKE_LAW in fabricated[0].title
    assert fabricated[0].rule_class == RuleClass.MANDATORY
    assert fabricated[0].severity == Severity.HIGH
    assert fabricated[0].risk_source == RiskSource.STATUTE
    assert fabricated[0].delivery == Delivery.LIST_ONLY

    counts = run.summary["foreign_law"]["counts"]
    assert counts[foreign_law.STATUS_MISSING_LAW] >= 1
    assert counts[foreign_law.STATUS_VERIFIED] >= 1


def test_prompt_carries_jurisdiction_switch_law_rules_and_verified_text(thai_verifier: Any) -> None:
    text = _contract_text()
    caller = _llm_returning(_lease_year_payload())

    review_pipeline.run_review(
        kind=KIND,
        owner_id=OWNER_ID,
        subpath=SUBPATH,
        stance=Stance.PARTY_B,
        contract_type="土地租赁",
        jurisdiction=Jurisdiction.TH,
        raw_bytes=_docx_bytes(text),
        text=text,
        caller=caller,
    )

    system = caller.captured["messages"][0]["content"]
    # ① 身份从「中国执业律师」切到泰国法
    assert "泰国法" in system
    assert "你是中国执业律师" not in system
    # ② 域外法硬约束在
    assert "不许凭记忆引用外国法条文" in system
    # ③ 查明结果的原文进了提示词（模型是比对而不是回忆）
    assert "Section 540. The duration of a hire of immovable property cannot exceed thirty years" in system
    # ④ 编造的那部法被明确标成查无此法
    assert "查无此法" in system
    # ⑤ 泰国标准库进了提示词
    assert "th.lease_term_limit" in system


def test_chinese_jurisdiction_prompt_stays_chinese(thai_verifier: Any) -> None:
    text = "甲方愿意支付人民币壹万元整。依据《民法典》第470条。"
    caller = _llm_returning({"subject_profile": [], "relations": [], "findings": []})

    run = review_pipeline.run_review(
        kind=KIND,
        owner_id=OWNER_ID,
        subpath="1-合同/中国合同.docx",
        stance=Stance.NEUTRAL,
        contract_type="买卖",
        jurisdiction=Jurisdiction.CN,
        raw_bytes=_docx_bytes(text),
        text=text,
        caller=caller,
    )

    system = caller.captured["messages"][0]["content"]
    assert "适用中国法" in system
    assert "不许凭记忆引用外国法条文" not in system
    assert run.summary["foreign_law"]["skipped"]


def test_unknown_jurisdiction_falls_back_to_china_not_crash() -> None:
    assert playbook_service.normalise_jurisdiction("th") == Jurisdiction.TH
    assert playbook_service.normalise_jurisdiction("泰国") == Jurisdiction.TH
    assert playbook_service.normalise_jurisdiction("瞎写") == Jurisdiction.CN
    assert playbook_service.normalise_jurisdiction(None) == Jurisdiction.CN


# ── 截断抢救（真机踩过：模型先写分析，JSON 被切在半句）─────────────────


def test_salvages_findings_from_truncated_output() -> None:
    raw = (
        "Let me analyze this contract carefully.\n\n"
        '{"subject_profile": ["泰国土地"], "relations": [], "findings": ['
        '{"rule_key": "th.lease_term_limit", "verdict": "deviation", "severity": "high", '
        '"title": "租期超上限", "reason": "CCC 540", "quote": "50 年"},'
        '{"rule_key": "th.vat_rate", "verdict": "deviation", "severity": "medium", "title": "税率写错",'
    )
    produced = review_pipeline.parse_review_output(raw)
    assert [f["rule_key"] for f in produced.findings] == ["th.lease_term_limit"]


def test_truncated_output_without_complete_finding_yields_nothing() -> None:
    raw = '{"subject_profile": ["泰国土地"], "findings": [{"rule_key": "th.vat_rate", "verdict": "dev'
    assert review_pipeline.parse_review_output(raw).findings == []


def test_wellformed_output_is_unaffected_by_salvage_path() -> None:
    produced = review_pipeline.parse_review_output(
        '{"subject_profile": ["a"], "relations": [{"relation": "x", "why": "y", "risk": "z"}],'
        ' "findings": [{"rule_key": "th.vat_rate"}]}'
    )
    assert produced.subject_profile == ["a"]
    assert produced.relations[0]["relation"] == "x"
    assert [f["rule_key"] for f in produced.findings] == ["th.vat_rate"]
