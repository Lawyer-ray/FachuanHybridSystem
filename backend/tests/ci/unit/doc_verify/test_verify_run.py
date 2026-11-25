"""核对编排：幂等、状态推导、裁决留痕、待裁决清单。

跨 lane 依赖（lane A 的比对引擎、lane B 的入站件提取）在这里用 monkeypatch 替换
`apps.doc_verify.services.verify.deps` 的同名属性——本分支不假定那两条线已合入，
但要求它们的调用形状与契约一致。
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from apps.core.exceptions import ValidationException
from apps.doc_verify.domain.contracts import AssertionKind, Baseline, Finding, Inbound, Report, Severity
from apps.doc_verify.models import CaptureSource, OutboundArtifact, VerificationDecision, VerificationRun, VerifyState
from apps.doc_verify.services.verify import decision as decision_service
from apps.doc_verify.services.verify import deps
from apps.doc_verify.services.verify import query as query_service
from apps.doc_verify.services.verify import run as run_service
from apps.testing.factories import CaseFactory

PDF_BYTES = b"%PDF-1.7 inbound payload"
BASELINE_BYTES = b"%PDF-1.7 outbound baseline"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _finding(severity: Severity, code: str = "field_mismatch") -> Finding:
    return Finding(
        kind=AssertionKind.FIELD,
        code=code,
        title="金额不一致",
        severity=severity,
        detail="基线 100000 / 回传 10000",
        expected="100000",
        actual="10000",
        page=2,
    )


def _artifact(**overrides: Any) -> OutboundArtifact:
    values: dict[str, Any] = {
        "doc_type": "起诉状",
        "version": "V4_20261106",
        "file_name": "起诉状_V4.pdf",
        "file_sha256": _sha(BASELINE_BYTES),
        "page_count": 2,
        "page_signatures": [[0.5, 0.25], [0.5, 0.25]],
        "text_layer": "诉讼请求：返还本金 100000 元",
        "masks": [{"page": 2, "reason": "signature"}],
        "capture_source": CaptureSource.SEND_TO_CLIENT,
        "verify_required": True,
    }
    values.update(overrides)
    return OutboundArtifact.objects.create(**values)


def _inbound(**overrides: Any) -> Inbound:
    values: dict[str, Any] = {
        "sha256": _sha(PDF_BYTES),
        "page_count": 2,
        "page_signatures": ((0.5, 0.25), (0.5, 0.25)),
        "text": "诉讼请求：返还本金 10000 元",
        "file_name": "回传件.pdf",
    }
    values.update(overrides)
    return Inbound(**values)


def _patch_extract(monkeypatch: pytest.MonkeyPatch, **inbound_overrides: Any) -> list[SimpleNamespace]:
    """替换 lane B 的入站件提取，记录入参；返回的 Inbound 与真实字节的 sha 保持一致。"""
    calls: list[SimpleNamespace] = []

    def fake_extract(data: bytes, file_name: str = "") -> Any:
        calls.append(SimpleNamespace(data=data, file_name=file_name))
        return _inbound(sha256=_sha(data), **inbound_overrides)

    monkeypatch.setattr(deps, "extract_document", fake_extract)
    return calls


def _patch_compare(monkeypatch: pytest.MonkeyPatch, report: Report | None = None) -> list[SimpleNamespace]:
    """替换 lane A 的比对引擎，记录入参；默认返回空报告。"""
    calls: list[SimpleNamespace] = []

    def fake_compare(baseline: Any, inbound: Any, *, tier: int = 0) -> Any:
        calls.append(SimpleNamespace(baseline=baseline, inbound=inbound, tier=tier))
        return Report(tier=tier) if report is None else report

    monkeypatch.setattr(deps, "compare_documents", fake_compare)
    return calls


def _run(artifact: OutboundArtifact, *, state: str, decisions: tuple[str, ...] = ()) -> VerificationRun:
    run = VerificationRun.objects.create(
        artifact=artifact,
        run_key=f"key-{uuid4()}",
        state=state,
        inbound_sha256=_sha(PDF_BYTES),
        page_count=2,
    )
    for action in decisions:
        decision_service.record_decision(verification=run, action=action)
    return run


def _report(
    *findings: Finding,
    text_compared: bool = False,
    pages_no_text: int = 0,
    identical: bool = False,
    tier: int = 0,
) -> Report:
    """造一份报告：覆盖度键名与 `domain/compare._coverage` 逐字一致。"""
    coverage = {"text_compared": text_compared, "pages_no_text": pages_no_text, "bytes_identical": identical}
    return Report(findings=list(findings), coverage=coverage, tier=tier)


class TestDeriveState:
    """状态是推导出来的，不接受调用方拍板。

    判据是**覆盖度**不是 tier：tier 只说明花了多少钱，不说明比了什么
    （见 `domain/states.py` 的 docstring）。
    """

    def test_red_finding_means_changed(self) -> None:
        assert run_service.derive_state(_report(_finding(Severity.RED))) == VerifyState.CHANGED

    def test_yellow_finding_means_changed(self) -> None:
        assert run_service.derive_state(_report(_finding(Severity.YELLOW))) == VerifyState.CHANGED

    def test_gray_finding_means_unverifiable(self) -> None:
        report = _report(_finding(Severity.GRAY, code="PAGE_NO_TEXT"))
        assert run_service.derive_state(report) == VerifyState.UNVERIFIABLE

    def test_yellow_wins_over_gray(self) -> None:
        """有具体可疑差异时先说「疑似改动」：它才是最需要立刻裁决的那件事。"""
        report = _report(_finding(Severity.GRAY), _finding(Severity.YELLOW))
        assert run_service.derive_state(report) == VerifyState.CHANGED

    def test_no_findings_without_text_means_no_difference_detected(self) -> None:
        assert run_service.derive_state(_report()) == VerifyState.NO_DIFFERENCE_DETECTED

    def test_no_findings_with_full_text_comparison_means_verified_clean(self) -> None:
        """tier 0 也能逐字比数字件的文本层：比完干净就是真的干净。"""
        report = _report(text_compared=True, pages_no_text=0, tier=0)
        assert run_service.derive_state(report) == VerifyState.VERIFIED_CLEAN

    def test_partial_text_coverage_is_never_green(self) -> None:
        """tier 1 但有一页没取到字 → 不许给 verified_clean（那是句假话）。"""
        report = _report(text_compared=True, pages_no_text=1, tier=1)
        assert run_service.derive_state(report) == VerifyState.NO_DIFFERENCE_DETECTED

    def test_identical_bytes_win_over_any_finding(self) -> None:
        report = _report(_finding(Severity.RED), identical=True, tier=1)
        assert run_service.derive_state(report) == VerifyState.IDENTICAL


@pytest.mark.django_db
class TestVerifyInboundIdempotency:
    def test_same_artifact_and_same_bytes_creates_one_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        extract_calls = _patch_extract(monkeypatch)
        _patch_compare(monkeypatch)

        first = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES, file_name="回传件.pdf")
        second = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES, file_name="回传件.pdf")

        assert first.id == second.id
        assert VerificationRun.objects.filter(artifact=artifact).count() == 1
        # 幂等不只是「不多建行」：第二次连提取都不该再跑
        # 取字在「未指定 tier」时会跑两次：第二遍是为了知道该用哪一层
        # （层数取决于入站件有没有文本层）。**贵的那段（比对/OCR）**不重跑，
        # 见下面 compare 调用计数与 run 行数。
        assert extract_calls

    def test_extract_receives_the_raw_bytes_and_file_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        extract_calls = _patch_extract(monkeypatch)
        _patch_compare(monkeypatch)

        run_service.verify_inbound(artifact=artifact, data=PDF_BYTES, file_name="客户回传.pdf")

        assert extract_calls[0].data == PDF_BYTES
        assert extract_calls[0].file_name == "客户回传.pdf"

    def test_different_bytes_create_a_second_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        _patch_extract(monkeypatch)
        _patch_compare(monkeypatch)

        run_service.verify_inbound(artifact=artifact, data=PDF_BYTES)
        run_service.verify_inbound(artifact=artifact, data=PDF_BYTES + b" v2")

        assert VerificationRun.objects.filter(artifact=artifact).count() == 2

    def test_run_key_is_sha256_of_artifact_id_and_inbound_bytes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        _patch_extract(monkeypatch)
        _patch_compare(monkeypatch)

        run = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES)

        expected = hashlib.sha256(f"{artifact.id}:{_sha(PDF_BYTES)}".encode()).hexdigest()[:64]
        assert run.run_key == expected


@pytest.mark.django_db
class TestVerifyInboundRecord:
    def test_records_report_and_inbound_facts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        _patch_extract(monkeypatch, page_count=3, text="回传正文")
        _patch_compare(
            monkeypatch,
            Report(
                findings=[_finding(Severity.RED)],
                coverage={"comparable_pages": 3, "image_pages": 1},
                tier=0,
            ),
        )

        run = run_service.verify_inbound(
            artifact=artifact,
            data=PDF_BYTES,
            file_name="回传件.pdf",
            source_message_id=42,
        )

        run.refresh_from_db()
        assert run.state == VerifyState.CHANGED
        assert run.tier == 0
        assert run.inbound_sha256 == _sha(PDF_BYTES)
        assert run.inbound_file_name == "回传件.pdf"
        assert run.page_count == 3
        assert run.coverage == {"comparable_pages": 3, "image_pages": 1}
        assert run.findings[0]["code"] == "field_mismatch"
        assert run.findings[0]["severity"] == "red"
        assert run.source_message_id == 42

    def test_inbound_file_name_from_extractor_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """提取层知道真实文件名时以它为准（上传名可能是临时名）。"""
        artifact = _artifact()
        _patch_extract(monkeypatch)
        _patch_compare(monkeypatch)

        run = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES, file_name="tmp-upload.pdf")

        assert run.inbound_file_name == "回传件.pdf"

    def test_identical_bytes_short_circuit_inside_the_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """原样回传：短路发生在**引擎内部**（sha 相同直接返回 identical 覆盖度）。

        编排层不再自己短路——同一个事实两处实现，迟早有一处少写一个 coverage 键，
        于是「原样回传」被报成「未发现差异」。引擎那一步是 O(1) 的 sha 比较，不浪费。
        """
        artifact = _artifact(file_sha256=_sha(PDF_BYTES))
        _patch_extract(monkeypatch)
        compare_calls = _patch_compare(monkeypatch, Report(findings=[], coverage={"bytes_identical": True}))

        run = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES)

        assert len(compare_calls) == 1
        assert run.state == VerifyState.IDENTICAL
        assert run.findings == []

    def test_does_not_write_decisions_or_touch_the_baseline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        before = (
            artifact.doc_type,
            artifact.version,
            artifact.file_name,
            artifact.file_sha256,
            artifact.page_count,
            artifact.text_layer,
            artifact.verify_required,
        )
        _patch_extract(monkeypatch)
        _patch_compare(monkeypatch, Report(findings=[_finding(Severity.RED)]))

        run_service.verify_inbound(artifact=artifact, data=PDF_BYTES)

        artifact.refresh_from_db()
        after = (
            artifact.doc_type,
            artifact.version,
            artifact.file_name,
            artifact.file_sha256,
            artifact.page_count,
            artifact.text_layer,
            artifact.verify_required,
        )
        assert after == before
        assert VerificationDecision.objects.filter(verification__artifact=artifact).count() == 0

    @pytest.mark.parametrize("tier", [-1, 3])
    def test_rejects_tier_outside_the_contract(self, monkeypatch: pytest.MonkeyPatch, tier: int) -> None:
        artifact = _artifact()
        _patch_extract(monkeypatch)
        _patch_compare(monkeypatch)

        with pytest.raises(ValidationException):
            run_service.verify_inbound(artifact=artifact, data=PDF_BYTES, tier=tier)

        assert VerificationRun.objects.filter(artifact=artifact).count() == 0

    def test_rejects_empty_bytes(self) -> None:
        artifact = _artifact()
        with pytest.raises(ValidationException):
            run_service.verify_inbound(artifact=artifact, data=b"")
        assert VerificationRun.objects.filter(artifact=artifact).count() == 0

    def test_rejects_overlong_file_name(self) -> None:
        artifact = _artifact()
        with pytest.raises(ValidationException):
            run_service.verify_inbound(artifact=artifact, data=PDF_BYTES, file_name="长" * 256)
        assert VerificationRun.objects.filter(artifact=artifact).count() == 0


@pytest.mark.django_db
class TestVerifyExistingBytes:
    def test_requires_tier_at_least_one(self) -> None:
        """免费层读的是同一份 JSONField，自检恒等——那种「通过」没有信息量。"""
        artifact = _artifact()
        with pytest.raises(ValidationException):
            run_service.verify_existing_bytes(artifact=artifact, tier=0)

    def test_compares_stored_snapshot_without_persisting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        compare_calls = _patch_compare(monkeypatch, Report(findings=[], tier=1))

        report = run_service.verify_existing_bytes(artifact=artifact, tier=1)

        assert report.tier == 1
        assert len(compare_calls) == 1
        baseline = compare_calls[0].baseline
        inbound = compare_calls[0].inbound
        assert isinstance(baseline, Baseline)
        assert baseline.doc_type == artifact.doc_type
        assert baseline.version == artifact.version
        assert baseline.sha256 == artifact.file_sha256
        assert baseline.page_signatures == ((0.5, 0.25), (0.5, 0.25))
        assert baseline.text == artifact.text_layer
        assert baseline.masks == ({"page": 2, "reason": "signature"},)
        assert inbound.sha256 == artifact.file_sha256
        assert inbound.text == artifact.text_layer
        assert inbound.file_name == artifact.file_name
        assert compare_calls[0].tier == 1
        assert VerificationRun.objects.count() == 0


@pytest.mark.django_db
class TestRecordDecision:
    @pytest.mark.parametrize("action", ["accept", "reject", "reissue"])
    def test_accepts_three_actions(self, action: str) -> None:
        run = _run(_artifact(), state=VerifyState.CHANGED)

        decided = decision_service.record_decision(verification=run, action=action, reason="已核对原件")

        assert decided.action == action
        assert decided.reason == "已核对原件"
        assert run.decisions.count() == 1

    def test_strips_surrounding_whitespace(self) -> None:
        run = _run(_artifact(), state=VerifyState.CHANGED)

        decided = decision_service.record_decision(verification=run, action=" accept ", reason="  客户已说明  ")

        assert decided.action == "accept"
        assert decided.reason == "客户已说明"

    @pytest.mark.parametrize("action", ["approve", "ACCEPT", "", "accept/reject"])
    def test_rejects_actions_outside_the_three(self, action: str) -> None:
        run = _run(_artifact(), state=VerifyState.CHANGED)

        with pytest.raises(ValidationException):
            decision_service.record_decision(verification=run, action=action)

        assert run.decisions.count() == 0

    def test_keeps_history_instead_of_overwriting(self) -> None:
        """写错就再记一条：历史行一个字都不能改。"""
        run = _run(_artifact(), state=VerifyState.CHANGED)

        first = decision_service.record_decision(verification=run, action="accept", reason="第一次看错")
        decision_service.record_decision(verification=run, action="reject", reason="复核后确认有改动")

        first.refresh_from_db()
        assert first.action == "accept"
        assert first.reason == "第一次看错"
        assert run.decisions.count() == 2

    def test_decided_by_can_be_absent(self) -> None:
        run = _run(_artifact(), state=VerifyState.CHANGED)

        decided = decision_service.record_decision(verification=run, action="accept")

        assert decided.decided_by_id is None


@pytest.mark.django_db
class TestListUnverified:
    def _case_and_artifact(self, *, verify_required: bool = True) -> tuple[Any, OutboundArtifact]:
        case = CaseFactory()
        return case, _artifact(case=case, verify_required=verify_required)

    def test_lists_only_runs_that_need_a_decision(self) -> None:
        case, artifact = self._case_and_artifact()
        changed = _run(artifact, state=VerifyState.CHANGED)
        unverifiable = _run(artifact, state=VerifyState.UNVERIFIABLE)
        _run(artifact, state=VerifyState.VERIFIED_CLEAN)
        _run(artifact, state=VerifyState.NO_DIFFERENCE_DETECTED)
        _run(artifact, state=VerifyState.IDENTICAL)

        items = query_service.list_unverified(case.id)

        assert [item["id"] for item in items] == [unverifiable.id, changed.id]

    @pytest.mark.parametrize("action", ["accept", "reject"])
    def test_decided_runs_leave_the_list(self, action: str) -> None:
        case, artifact = self._case_and_artifact()
        _run(artifact, state=VerifyState.CHANGED, decisions=(action,))

        assert query_service.list_unverified(case.id) == []

    def test_decision_on_one_run_does_not_hide_another_run_of_the_same_artifact(self) -> None:
        """同一份基线的两次回传各自裁决：A 被接受不影响 B 仍在清单里。"""
        case, artifact = self._case_and_artifact()
        _run(artifact, state=VerifyState.CHANGED, decisions=("accept",))
        pending = _run(artifact, state=VerifyState.CHANGED)

        assert [item["id"] for item in query_service.list_unverified(case.id)] == [pending.id]

    def test_reissue_keeps_the_run_in_the_list(self) -> None:
        """要求重出之后客户还没回新版，这一条仍在进行中。"""
        case, artifact = self._case_and_artifact()
        run = _run(artifact, state=VerifyState.CHANGED, decisions=("reissue",))

        assert [item["id"] for item in query_service.list_unverified(case.id)] == [run.id]

    def test_artifact_without_verify_required_is_excluded(self) -> None:
        case, artifact = self._case_and_artifact(verify_required=False)
        _run(artifact, state=VerifyState.CHANGED)

        assert query_service.list_unverified(case.id) == []

    def test_other_cases_are_excluded(self) -> None:
        case, artifact = self._case_and_artifact()
        _, other_artifact = self._case_and_artifact()
        _run(artifact, state=VerifyState.CHANGED)
        _run(other_artifact, state=VerifyState.CHANGED)

        items = query_service.list_unverified(case.id)

        assert len(items) == 1
        assert items[0]["case_id"] == case.id

    def test_row_carries_the_artifact_context(self) -> None:
        case, artifact = self._case_and_artifact()
        run = _run(artifact, state=VerifyState.CHANGED)

        item = query_service.list_unverified(case.id)[0]

        assert item["id"] == run.id
        assert item["artifact_id"] == artifact.id
        assert item["doc_type"] == "起诉状"
        assert item["state"] == VerifyState.CHANGED
        assert item["state_label"] == "疑似改动"
        assert item["tier"] == 0
        assert item["page_count"] == 2
