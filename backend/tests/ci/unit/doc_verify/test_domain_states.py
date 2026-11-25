"""`domain/states.py` 的单测：状态推导的四级优先序，以及状态字符串与模型的契约。

状态推导是「报告对律师说的那句话」的唯一出口：gray 被当成干净、或没比过正文被说成
「核对通过」，都是这句假话的来源。所以这里逐条钉住优先序与覆盖度判据。
"""

from __future__ import annotations

import pytest

from apps.doc_verify.domain.contracts import AssertionKind, Finding, Report, Severity
from apps.doc_verify.domain.states import (
    BLOCKING_STATES,
    PASS_STATES,
    STATE_CHANGED,
    STATE_IDENTICAL,
    STATE_NO_DIFFERENCE_DETECTED,
    STATE_NOT_REQUESTED,
    STATE_UNVERIFIABLE,
    STATE_VERIFIED_CLEAN,
    derive_state,
)
from apps.doc_verify.models.verification import VerifyState

#: 报告能推导出来的状态（`not_requested` 不在内：它由「压根没有核对运行」决定）。
DERIVABLE_STATES = {
    STATE_IDENTICAL,
    STATE_VERIFIED_CLEAN,
    STATE_NO_DIFFERENCE_DETECTED,
    STATE_CHANGED,
    STATE_UNVERIFIABLE,
}

#: 正文真的比过、且没有一页缺文本的覆盖度。
CLEAN_COVERAGE = {"pages_total": 2, "pages_with_text": 2, "pages_no_text": 0, "text_compared": True}


def _finding(severity: Severity, code: str = "TEST") -> Finding:
    return Finding(kind=AssertionKind.PARAGRAPH, code=code, title="测试", severity=severity)


class TestStateValuesMatchModel:
    def test_all_state_constants_exist_in_verify_state(self) -> None:
        # 状态字符串是写进 VerificationRun.state 的库值，改名而不同步模型等于写脏数据
        model_values = {choice.value for choice in VerifyState}
        assert DERIVABLE_STATES | {STATE_NOT_REQUESTED} == model_values

    def test_blocking_states_are_release_requires_adjudication(self) -> None:
        assert {STATE_CHANGED, STATE_UNVERIFIABLE} == BLOCKING_STATES

    def test_pass_states_are_the_two_auto_release_ones(self) -> None:
        assert {STATE_IDENTICAL, STATE_VERIFIED_CLEAN} == PASS_STATES

    def test_blocking_and_pass_cover_two_disjoint_facts(self) -> None:
        assert BLOCKING_STATES.isdisjoint(PASS_STATES)
        model_values = {choice.value for choice in VerifyState}
        assert (BLOCKING_STATES | PASS_STATES).issubset(model_values)


class TestDeriveState:
    def test_bytes_identical_wins_over_everything(self) -> None:
        report = Report(findings=[_finding(Severity.RED)], coverage={"bytes_identical": True}, tier=0)
        assert derive_state(report) == STATE_IDENTICAL

    @pytest.mark.parametrize("severity", [Severity.RED, Severity.YELLOW])
    def test_red_or_yellow_is_changed(self, severity: Severity) -> None:
        assert derive_state(Report(findings=[_finding(severity)], coverage=CLEAN_COVERAGE, tier=1)) == STATE_CHANGED

    def test_red_wins_over_gray(self) -> None:
        report = Report(findings=[_finding(Severity.GRAY), _finding(Severity.RED)], coverage={}, tier=2)
        assert derive_state(report) == STATE_CHANGED

    def test_only_gray_is_unverifiable(self) -> None:
        report = Report(findings=[_finding(Severity.GRAY)], coverage=CLEAN_COVERAGE, tier=1)
        assert derive_state(report) == STATE_UNVERIFIABLE

    def test_text_compared_and_no_missing_page_is_verified_clean_even_at_tier_zero(self) -> None:
        # 数字件在免费层也能逐字比：比完干净就是真的干净，不能打成「没核」
        assert derive_state(Report(findings=[], coverage=CLEAN_COVERAGE, tier=0)) == STATE_VERIFIED_CLEAN

    def test_not_compared_is_no_difference_detected(self) -> None:
        coverage = {"pages_total": 2, "pages_with_text": 0, "pages_no_text": 2, "text_compared": False}
        assert derive_state(Report(findings=[], coverage=coverage, tier=0)) == STATE_NO_DIFFERENCE_DETECTED

    def test_one_page_without_text_is_not_verified_clean(self) -> None:
        coverage = {"pages_total": 3, "pages_with_text": 2, "pages_no_text": 1, "text_compared": True}
        assert derive_state(Report(findings=[], coverage=coverage, tier=1)) == STATE_NO_DIFFERENCE_DETECTED

    def test_missing_coverage_keys_are_treated_as_not_compared(self) -> None:
        # 覆盖度是别人写的：读不到就等于没有证据
        assert derive_state(Report(findings=[], coverage={}, tier=1)) == STATE_NO_DIFFERENCE_DETECTED
