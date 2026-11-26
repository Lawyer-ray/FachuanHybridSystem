"""审查执行链：立场对齐、标准快照、三道闸。

## 每条断言对应的真实后果

| 断言 | 不守会怎样 |
|---|---|
| 换立场 → 严重度/方向翻转 | 「换个立场重跑，结果时对时不对」——立场退化成一句 prompt 装饰 |
| `not_applicable` 不进分母 | 6 条可审条款的框架协议被算成 12 分 |
| 标准改版不篡改历史 run 的快照 | 客户问「当时为什么说没问题」，答不出来 |
| 觉察到自创检查项就丢 | 模型超范围发挥，闸一拦不住的表外条目混进清单 |
| format 占比 ≤ 20% | 60 条里 40 条「建议措辞更严谨」，律师把整份清单当噪音 |
| 主清单 ≤ 25 条 | 同上，只是形式不同 |
| Top-3 必须带量化后果 | 一页纸变成「建议关注相关风险」这类空话 |
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from docx import Document

from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService
from apps.doc_workspace.models import Beneficiary, FindingKind, PlaybookRule, Severity, Stance, Verdict
from apps.doc_workspace.services import playbook_service, review_pipeline

pytestmark = pytest.mark.django_db

KIND = "contract"
OWNER_ID = 815
SUBPATH = "1-合同/a.docx"
P1 = "甲方愿意支付人民币壹万元整。"


class _Service(BoundFolderBrowseService):
    root: Path

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def _require_access(self, **_kw: Any) -> None:
        return None

    def _local_root(self, _owner_id: int) -> Path:
        return self.root


@pytest.fixture
def wired(monkeypatch: Any, tmp_path: Path) -> Path:
    d = tmp_path / "1-合同"
    d.mkdir(parents=True)
    doc = Document()
    doc.add_paragraph(P1)
    buf = io.BytesIO()
    doc.save(buf)
    (d / "a.docx").write_bytes(buf.getvalue())

    from apps.contracts.services.contract.integrations import folder_browse_service as mod

    monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Service(tmp_path))
    return tmp_path


def _caller(payload: list[dict[str, Any]]) -> review_pipeline.LLMCaller:
    return lambda _messages: json.dumps(payload, ensure_ascii=False)


def _one_finding(rule_key: str, **kw: Any) -> dict[str, Any]:
    item = {
        "rule_key": rule_key,
        "verdict": Verdict.MISSING,
        "severity": Severity.HIGH,
        "quote": "",
        "title": "缺少违约金上限",
        "reason": "无上限的违约金可能超出实际损失",
        "impact": "一旦违约可能被判赔超过合同价款 30%",
        "suggestion_original": P1,
        "suggestion_replacement": "甲方同意支付人民币壹万元整，违约金以合同总价款的 20% 为限。",
    }
    item.update(kw)
    return item


class TestStanceFlipsDirection:
    def test_same_clause_flips_severity_between_stances(self, wired: Path) -> None:
        """同一条「保护乙方」的标准：站乙方是高风险，站甲方则降一档。"""
        payload = [_one_finding("breach.liquidated_damages_cap")]
        book = playbook_service.resolve(contract_type="", stance=Stance.NEUTRAL)
        # 把这条规则改成「保护乙方」，以构造方向明确的场景
        PlaybookRule.objects.filter(playbook=book, rule_key="breach.liquidated_damages_cap").update(
            beneficiary=Beneficiary.PARTY_B
        )

        run_b = review_pipeline.run_review(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            stance=Stance.PARTY_B,
            playbook=book,
            caller=_caller(payload),
        )
        run_a = review_pipeline.run_review(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            stance=Stance.PARTY_A,
            playbook=book,
            caller=_caller(payload),
        )

        finding_b = run_b.findings.get(rule_key="breach.liquidated_damages_cap")
        finding_a = run_a.findings.get(rule_key="breach.liquidated_damages_cap")
        assert finding_b.severity == Severity.HIGH
        assert finding_a.severity == Severity.MEDIUM
        assert finding_a.severity != finding_b.severity

    def test_neutral_rule_is_not_adjusted(self) -> None:
        assert review_pipeline.align_to_stance(
            beneficiary=Beneficiary.NEUTRAL, stance=Stance.PARTY_A, verdict=Verdict.MISSING, severity=Severity.HIGH
        ) == (Verdict.MISSING, Severity.HIGH, "neutral")

    def test_favor_us_keeps_severity(self) -> None:
        verdict, severity, direction = review_pipeline.align_to_stance(
            beneficiary=Beneficiary.PARTY_A, stance=Stance.PARTY_A, verdict=Verdict.MISSING, severity=Severity.HIGH
        )
        assert (verdict, severity, direction) == (Verdict.MISSING, Severity.HIGH, "favor_us")

    def test_favor_them_downgrades_one_step_not_more(self) -> None:
        for given, expected in ((Severity.HIGH, Severity.MEDIUM), (Severity.MEDIUM, Severity.LOW), (Severity.LOW, Severity.LOW)):
            _v, severity, direction = review_pipeline.align_to_stance(
                beneficiary=Beneficiary.PARTY_B, stance=Stance.PARTY_A, verdict=Verdict.DEVIATION, severity=given
            )
            assert severity == expected, given
            assert direction == "favor_them"


class TestPlaybookSnapshot:
    def test_old_run_keeps_its_standard_after_playbook_changes(self, wired: Path) -> None:
        """标准改版不得篡改历史结论：快照存在 run 上，不靠外键回查。"""
        book = playbook_service.resolve(contract_type="", stance=Stance.NEUTRAL)
        old_standard = PlaybookRule.objects.get(playbook=book, rule_key="dispute.jurisdiction").standard_text

        run_old = review_pipeline.run_review(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, playbook=book, caller=_caller([])
        )

        PlaybookRule.objects.filter(playbook=book, rule_key="dispute.jurisdiction").update(
            standard_text="改成新的管辖标准"
        )
        new_book = playbook_service.bump_version(book, note="改管辖标准")

        run_new = review_pipeline.run_review(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, playbook=new_book, caller=_caller([])
        )

        old_snapshot = {r["rule_key"]: r for r in run_old.playbook_snapshot}
        new_snapshot = {r["rule_key"]: r for r in run_new.playbook_snapshot}
        assert old_snapshot["dispute.jurisdiction"]["standard_text"] == old_standard
        assert new_snapshot["dispute.jurisdiction"]["standard_text"] == "改成新的管辖标准"
        assert run_new.playbook_version == new_book.version

    def test_version_bump_copies_every_rule(self) -> None:
        book = playbook_service.ensure_builtin()
        new = playbook_service.bump_version(book)
        assert new.version == book.version + 1
        assert new.rules.count() == book.rules.count()

    def test_resolve_prefers_narrower_playbook(self) -> None:
        specific = playbook_service.ensure_builtin(contract_type="租赁", stance=Stance.PARTY_A)
        assert playbook_service.resolve(contract_type="租赁", stance=Stance.PARTY_A).id == specific.id
        # 没有「租赁 + 中立」时退到「租赁 + 甲方」…再退到通用
        assert playbook_service.resolve(contract_type="买卖", stance=Stance.PARTY_B).contract_type in ("买卖", "")


class TestCoverageDenominator:
    def test_not_applicable_excluded(self, wired: Path) -> None:
        payload = [
            _one_finding("subject.identity", verdict=Verdict.NOT_APPLICABLE),
            _one_finding("subject.capacity", verdict=Verdict.NOT_APPLICABLE),
            _one_finding("subject.amount_consistency", verdict=Verdict.COMPLIANT),
        ]
        run = review_pipeline.run_review(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, caller=_caller(payload)
        )
        assert run.summary["applicable"] == 1
        assert run.summary["coverage"] == 1.0


class TestSelfInventedRulesDropped:
    def test_unknown_rule_key_is_discarded(self, wired: Path) -> None:
        payload = [_one_finding("我自创的检查项"), _one_finding("subject.identity")]
        run = review_pipeline.run_review(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, caller=_caller(payload)
        )
        keys = list(run.findings.values_list("rule_key", flat=True))
        assert keys == ["subject.identity"]


class TestGates:
    def _item(self, **kw: Any) -> dict[str, Any]:
        base = {
            "kind": FindingKind.RISK,
            "severity": Severity.MEDIUM,
            "verdict": Verdict.DEVIATION,
            "title": "t",
            "reason": "r",
            "impact": "损失 10 万元",
            "rule_key": "k",
        }
        base.update(kw)
        return base

    def test_format_ratio_is_capped(self) -> None:
        items = [self._item(kind=FindingKind.FORMAT, severity=Severity.LOW) for _ in range(8)]
        items += [self._item() for _ in range(2)]

        kept, report = review_pipeline.enforce_gates(items)

        assert report.format_ratio_before == 0.8
        assert report.format_ratio_after <= review_pipeline.FORMAT_RATIO_MAX
        assert report.dropped_format > 0
        assert len(kept) < len(items)

    def test_item_cap_keeps_highest_severity(self) -> None:
        items = [self._item(severity=Severity.LOW) for _ in range(30)]
        items.append(self._item(severity=Severity.HIGH, title="最严重"))
        kept, report = review_pipeline.enforce_gates(items)

        assert report.kept == review_pipeline.MAX_MAIN_ITEMS
        titles = [i["title"] for i in kept]
        assert "最严重" in titles, "条数闸必须按严重度保留，不能砍尾部"

    def test_top_requires_quantified_consequence(self) -> None:
        items = [
            self._item(severity=Severity.HIGH, title="有数字", impact="可能被判赔 500 万元"),
            self._item(severity=Severity.HIGH, title="空话", impact="建议关注相关风险"),
        ]
        _kept, report = review_pipeline.enforce_gates(items)

        assert report.top == ["有数字"]
        assert report.dropped_no_impact_from_top == 1

    def test_quantified_detector(self) -> None:
        assert review_pipeline.has_quantified_consequence("超过合同总价款的 20%")
        assert review_pipeline.has_quantified_consequence("逾期 30 日")
        assert review_pipeline.has_quantified_consequence("损失约 5 万元")
        assert not review_pipeline.has_quantified_consequence("建议关注相关风险")
        assert not review_pipeline.has_quantified_consequence("")


class TestRunReviewShape:
    def test_review_creates_run_without_second_docx(self, wired: Path) -> None:
        before = sorted(p.relative_to(wired / "1-合同").as_posix() for p in (wired / "1-合同").rglob("*"))
        run = review_pipeline.run_review(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            caller=_caller([_one_finding("performance.deadline")]),
        )
        after = sorted(p.relative_to(wired / "1-合同").as_posix() for p in (wired / "1-合同").rglob("*"))

        assert run.findings.count() == 1
        assert after == before == ["a.docx"]

    def test_llm_failure_marks_run_failed(self, wired: Path) -> None:
        def boom(_messages: list[dict[str, str]]) -> str:
            raise RuntimeError("模型挂了")

        run = review_pipeline.run_review(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, caller=boom
        )
        assert run.status == "failed"
        assert "模型挂了" in run.error_message

    def test_garbage_output_marks_done_with_zero_findings(self, wired: Path) -> None:
        run = review_pipeline.run_review(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, caller=lambda _m: "对不起我无法完成"
        )
        assert run.status == "done"
        assert run.findings.count() == 0

    def test_findings_delivery_is_derived_from_payload(self, wired: Path) -> None:
        payload = [
            _one_finding("subject.identity"),
            _one_finding(
                "performance.deadline",
                suggestion_original="",
                suggestion_replacement="",
                suggestion_note="建议明确起算点",
            ),
            _one_finding("confidentiality.scope", suggestion_original="", suggestion_replacement=""),
        ]
        run = review_pipeline.run_review(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, caller=_caller(payload)
        )
        by_rule = {f.rule_key: f for f in run.findings.all()}
        assert by_rule["subject.identity"].delivery == "revision"
        assert by_rule["performance.deadline"].delivery == "comment"
        assert by_rule["confidentiality.scope"].delivery == "list_only"
