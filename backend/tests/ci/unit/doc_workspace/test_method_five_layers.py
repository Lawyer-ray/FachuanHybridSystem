"""五层方法论的落地断言：规则四类、阶段三段、风险四维、条款的出生证明。

来源：一位法务总的合同审查方法图（国有建设用地使用权转让合同为例）。它对我们
模型提了三个结构性要求，本文件逐条钉住：

1. **规则有类别**，且 `mandatory` 必须免疫立场降权与过度审查闸
   —— 这是修掉的一处真实漏判路径（把「抵押未解除不得转让」当可谈的商业建议）；
2. **阶段有三段**，且零结论的阶段也要出现（覆盖证明，不是空白）；
3. **风险有四个来源**，结论必须标「据法条 / 据类案 / 据推演 / 据标的特性」。

另外钉住几处**法律口径**（据复核结论修正过的）：抵押转让已由《民法典》第406条
取代旧第191条；承租人优先购买权被妨害只能索赔（不是无效）；土壤修复是法定行政
义务（不是「从上游合同继承」）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from apps.doc_workspace.models import (
    Consequence,
    Finding,
    FindingStatus,
    ReviewRun,
    RiskSource,
    RuleClass,
    Severity,
    SourceWeight,
    Stage,
)
from apps.doc_workspace.services import playbook_service, review_model, review_pipeline

pytestmark = pytest.mark.django_db

OWNER_ID = 1421
SUBPATH = "1-合同/a.docx"


def _run(**kw: Any) -> ReviewRun:
    defaults = {
        "owner_kind": "contract",
        "owner_id": OWNER_ID,
        "subpath": SUBPATH,
        "status": "done",
        "stance": "neutral",
        "contract_type": "",
        "playbook_snapshot": playbook_service.snapshot_rules(playbook_service.ensure_builtin()),
        "playbook_version": playbook_service.BUILTIN_VERSION,
    }
    defaults.update(kw)
    return ReviewRun.objects.create(**defaults)


def _item(**kw: Any) -> dict[str, Any]:
    base = {
        "kind": "risk",
        "severity": Severity.MEDIUM,
        "verdict": "deviation",
        "title": "t",
        "reason": "r",
        "impact": "损失 10 万元",
        "rule_key": "k",
        "rule_class": RuleClass.CONTRACTUAL,
        "stage": Stage.GENERAL,
        "risk_source": RiskSource.STATUTE,
        "source_weight": SourceWeight.CORE,
        "consequence": Consequence.BREACH,
    }
    base.update(kw)
    return base


class TestMandatoryImmunity:
    """强制性规则不因立场降档、不被任何一道闸丢弃。"""

    @pytest.mark.parametrize("severity", [Severity.HIGH, Severity.MEDIUM, Severity.LOW])
    def test_stance_alignment_never_downgrades_mandatory(self, severity: str) -> None:
        verdict, kept_severity, direction = review_pipeline.align_to_stance(
            beneficiary="party_b",
            stance="party_a",
            verdict="missing",
            severity=severity,
            rule_class=RuleClass.MANDATORY,
        )
        assert kept_severity == severity
        assert direction == "mandatory"

    def test_contractual_still_downgrades(self) -> None:
        """免疫只给 mandatory，别把「可以谈」也一起免除。"""
        _v, severity, direction = review_pipeline.align_to_stance(
            beneficiary="party_b",
            stance="party_a",
            verdict="deviation",
            severity=Severity.HIGH,
            rule_class=RuleClass.CONTRACTUAL,
        )
        assert severity == Severity.MEDIUM
        assert direction == "favor_them"

    def test_cap_keeps_mandatory_even_when_low_severity(self) -> None:
        """条数闸按严重度截断时，低危的强制性条目也不能被截掉。"""
        items = [_item(severity=Severity.HIGH) for _ in range(30)]
        items.append(
            _item(
                severity=Severity.LOW,
                rule_class=RuleClass.MANDATORY,
                title="集体土地擅自入市",
                impact="合同无效，损失全部价款 500 万元",
            )
        )
        kept, report = review_pipeline.enforce_gates(items)
        titles = [i["title"] for i in kept]
        assert "集体土地擅自入市" in titles
        assert report.mandatory_protected == 1
        assert report.kept <= review_pipeline.MAX_MAIN_ITEMS + 1  # 强制性占位，不被这条上限吃掉

    def test_format_gate_never_drops_mandatory(self) -> None:
        items = [_item(kind="format", severity=Severity.LOW) for _ in range(8)]
        items.append(_item(kind="format", rule_class=RuleClass.MANDATORY, title="必须保留"))
        kept, _report = review_pipeline.enforce_gates(items)
        assert any(i["title"] == "必须保留" for i in kept)

    def test_severity_of_mandatory_comes_from_rule_not_model(self) -> None:
        """模型说「影响不大」不能把「可能无效」降成低危。"""
        rule = {
            "rule_key": "land.collective_land",
            "clause_type": "转让资格",
            "standard_text": "…",
            "severity_if_missing": Severity.HIGH,
            "rule_class": RuleClass.MANDATORY,
            "stage": Stage.BEFORE,
            "consequence": Consequence.INVALID,
            "beneficiary": "neutral",
        }
        item = review_pipeline._normalize_item(  # noqa: SLF001
            {"rule_key": "land.collective_land", "verdict": "missing", "severity": "low", "title": "t"},
            rules_by_key={"land.collective_land": rule},
            stance="neutral",
        )
        assert item is not None
        assert item["severity"] == Severity.HIGH
        assert item["consequence"] == Consequence.INVALID


class TestParseReviewOutput:
    def test_new_contract_object(self) -> None:
        raw = json.dumps(
            {
                "subject_profile": ["工业用地", "带产业监管"],
                "relations": [{"relation": "抵押权人", "why": "带押转让", "risk": "过户被拒"}],
                "findings": [{"rule_key": "a", "verdict": "missing"}],
            },
            ensure_ascii=False,
        )
        out = review_pipeline.parse_review_output(raw)
        assert out.subject_profile == ["工业用地", "带产业监管"]
        assert out.relations[0]["relation"] == "抵押权人"
        assert len(out.findings) == 1

    def test_legacy_array(self) -> None:
        out = review_pipeline.parse_review_output('[{"rule_key":"a"},{"rule_key":"b"}]')
        assert len(out.findings) == 2
        assert out.subject_profile == []

    def test_single_element_array_is_not_mistaken_for_object(self) -> None:
        """回归：`[{...}]` 曾被内层对象正则误判成新契约，导致**整份结论丢失**。"""
        out = review_pipeline.parse_review_output('[{"rule_key":"only-one"}]')
        assert len(out.findings) == 1
        assert out.findings[0]["rule_key"] == "only-one"

    def test_fenced_json(self) -> None:
        raw = '```json\n{"findings":[{"rule_key":"x"}]}\n```'
        assert len(review_pipeline.parse_review_output(raw).findings) == 1

    def test_garbage(self) -> None:
        out = review_pipeline.parse_review_output("对不起我无法完成")
        assert out.findings == []


class TestStageAndSourcePersistence:
    def _execute(self, run: ReviewRun, payload: dict[str, Any] | list[Any]) -> ReviewRun:
        return review_pipeline.execute_run(
            run, caller=lambda _m: json.dumps(payload, ensure_ascii=False), text="第一条 甲方支付价款。"
        )

    def test_new_fields_are_persisted(self) -> None:
        run = _run()
        self._execute(
            run,
            {
                "findings": [
                    {
                        "rule_key": "dispute.jurisdiction",
                        "verdict": "missing",
                        "severity": "high",
                        "title": "管辖未约定",
                        "reason": "争议解决不明",
                        "impact": "诉讼成本增加 3 万元",
                        "risk_source": "case",
                        "source_weight": "supporting",
                    }
                ]
            },
        )
        finding = run.findings.get()
        assert finding.rule_class == RuleClass.CONTRACTUAL
        assert finding.stage == Stage.GENERAL  # 来自规则快照，不是模型
        assert finding.risk_source == RiskSource.CASE
        assert finding.source_weight == SourceWeight.SUPPORTING
        assert finding.consequence == Consequence.BREACH

    def test_summary_has_all_four_stages_even_when_empty(self) -> None:
        run = _run()
        self._execute(run, {"findings": []})
        stages = run.summary["stages"]
        assert set(stages) == set(Stage.values)
        assert all(bucket["total"] == 0 for bucket in stages.values())

    def test_summary_records_profile_and_relations(self) -> None:
        run = _run()
        self._execute(
            run,
            {
                "subject_profile": ["工业用地", "历史污染"],
                "relations": [{"relation": "承租人", "why": "优先购买权", "risk": "交易被索赔阻滞"}],
                "findings": [],
            },
        )
        assert run.summary["subject_profile"] == ["工业用地", "历史污染"]
        assert run.summary["relations"][0]["relation"] == "承租人"


class TestMetricsWithStages:
    def test_stage_rollup_counts(self) -> None:
        run = _run()
        Finding.objects.create(
            run=run, ordinal=0, rule_key="a", title="t", stage=Stage.BEFORE, severity=Severity.HIGH,
            rule_class=RuleClass.MANDATORY, consequence=Consequence.INVALID,
        )
        Finding.objects.create(
            run=run, ordinal=1, rule_key="b", title="t2", stage=Stage.DURING, severity=Severity.LOW,
            status=FindingStatus.REJECTED,
        )
        rollup = review_model.stage_rollup(run=run)
        assert rollup[Stage.BEFORE]["total"] == 1
        assert rollup[Stage.BEFORE]["high"] == 1
        assert rollup[Stage.DURING]["total"] == 1
        assert rollup[Stage.AFTER]["total"] == 0  # 零也要在
        assert rollup[Stage.DURING]["proposed"] == 0  # 已驳回

    def test_metrics_count_mandatory_separately(self) -> None:
        run = _run()
        Finding.objects.create(
            run=run, ordinal=0, rule_key="m", title="强制", rule_class=RuleClass.MANDATORY,
            consequence=Consequence.INVALID,
        )
        Finding.objects.create(run=run, ordinal=1, rule_key="c", title="普通")
        m = review_model.run_metrics(run)
        assert m["mandatory_total"] == 1
        assert m["mandatory_open"] == 1


class TestLandRulesLegalCaliber:
    """规则库的法律口径（据复核结论修正过，写错比不写更危险）。"""

    def _rules(self) -> dict[str, dict[str, Any]]:
        book = playbook_service.ensure_builtin(contract_type="土地使用权转让")
        return {r["rule_key"]: r for r in playbook_service.snapshot_rules(book)}

    def test_land_playbook_has_twelve_rules(self) -> None:
        assert len(self._rules()) >= 12

    def test_mortgage_rule_uses_civil_code_406_terminology(self) -> None:
        rule = self._rules()["land.mortgage_transfer_restriction"]
        assert "406" in rule["legal_basis"]
        # 旧物权法第191条口径（抵押期间一律不得转让）已被取代，不能写回去
        assert "抵押期间**可以**转让" in rule["standard_text"]
        assert rule["consequence"] == Consequence.UNENFORCEABLE

    def test_seizure_is_split_from_mortgage(self) -> None:
        rules = self._rules()
        assert "land.seizure_or_title_dispute" in rules
        assert rules["land.seizure_or_title_dispute"]["consequence"] == Consequence.ADMINISTRATIVE

    def test_lessee_preemption_is_damages_not_invalidity(self) -> None:
        rule = self._rules()["land.preemption.lessee"]
        assert rule["rule_class"] == RuleClass.CONTRACTUAL
        assert rule["consequence"] == Consequence.BREACH
        assert "赔偿" in rule["standard_text"]
        # 共有人档才是真效力风险
        assert self._rules()["land.preemption.coowner"]["consequence"] == Consequence.INVALID

    def test_soil_remediation_is_administrative_duty(self) -> None:
        rule = self._rules()["land.soil_remediation"]
        assert rule["rule_class"] == RuleClass.MANDATORY
        assert rule["consequence"] == Consequence.ADMINISTRATIVE
        # 合同承继面向另立一条
        assert self._rules()["risk.soil_liability_succession"]["rule_class"] == RuleClass.INHERITED

    def test_investment_ratio_does_not_overstate_invalidity(self) -> None:
        rule = self._rules()["land.investment_ratio"]
        assert rule["consequence"] == Consequence.ADMINISTRATIVE
        assert "不导致合同无效" in rule["standard_text"]

    def test_collective_land_is_invalid(self) -> None:
        assert self._rules()["land.collective_land"]["consequence"] == Consequence.INVALID

    def test_grant_succession_cites_the_right_articles(self) -> None:
        rule = self._rules()["land.grant_contract_succession"]
        assert "第42条" in rule["legal_basis"]
        assert "第555条" in rule["legal_basis"]

    def test_builtin_version_was_bumped(self) -> None:
        """改了 standard_text / legal_basis 就必须 bump：否则历史快照对不上口径。"""
        assert playbook_service.BUILTIN_VERSION >= 2


class TestPromptCarriesMethod:
    def test_prompt_asks_for_profile_relations_and_sources(self) -> None:
        rules = playbook_service.snapshot_rules(playbook_service.ensure_builtin())
        messages = review_pipeline.build_prompt(
            rules=rules, contract_text="第一条 甲方支付价款。", stance="party_a", contract_type="土地使用权转让"
        )
        system = messages[0]["content"]
        assert "subject_profile" in system
        assert "relations" in system
        assert "risk_source" in system
        assert "先展开关系" in system
        assert "mandatory" in system

    def test_report_leads_with_mandatory_items(self, tmp_path: Path) -> None:  # noqa: ARG002
        run = _run()
        Finding.objects.create(
            run=run, ordinal=0, rule_key="land.collective_land", title="集体土地擅自入市",
            rule_class=RuleClass.MANDATORY, severity=Severity.HIGH,
            consequence=Consequence.INVALID, clause_type="转让资格",
            legal_basis="《土地管理法》第63条",
        )
        for i in range(1, 6):
            Finding.objects.create(run=run, ordinal=i, rule_key=f"x{i}", title=f"普通{i}")
        md = review_pipeline.build_top_report(run)
        assert "强制性事项" in md
        assert "集体土地擅自入市" in md
        assert "可能无效" in md
        assert "覆盖情况（按阶段）" in md
