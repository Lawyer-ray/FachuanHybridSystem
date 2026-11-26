"""审查模型：坐标、七态状态机、锚点失效、口径统计。

## 每条断言对应的真实后果

| 断言 | 不守会怎样 |
|---|---|
| run/finding 挂在 (kind, owner_id, subpath) 上 | 结果挂不回文件，只能另开一个页面看——旧的 `ReviewTask` 就是这么坏的 |
| 一次审查不产生第二份 docx | 律师要在两份文件之间对账，且客户交付时不知道该给哪份 |
| 终态不可改写 | 历史结论被就地改掉，「当时为什么这么判」再也说不清 |
| 驳回必须带理由码 | 自由文本没法统计，误报率永远是糊涂账 |
| 锚点失效 → `stale` 且文件零改动 | 改到「最像的那一段」= 错位改字，法律文书不能容忍 |
| `not_applicable` 不进覆盖率分母 | 6 条可审条款的框架协议被算成 12 分 |
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from docx import Document

from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService
from apps.doc_workspace.models import (
    Delivery,
    Finding,
    FindingKind,
    FindingStatus,
    RejectReason,
    ReviewRun,
    RunStatus,
    Severity,
    Verdict,
)
from apps.doc_workspace.services import review_model

pytestmark = pytest.mark.django_db

KIND = "contract"
OWNER_ID = 714
SUBPATH = "1-合同/a.docx"
P1 = "甲方愿意支付人民币壹万元整。"
P2 = "乙方应当在三十日内完成交付。"


class _Service(BoundFolderBrowseService):
    root: Path

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def _require_access(self, **_kw: Any) -> None:
        return None

    def _local_root(self, _owner_id: int) -> Path:
        return self.root


def _docx() -> bytes:
    doc = Document()
    doc.add_paragraph(P1)
    doc.add_paragraph(P2)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def folder_root(tmp_path: Path) -> Path:
    d = tmp_path / "1-合同"
    d.mkdir(parents=True)
    (d / "a.docx").write_bytes(_docx())
    return tmp_path


@pytest.fixture
def wired(monkeypatch: Any, folder_root: Path) -> Path:
    from apps.contracts.services.contract.integrations import folder_browse_service as mod

    monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Service(folder_root))
    return folder_root


def _run(**kw: Any) -> ReviewRun:
    defaults = {"owner_kind": KIND, "owner_id": OWNER_ID, "subpath": SUBPATH, "status": RunStatus.DONE}
    defaults.update(kw)
    return ReviewRun.objects.create(**defaults)


def _finding(run: ReviewRun, **kw: Any) -> Finding:
    defaults = {
        "run": run,
        "ordinal": 0,
        "verdict": Verdict.DEVIATION,
        "severity": Severity.HIGH,
        "kind": FindingKind.RISK,
        "quote": P1,
        "title": "违约金无上限",
        "reason": "建议设上限",
        "suggestion_original": P1,
        "suggestion_replacement": "甲方同意支付人民币壹万元整。",
        "delivery": Delivery.REVISION,
    }
    defaults.update(kw)
    return Finding.objects.create(**defaults)


def _disk(root: Path) -> bytes:
    return (root / "1-合同" / "a.docx").read_bytes()


def _document_xml(root: Path) -> str:
    """docx 是 ZIP，`w:ins` 在压缩后不会以明文出现在字节里，必须解包看。"""
    import zipfile

    with zipfile.ZipFile(root / "1-合同" / "a.docx") as zf:
        return zf.read("word/document.xml").decode("utf-8")


class TestCoordinates:
    def test_findings_are_reachable_from_the_file(self) -> None:
        run = _run()
        _finding(run)
        _finding(run, ordinal=1)

        same_file = ReviewRun.objects.filter(owner_kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH)
        assert same_file.count() == 1
        assert same_file.first().findings.count() == 2

    def test_review_creates_no_second_docx(self, wired: Path) -> None:
        """审查与落笔都不该在文件夹里长出新文件。"""
        before = sorted(p.relative_to(wired / "1-合同").as_posix() for p in (wired / "1-合同").rglob("*"))
        run = _run()
        finding = _finding(run)
        review_model.apply_finding(finding)

        after = sorted(p.relative_to(wired / "1-合同").as_posix() for p in (wired / "1-合同").rglob("*"))
        assert after == before == ["a.docx"]


class TestStateMachine:
    def test_every_declared_transition_is_legal(self) -> None:
        """`ALLOWED` 里声明的每一条迁移都必须真的能走通。"""
        for from_status, targets in review_model.ALLOWED.items():
            for to_status in targets:
                run = _run()
                finding = _finding(run, status=from_status)
                if to_status == FindingStatus.REJECTED:
                    review_model.reject(finding, reason_code=RejectReason.COMMERCIAL)
                else:
                    review_model.transition(finding, to_status)
                assert finding.status == to_status, f"{from_status} → {to_status}"

    @pytest.mark.parametrize("terminal", sorted(review_model.TERMINAL))
    def test_terminal_states_are_immutable(self, terminal: str) -> None:
        """终态不可再变：要改结论就新建一条，历史不能被就地改写。"""
        finding = _finding(_run(), status=terminal)
        with pytest.raises(review_model.IllegalTransition):
            review_model.transition(finding, FindingStatus.PROPOSED)

    def test_illegal_transition_from_proposed(self) -> None:
        finding = _finding(_run())
        with pytest.raises(review_model.IllegalTransition):
            review_model.transition(finding, FindingStatus.PROPOSED)  # 自己到自己也不行

    def test_reject_requires_reason_code(self) -> None:
        finding = _finding(_run())
        with pytest.raises(ValueError, match="理由码"):
            review_model.reject(finding, reason_code="")

    def test_reject_rejects_unknown_code(self) -> None:
        finding = _finding(_run())
        with pytest.raises(ValueError, match="未知驳回理由码"):
            review_model.reject(finding, reason_code="随便写一个")

    def test_reject_records_code_and_note(self) -> None:
        finding = _finding(_run())
        review_model.reject(finding, reason_code=RejectReason.COMMERCIAL, note="客户谈判筹码")
        finding.refresh_from_db()
        assert finding.status == FindingStatus.REJECTED
        assert finding.reject_reason_code == RejectReason.COMMERCIAL
        assert finding.reject_note == "客户谈判筹码"
        assert finding.decided_at is not None


class TestApplyFinding:
    def test_revision_delivery_lands_and_accepts(self, wired: Path) -> None:
        finding = _finding(_run())
        result = review_model.apply_finding(finding)

        assert result["applied"] is True
        finding.refresh_from_db()
        assert finding.status == FindingStatus.ACCEPTED
        assert finding.docx_rev_ids, "落笔后必须记住修订号，否则无法按结论撤回"
        assert "<w:ins" in _document_xml(wired)

    def test_missing_anchor_marks_stale_and_writes_nothing(self, wired: Path) -> None:
        """锚点失效：状态置 stale，**文件一个字节都不动**。"""
        before = _disk(wired)
        finding = _finding(_run(), suggestion_original="这句话在文档里不存在", quote="这句话在文档里不存在")

        result = review_model.apply_finding(finding)

        assert result["applied"] is False
        assert result.get("stale") is True
        finding.refresh_from_db()
        assert finding.status == FindingStatus.STALE
        assert _disk(wired) == before

    def test_stale_can_be_retried_after_reanchoring(self, wired: Path) -> None:
        """stale 不是终态：律师重新框选后还能再来一次。"""
        finding = _finding(_run(), suggestion_original="不存在", quote="不存在")
        review_model.apply_finding(finding)

        finding.suggestion_original = P1
        finding.save(update_fields=["suggestion_original"])
        review_model.transition(finding, FindingStatus.PROPOSED)

        result = review_model.apply_finding(finding)
        assert result["applied"] is True
        finding.refresh_from_db()
        assert finding.status == FindingStatus.ACCEPTED

    def test_comment_delivery_writes_comment_without_touching_text(self, wired: Path) -> None:
        before_text = _disk(wired)
        finding = _finding(
            _run(),
            delivery=Delivery.COMMENT,
            suggestion_original="",
            suggestion_replacement="",
            suggestion_note="违约金没有上限，是否接受取决于谈判地位。",
            quote=P1,
        )

        result = review_model.apply_finding(finding)

        assert result["applied"] is True
        finding.refresh_from_db()
        assert finding.status == FindingStatus.ACCEPTED
        assert finding.comment_ids
        # 批注不改正文
        doc = Document(io.BytesIO(_disk(wired)))
        assert doc.paragraphs[0].text == P1
        assert before_text != _disk(wired)  # 但文件确实变了（多了批注）

    def test_list_only_is_accepted_without_writing(self, wired: Path) -> None:
        before = _disk(wired)
        finding = _finding(_run(), delivery=Delivery.LIST_ONLY, suggestion_original="", suggestion_replacement="")

        result = review_model.apply_finding(finding)

        assert result["applied"] is False
        finding.refresh_from_db()
        assert finding.status == FindingStatus.ACCEPTED
        assert _disk(wired) == before

    def test_manual_trace_is_not_reapplied(self, wired: Path) -> None:
        before = _disk(wired)
        finding = _finding(_run(), kind=FindingKind.MANUAL)
        result = review_model.apply_finding(finding)
        assert result["applied"] is False
        assert _disk(wired) == before


class TestMetrics:
    def test_not_applicable_excluded_from_coverage_denominator(self) -> None:
        run = _run()
        for i in range(40):
            _finding(run, ordinal=i, verdict=Verdict.NOT_APPLICABLE, severity=Severity.LOW)
        for i in range(6):
            _finding(run, ordinal=100 + i, verdict=Verdict.COMPLIANT, severity=Severity.LOW)

        m = review_model.run_metrics(run)

        assert m["total"] == 46
        assert m["applicable"] == 6
        assert m["compliant"] == 6
        # 若把 not_applicable 算进分母，这里会是 6/46 = 0.13
        assert m["coverage"] == 1.0

    def test_false_positive_rate_uses_only_the_false_positive_code(self) -> None:
        run = _run()
        a = _finding(run, ordinal=0)
        b = _finding(run, ordinal=1)
        c = _finding(run, ordinal=2)
        d = _finding(run, ordinal=3)
        review_model.reject(a, reason_code=RejectReason.FALSE_POSITIVE)
        review_model.reject(b, reason_code=RejectReason.COMMERCIAL)
        review_model.accept(c)
        review_model.accept(d)

        m = review_model.run_metrics(run)

        assert m["reviewed"] == 4
        assert m["false_positives"] == 1
        assert m["false_positive_rate"] == 0.25
        assert m["accept_rate"] == 0.5

    def test_rates_are_zero_without_reviews(self) -> None:
        m = review_model.run_metrics(_run())
        assert m["reviewed"] == 0
        assert m["accept_rate"] == 0.0
        assert m["false_positive_rate"] == 0.0

    def test_top_high_takes_at_most_three(self) -> None:
        run = _run()
        for i in range(5):
            _finding(run, ordinal=i, severity=Severity.HIGH)
        _finding(run, ordinal=9, severity=Severity.MEDIUM)
        m = review_model.run_metrics(run)
        assert len(m["top_high"]) == 3


class TestRunLifecycle:
    def test_finish_run_writes_summary(self) -> None:
        run = _run(status=RunStatus.RUNNING)
        _finding(run)
        review_model.finish_run(run)
        run.refresh_from_db()
        assert run.status == RunStatus.DONE
        assert run.finished_at is not None
        assert run.summary["total"] == 1

    def test_supersede_marks_older_runs(self) -> None:
        """同一份文件上更早的未完成轮次必须被取代，否则清单里一半是上一版的建议。"""
        old = _run(status=RunStatus.DONE)
        new = _run()
        assert review_model.supersede_previous_runs(new) == 1
        old.refresh_from_db()
        assert old.status == RunStatus.SUPERSEDED

    def test_supersede_does_not_touch_other_files(self) -> None:
        other = _run(subpath="2-其他/b.docx", status=RunStatus.DONE)
        new = _run()
        review_model.supersede_previous_runs(new)
        other.refresh_from_db()
        assert other.status == RunStatus.DONE
