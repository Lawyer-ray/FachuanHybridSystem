"""市面机制落地的三条改进（对应 `market-refresh.md` 的 I1/I2/I3）。

| 改进 | 市面来源（一手） | 我们落成了什么 |
|---|---|---|
| I1 驳回理由回流降权 | Harvey **Memory**（"AI that remembers your preferences"）；Spellbook/LegalOn **Playbooks** | `playbook_feedback`：同客户同一规则被驳回 ≥2 次 → 本轮降一档 |
| I2 一页纸带出处 + 人效口径 + AI 声明 | Definely「Every finding sourced, every change approved by you」；Luminance「75% reduction…」 | `build_top_report`：每条列 rule_key/条款/法条依据；附评估/采纳/驳回口径与参与声明 |
| I3 与历史版本对照 | Spellbook **Compare**（"Compare contracts to industry standards"） | `delta_review.compare_versions`：段落级确定性 diff |

三条都刻意**没有**做成「AI 自己决定要不要提」——判定权留给人，代码只做可复现的降权与统计。
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from docx import Document

from apps.doc_workspace.models import Finding, FindingStatus, RejectReason, ReviewRun, Severity
from apps.doc_workspace.services import (
    delta_review,
    playbook_feedback,
    playbook_service,
    review_model,
    review_pipeline,
    snapshot_service,
)

pytestmark = pytest.mark.django_db

OWNER_ID = 1320
SUBPATH = "1-合同/a.docx"


def _run(status: str = "done") -> ReviewRun:
    return ReviewRun.objects.create(
        owner_kind="contract",
        owner_id=OWNER_ID,
        subpath=SUBPATH,
        status=status,
        stance="neutral",
        contract_type="",
        playbook_snapshot=playbook_service.snapshot_rules(playbook_service.ensure_builtin()),
        playbook_version=1,
    )


def _finding(run: ReviewRun, **kw: Any) -> Finding:
    defaults = {
        "run": run,
        "ordinal": 0,
        "verdict": "deviation",
        "severity": Severity.HIGH,
        "kind": "risk",
        "rule_key": "breach.liquidated_damages_cap",
        "title": "违约金无上限",
        "reason": "可能被判赔超过实际损失",
        "suggestion_original": "甲方愿意支付人民币壹万元整。",
        "suggestion_replacement": "违约金以 20% 为限。",
        "delivery": "revision",
        "status": FindingStatus.PROPOSED,
    }
    defaults.update(kw)
    return Finding.objects.create(**defaults)


def _reject(run: ReviewRun, reason: str, **kw: Any) -> Finding:
    finding = _finding(run, **kw)
    review_model.reject(finding, reason_code=reason)
    return finding


class TestFeedbackCollect:
    def test_threshold_is_two_suppressing_rejections(self) -> None:
        run = _run()
        _reject(run, RejectReason.COMMERCIAL)
        assert playbook_feedback.collect(kind="contract", owner_id=OWNER_ID).suppressed == set()

        _reject(run, RejectReason.CLIENT_REFUSED, ordinal=1)
        fb = playbook_feedback.collect(kind="contract", owner_id=OWNER_ID)
        assert fb.suppressed == {"breach.liquidated_damages_cap"}
        assert fb.rules["breach.liquidated_damages_cap"] == 2

    @pytest.mark.parametrize("reason", [RejectReason.FALSE_POSITIVE, RejectReason.OTHER])
    def test_false_positive_and_other_do_not_suppress(self, reason: str) -> None:
        """误报是**模型错了**，该进评测指标；把它变成「别再提」等于掩盖缺陷。"""
        run = _run()
        for i in range(5):
            _reject(run, reason, ordinal=i)
        assert playbook_feedback.collect(kind="contract", owner_id=OWNER_ID).suppressed == set()

    def test_scope_is_per_client(self) -> None:
        run = _run()
        _reject(run, RejectReason.COMMERCIAL)
        _reject(run, RejectReason.COMMERCIAL, ordinal=1)
        assert playbook_feedback.collect(kind="contract", owner_id=OWNER_ID + 1).suppressed == set()

    def test_describe_mentions_rule_and_count(self) -> None:
        run = _run()
        _reject(run, RejectReason.COMMERCIAL)
        _reject(run, RejectReason.COMMERCIAL, ordinal=1)
        text = playbook_feedback.collect(kind="contract", owner_id=OWNER_ID).describe()
        assert "breach.liquidated_damages_cap" in text
        assert "2 次" in text
        assert "降一档" in text

    def test_empty_feedback_describes_nothing(self) -> None:
        assert playbook_feedback.collect(kind="contract", owner_id=OWNER_ID).describe() == ""


class TestFeedbackDowngrade:
    def test_severity_downgrades_one_step_only(self) -> None:
        fb = playbook_feedback.Feedback(rules={"r": 2}, suppressed={"r"})
        items = [
            {"rule_key": "r", "severity": Severity.HIGH},
            {"rule_key": "other", "severity": Severity.HIGH},
        ]
        playbook_feedback.apply_to_items(items, fb)
        assert items[0]["severity"] == Severity.MEDIUM
        assert items[0]["suppressed"] is True
        assert items[1]["severity"] == Severity.HIGH

    def test_item_is_kept_not_dropped(self) -> None:
        """降权≠删除：真缺了违约金上限，律师偶尔也想看到它还缺着。"""
        fb = playbook_feedback.Feedback(rules={"r": 9}, suppressed={"r"})
        items = [{"rule_key": "r", "severity": Severity.LOW}]
        out = playbook_feedback.apply_to_items(items, fb)
        assert len(out) == 1
        assert out[0]["severity"] == Severity.LOW  # 已经最低，不再降

    def test_pipeline_puts_feedback_into_prompt_and_summary(self) -> None:
        prev = _run()
        _reject(prev, RejectReason.COMMERCIAL)
        _reject(prev, RejectReason.COMMERCIAL, ordinal=1)

        seen: list[str] = []

        def caller(messages: list[dict[str, str]]) -> str:
            seen.append(messages[0]["content"])
            return json.dumps(
                [
                    {
                        "rule_key": "breach.liquidated_damages_cap",
                        "verdict": "missing",
                        "severity": "high",
                        "title": "违约金无上限",
                        "reason": "无上限",
                        "impact": "可能赔 30 万元",
                    }
                ],
                ensure_ascii=False,
            )

        doc = Document()
        doc.add_paragraph("甲方愿意支付人民币壹万元整。")
        buf = io.BytesIO()
        doc.save(buf)

        run = review_pipeline.run_review(
            kind="contract",
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            caller=caller,
            raw_bytes=buf.getvalue(),
        )

        assert "本所已多次驳回的条款" in seen[0]
        assert run.summary["feedback"]["suppressed"] == ["breach.liquidated_damages_cap"]
        # 降权生效：高危 → 中危
        assert run.findings.first().severity == Severity.MEDIUM


class TestReportWithSources:
    def test_each_item_carries_source_and_legal_basis(self) -> None:
        run = _run()
        _finding(run, clause_type="违约责任", rule_key="breach.liquidated_damages_cap", legal_basis="《民法典》第585条")
        review_model.refresh_summary(run)

        md = review_pipeline.build_top_report(run)

        assert "出处：违约责任 / breach.liquidated_damages_cap" in md
        assert "依据 《民法典》第585条" in md

    def test_report_states_workload_and_ai_disclaimer(self) -> None:
        run = _run()
        a = _finding(run, ordinal=0)
        b = _finding(run, ordinal=1, title="管辖不利")
        review_model.accept(a)
        review_model.reject(b, reason_code=RejectReason.COMMERCIAL, note="客户不让改")
        review_model.refresh_summary(run)

        md = review_pipeline.build_top_report(run)

        assert "律师已采纳 1 项、驳回 1 项" in md
        assert "因商业考量/客户决定未采纳 1 项" in md
        assert "AI 辅助生成" in md
        assert "不构成法律意见" in md

    def test_report_lists_gate_numbers(self) -> None:
        run = _run()
        _finding(run)
        run.summary = {"gates": {"format_ratio_after": 0.0, "kept": 1}}
        run.save(update_fields=["summary"])
        review_model.refresh_summary(run)

        md = review_pipeline.build_top_report(run)
        assert "三道闸" in md
        assert "上限 25" in md


class TestCompareVersions:
    def test_reports_changed_paragraph_count(self, monkeypatch: Any) -> None:
        from pathlib import Path

        from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService

        class _Svc(BoundFolderBrowseService):
            root: Path

            def __init__(self, root: Path) -> None:
                super().__init__()
                self.root = root

            def _require_access(self, **_kw: Any) -> None:
                return None

            def _local_root(self, _owner_id: int) -> Path:
                return self.root

        import tempfile

        tmp = Path(tempfile.mkdtemp())
        (tmp / "1-合同").mkdir(parents=True)
        old = Document()
        old.add_paragraph("第一条 不变")
        old.add_paragraph("第二条 旧内容")
        buf = io.BytesIO()
        old.save(buf)
        (tmp / "1-合同" / "a.docx").write_bytes(buf.getvalue())

        from apps.contracts.services.contract.integrations import folder_browse_service as mod

        monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Svc(tmp))
        snap = snapshot_service.capture(
            kind="contract", owner_id=OWNER_ID, subpath=SUBPATH, data=buf.getvalue(), reason="editor_save"
        )

        new = Document()
        new.add_paragraph("第一条 不变")
        new.add_paragraph("第二条 新内容")
        buf2 = io.BytesIO()
        new.save(buf2)
        (tmp / "1-合同" / "a.docx").write_bytes(buf2.getvalue())

        result = delta_review.compare_versions(kind="contract", owner_id=OWNER_ID, subpath=SUBPATH, seq=snap.seq)

        assert result["found"] is True
        assert result["total_paragraphs"] == 2
        assert result["changed_paragraphs"] == 1
        assert result["unchanged"] is False

    def test_missing_snapshot_is_soft(self) -> None:
        result = delta_review.compare_versions(kind="contract", owner_id=OWNER_ID, subpath=SUBPATH, seq=99)
        assert result["found"] is False

    def test_identical_versions_report_unchanged(self, monkeypatch: Any) -> None:
        from pathlib import Path

        from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService

        class _Svc(BoundFolderBrowseService):
            root: Path

            def __init__(self, root: Path) -> None:
                super().__init__()
                self.root = root

            def _require_access(self, **_kw: Any) -> None:
                return None

            def _local_root(self, _owner_id: int) -> Path:
                return self.root

        import tempfile

        tmp = Path(tempfile.mkdtemp())
        (tmp / "1-合同").mkdir(parents=True)
        doc = Document()
        doc.add_paragraph("第一条 不变")
        buf = io.BytesIO()
        doc.save(buf)
        (tmp / "1-合同" / "a.docx").write_bytes(buf.getvalue())

        from apps.contracts.services.contract.integrations import folder_browse_service as mod

        monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Svc(tmp))
        snap = snapshot_service.capture(
            kind="contract", owner_id=OWNER_ID, subpath=SUBPATH, data=buf.getvalue(), reason="editor_save"
        )

        result = delta_review.compare_versions(kind="contract", owner_id=OWNER_ID, subpath=SUBPATH, seq=snap.seq)
        assert result["unchanged"] is True
        assert result["changed_paragraphs"] == 0
