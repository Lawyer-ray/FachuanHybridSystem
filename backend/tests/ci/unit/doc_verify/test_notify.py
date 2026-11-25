"""检出红线 → 待办：只在「真检出问题」时建一条，且永不炸掉核对。

## 为什么断言「1 条」而不是「每个承办律师 1 条」

`Reminder` 没有收件人字段：绑案件的提醒对该案全部承办律师可见，是**同一行**。
按人拆行会让每个律师在日历里看到 N 条一模一样的待办（`ReminderType.OTHER` 不进
`calendar_view_service.merge_events` 的合并口径）。理由见 `services/verify/notify.py`。

## 为什么灰的、干净的都不建

待办流的价值来自稀缺。灰的（图片页比不了）、干净的（正文逐项比过）也往里塞，
律师很快就会整体忽略这个流——那比不提醒更糟。
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from django.db import DatabaseError
from django.utils import timezone

from apps.cases.models import CaseAssignment
from apps.doc_verify.domain.contracts import AssertionKind, Finding, Inbound, Report, Severity
from apps.doc_verify.models import CaptureSource, OutboundArtifact, VerificationRun, VerifyState
from apps.doc_verify.services.verify import deps
from apps.doc_verify.services.verify import notify as notify_service
from apps.doc_verify.services.verify import run as run_service
from apps.reminders.models import Reminder, ReminderType
from apps.testing.factories import CaseFactory, LawyerFactory

DOC_TYPE = "民事起诉状"
INBOUND_BYTES = b"%PDF-1.7 inbound payload"
BASELINE_BYTES = b"%PDF-1.7 outbound baseline"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _finding(severity: Severity, code: str) -> dict[str, Any]:
    """落库形状：`VerificationRun.findings` 存的是 `Finding.as_dict()`。"""
    return Finding(
        kind=AssertionKind.FIELD,
        code=code,
        title="金额不一致",
        severity=severity,
        detail="基线 100000 / 回传 10000",
        expected="100000",
        actual="10000",
        page=2,
    ).as_dict()


def _artifact(*, case: Any = None, with_case: bool = True, doc_type: str = DOC_TYPE) -> OutboundArtifact:
    return OutboundArtifact.objects.create(
        case=case if case is not None else (CaseFactory() if with_case else None),
        doc_type=doc_type,
        version="V4_20261106",
        file_name="起诉状_V4.pdf",
        file_sha256=_sha(BASELINE_BYTES),
        page_count=2,
        text_layer="诉讼请求：返还本金 100000 元",
        capture_source=CaptureSource.SEND_TO_CLIENT,
        verify_required=True,
    )


def _run(
    artifact: OutboundArtifact,
    *,
    state: str = VerifyState.CHANGED,
    findings: list[dict[str, Any]] | None = None,
) -> VerificationRun:
    return VerificationRun.objects.create(
        artifact=artifact,
        run_key=f"key-{uuid4()}",
        state=state,
        inbound_sha256=_sha(INBOUND_BYTES),
        page_count=2,
        findings=[_finding(Severity.RED, "AMOUNT_MISMATCH")] if findings is None else findings,
    )


def _assign_lawyers(case: Any, count: int = 1) -> list[Any]:
    return [CaseAssignment.objects.create(case=case, lawyer=LawyerFactory()) for _ in range(count)]


def _patch_notify_deps(monkeypatch: pytest.MonkeyPatch, *, severities: tuple[Severity, ...]) -> None:
    """替换跨 lane 依赖（提取 / 比对），让 `verify_inbound` 走完整编排路径。"""

    def fake_extract(data: bytes, file_name: str = "") -> Inbound:
        return Inbound(
            sha256=_sha(data),
            page_count=1,
            page_signatures=((0.5, 0.25),),
            text="诉讼请求：返还本金 10000 元",
            file_name=file_name,
        )

    def fake_compare(baseline: Any, inbound: Any, *, tier: int = 0) -> Report:
        return Report(
            findings=[
                Finding(kind=AssertionKind.FIELD, code=f"CODE_{i}", title="金额不一致", severity=s)
                for i, s in enumerate(severities)
            ],
            coverage={"text_compared": True, "pages_no_text": 0, "bytes_identical": False},
            tier=tier,
        )

    monkeypatch.setattr(deps, "extract_document", fake_extract)
    monkeypatch.setattr(deps, "compare_documents", fake_compare)


def _break_reminder_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """reminders 的 service 在写库时炸掉（库挂了 / 数据不合法的同一类结局）。"""

    class _BrokenReminderService:
        def create_reminder(self, **_: Any) -> Any:
            raise DatabaseError("reminders 写入失败")

    monkeypatch.setattr("apps.reminders.services.wiring.get_reminder_service", lambda: _BrokenReminderService())


class TestReminderContent:
    """待办正文是给人看的一句话：文书名 + 红线数 + 前两条 code。"""

    def test_names_document_red_count_and_first_two_codes(self) -> None:
        run = SimpleNamespace(
            artifact=SimpleNamespace(doc_type="民事起诉状"),
            state=VerifyState.CHANGED,
            findings=[
                _finding(Severity.RED, "AMOUNT_MISMATCH"),
                _finding(Severity.RED, "PARTY_NAME_MISMATCH"),
                _finding(Severity.RED, "CASE_NO_MISMATCH"),
                _finding(Severity.YELLOW, "PARAGRAPH_SHIFTED"),
            ],
        )

        content = notify_service.reminder_content(run)

        assert "民事起诉状" in content
        assert "3 条红线" in content  # 数的是红线，yellow 不算
        assert "AMOUNT_MISMATCH" in content
        assert "PARTY_NAME_MISMATCH" in content
        assert "CASE_NO_MISMATCH" not in content  # 只列前两条，第三条塞进来就读不成句子了

    def test_falls_back_to_a_generic_document_name(self) -> None:
        run = SimpleNamespace(
            artifact=SimpleNamespace(doc_type=""),
            state=VerifyState.CHANGED,
            findings=[_finding(Severity.RED, "AMOUNT_MISMATCH")],
        )

        assert "回传件《回传件》" in notify_service.reminder_content(run)


@pytest.mark.django_db
class TestNotifyPendingDecision:
    def test_red_finding_creates_one_reminder_for_the_case(self) -> None:
        """三个承办律师仍然只有一条待办：这是**一个**裁决任务，不是三份。"""
        case = CaseFactory()
        _assign_lawyers(case, count=3)
        run = _run(_artifact(case=case))

        created = notify_service.notify_pending_decision(run=run)

        assert created == 1
        reminder = Reminder.objects.get()
        assert reminder.case_id == case.id
        assert reminder.reminder_type == ReminderType.OTHER
        assert reminder.metadata == {
            "doc_verify_run_id": run.pk,
            "doc_verify_doc_type": DOC_TYPE,
            "doc_verify_state": VerifyState.CHANGED,
        }
        assert reminder.content == notify_service.reminder_content(run)
        expected_due_at = timezone.now() + timedelta(days=notify_service.REMINDER_DUE_IN_DAYS)
        assert abs((reminder.due_at - expected_due_at).total_seconds()) < 60
        assert reminder.created_by_id is None  # 这条路径手里没有操作人

    def test_actor_is_recorded_as_the_creator(self) -> None:
        case = CaseFactory()
        _assign_lawyers(case)
        actor = LawyerFactory()

        notify_service.notify_pending_decision(run=_run(_artifact(case=case)), actor=actor)

        assert Reminder.objects.get().created_by_id == actor.pk

    def test_yellow_only_does_not_notify(self) -> None:
        case = CaseFactory()
        _assign_lawyers(case)
        run = _run(_artifact(case=case), findings=[_finding(Severity.YELLOW, "PARAGRAPH_SHIFTED")])

        assert notify_service.notify_pending_decision(run=run) == 0
        assert Reminder.objects.count() == 0

    def test_gray_only_does_not_notify(self) -> None:
        case = CaseFactory()
        _assign_lawyers(case)
        run = _run(
            _artifact(case=case),
            state=VerifyState.UNVERIFIABLE,
            findings=[_finding(Severity.GRAY, "PAGE_NO_TEXT")],
        )

        assert notify_service.notify_pending_decision(run=run) == 0
        assert Reminder.objects.count() == 0

    def test_clean_run_does_not_notify(self) -> None:
        case = CaseFactory()
        _assign_lawyers(case)
        run = _run(_artifact(case=case), state=VerifyState.VERIFIED_CLEAN, findings=[])

        assert notify_service.notify_pending_decision(run=run) == 0
        assert Reminder.objects.count() == 0

    def test_identical_run_does_not_notify(self) -> None:
        case = CaseFactory()
        _assign_lawyers(case)
        run = _run(_artifact(case=case), state=VerifyState.IDENTICAL, findings=[])

        assert notify_service.notify_pending_decision(run=run) == 0
        assert Reminder.objects.count() == 0

    def test_red_in_a_blocking_state_other_than_changed_still_notifies(self) -> None:
        """触发条件是「阻塞状态 + 有红线」两条并列，不是 state 等于某一个值。"""
        case = CaseFactory()
        _assign_lawyers(case)
        run = _run(
            _artifact(case=case),
            state=VerifyState.UNVERIFIABLE,
            findings=[_finding(Severity.RED, "AMOUNT_MISMATCH"), _finding(Severity.GRAY, "PAGE_NO_TEXT")],
        )

        assert notify_service.notify_pending_decision(run=run) == 1

    def test_second_call_does_not_create_another_reminder(self) -> None:
        case = CaseFactory()
        _assign_lawyers(case)
        run = _run(_artifact(case=case))

        assert notify_service.notify_pending_decision(run=run) == 1
        assert notify_service.notify_pending_decision(run=run) == 0
        assert Reminder.objects.count() == 1

    def test_upgraded_run_creates_the_reminder_once(self) -> None:
        """升层重核是同一个 run：从「未发现差异」变成「疑似改动」时补建，之后不再重复。"""
        case = CaseFactory()
        _assign_lawyers(case)
        run = _run(_artifact(case=case), state=VerifyState.NO_DIFFERENCE_DETECTED, findings=[])
        assert notify_service.notify_pending_decision(run=run) == 0

        # 原地升级：同一行 run 的结论被更强的证据改写（见 run._upgrade_run）
        run.state = VerifyState.CHANGED
        run.tier = 1
        run.findings = [_finding(Severity.RED, "AMOUNT_MISMATCH")]
        run.save(update_fields=["state", "tier", "findings"])

        assert notify_service.notify_pending_decision(run=run) == 1
        assert notify_service.notify_pending_decision(run=run) == 0
        assert Reminder.objects.count() == 1

    def test_case_without_assigned_lawyer_does_not_notify(self) -> None:
        """没人被指派 → 绑案件的提醒谁也看不见，建了就是垃圾行。"""
        run = _run(_artifact(case=CaseFactory()))

        assert notify_service.notify_pending_decision(run=run) == 0
        assert Reminder.objects.count() == 0

    def test_run_without_case_does_not_notify(self) -> None:
        run = _run(_artifact(with_case=False))

        assert notify_service.notify_pending_decision(run=run) == 0
        assert Reminder.objects.count() == 0

    def test_reminder_service_failure_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        case = CaseFactory()
        _assign_lawyers(case)
        run = _run(_artifact(case=case))
        _break_reminder_service(monkeypatch)

        assert notify_service.notify_pending_decision(run=run) == 0
        assert Reminder.objects.count() == 0


@pytest.mark.django_db
class TestVerifyInboundNotifies:
    """调用点在 run 落库之后：待办说的是「这一行结论」，不是「打算核」。"""

    def test_red_run_creates_the_reminder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        case = CaseFactory()
        _assign_lawyers(case)
        artifact = _artifact(case=case)
        _patch_notify_deps(monkeypatch, severities=(Severity.RED,))

        run = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES, file_name="回传件.pdf")

        reminder = Reminder.objects.get()
        assert reminder.metadata["doc_verify_run_id"] == run.pk
        assert reminder.case_id == case.id

    def test_same_bytes_uploaded_twice_keeps_one_reminder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        case = CaseFactory()
        _assign_lawyers(case)
        artifact = _artifact(case=case)
        _patch_notify_deps(monkeypatch, severities=(Severity.RED,))

        first = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES)
        second = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES)

        assert first.pk == second.pk
        assert Reminder.objects.count() == 1

    def test_clean_run_creates_no_reminder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        case = CaseFactory()
        _assign_lawyers(case)
        artifact = _artifact(case=case)
        _patch_notify_deps(monkeypatch, severities=())

        run = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES)

        assert run.state == VerifyState.VERIFIED_CLEAN
        assert Reminder.objects.count() == 0

    def test_notify_failure_keeps_the_verification_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """待办没写成，核对结论一个字都不能少。"""
        case = CaseFactory()
        _assign_lawyers(case)
        artifact = _artifact(case=case)
        _patch_notify_deps(monkeypatch, severities=(Severity.RED,))
        _break_reminder_service(monkeypatch)

        run = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES)

        assert run.pk is not None
        assert run.state == VerifyState.CHANGED
        assert VerificationRun.objects.filter(artifact=artifact).count() == 1
        assert Reminder.objects.count() == 0
