"""delta 再审查：只审变更段落 + 上一轮结论续上 + 幂等。

## 每条断言对应的真实后果

| 断言 | 不守会怎样 |
|---|---|
| 变更区间由 `difflib` 算出（纯函数） | 让模型判断「哪里变了」，它会把没变的地方也重审一遍 |
| 第二轮输入段落数显著少 | 40 页文档再审一遍，成本和首轮一样，「再审查」就没人愿意点 |
| 只把变更段落喂给模型 | 全篇塞进去 = 同一批结论再提一遍，清单翻倍 |
| 仍存在→保持待决 / 已消解→moot / 锚点没了→stale | 律师看到的清单里混着已经处理完的条目 |
| 文档没变时不调模型 | 手滑点两次「重新审查」，清单里一半是完全相同的建议 |
| 沿用上一轮的标准快照 | 「上个月说可以、这个月说不行」只是因为标准改版，没人能解释 |
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from docx import Document

from apps.doc_workspace.models import Finding, FindingStatus, ReviewRun, RunStatus
from apps.doc_workspace.services import delta_review, playbook_service, review_pipeline

pytestmark = pytest.mark.django_db

UNCHANGED_1 = "第一条 本合同自双方签字之日起生效。"
UNCHANGED_2 = "第二条 保密义务在本合同终止后仍持续两年。"
TARGET = "第三条 乙方应当在三十日内完成交付。"
UNCHANGED_3 = "第四条 争议提交甲方所在地人民法院管辖。"
UNCHANGED_4 = "第五条 本合同一式两份，双方各执一份。"
NEW_TARGET = "第三条 乙方应当在十五日内完成交付。"


def _docx(*paragraphs: str) -> bytes:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _old_bytes() -> bytes:
    return _docx(UNCHANGED_1, UNCHANGED_2, TARGET, UNCHANGED_3, UNCHANGED_4)


def _new_bytes() -> bytes:
    return _docx(UNCHANGED_1, UNCHANGED_2, NEW_TARGET, UNCHANGED_3, UNCHANGED_4)


def _snapshot() -> list[dict[str, Any]]:
    return playbook_service.snapshot_rules(playbook_service.ensure_builtin())


def _prev_run(**kw: Any) -> ReviewRun:
    defaults = {
        "owner_kind": "contract",
        "owner_id": 1118,
        "subpath": "1-合同/a.docx",
        "status": RunStatus.DONE,
        "stance": "neutral",
        "contract_type": "",
        "playbook_snapshot": _snapshot(),
        "playbook_version": 1,
    }
    defaults.update(kw)
    return ReviewRun.objects.create(**defaults)


def _finding(run: ReviewRun, **kw: Any) -> Finding:
    defaults = {
        "run": run,
        "ordinal": 0,
        "verdict": "deviation",
        "severity": "high",
        "kind": "risk",
        "rule_key": "performance.deadline",
        "title": "交付期限过宽",
        "reason": "三十日过长",
        "quote": TARGET,
        "suggestion_original": TARGET,
        "suggestion_replacement": NEW_TARGET,
        "delivery": "revision",
        "status": FindingStatus.PROPOSED,
    }
    defaults.update(kw)
    return Finding.objects.create(**defaults)


def _caller(payload: list[dict[str, Any]] | None = None) -> Any:
    return lambda _messages: json.dumps(payload or [], ensure_ascii=False)


class TestDeltaPlanning:
    def test_changed_indices_are_computed_by_difflib(self) -> None:
        """纯函数：给定两版段落，变更下标是算出来的，不依赖模型。"""
        old = delta_review.paragraph_texts(_old_bytes())
        new = delta_review.paragraph_texts(_new_bytes())
        assert delta_review.changed_paragraph_indices(old, new) == [2]

    def test_plan_reports_much_fewer_paragraphs_to_review(self) -> None:
        plan = delta_review.plan_delta(_old_bytes(), _new_bytes())
        assert plan.total_paragraphs == 5
        assert plan.reviewed == 1
        assert plan.reviewed < plan.total_paragraphs
        assert plan.unchanged is False

    def test_identical_document_is_flagged_unchanged(self) -> None:
        plan = delta_review.plan_delta(_old_bytes(), _old_bytes())
        assert plan.unchanged is True
        assert plan.reviewed == 0

    def test_delta_text_only_contains_changed_paragraphs(self) -> None:
        text = delta_review.build_delta_text(_new_bytes(), [2])
        assert NEW_TARGET in text
        for untouched in (UNCHANGED_1, UNCHANGED_2, UNCHANGED_3, UNCHANGED_4):
            assert untouched not in text

    def test_inserted_paragraph_counts_as_changed(self) -> None:
        grown = _docx(UNCHANGED_1, UNCHANGED_2, TARGET, "第三条之一 新增条款。", UNCHANGED_3, UNCHANGED_4)
        plan = delta_review.plan_delta(_old_bytes(), grown)
        assert plan.changed_indices == [3]


class TestCarryForward:
    def test_present_moot_and_stale_are_separated(self) -> None:
        """三条典型结论各自流转：仍存在 / 已被消解 / 锚点失效。"""
        prev = _prev_run()
        # 「仍存在」的锚点必须在新版本里**还在**：拿被改掉的那段当锚点只会测出 stale
        still_there = _finding(
            prev,
            ordinal=0,
            quote=UNCHANGED_3,
            suggestion_original=UNCHANGED_3,
            suggestion_replacement="改成别的写法",
        )
        already_done = _finding(prev, ordinal=1, suggestion_replacement=NEW_TARGET)
        anchor_gone = _finding(
            prev,
            ordinal=2,
            quote="这句话在最新版本里已经不存在了",
            suggestion_original="这句话在最新版本里已经不存在了",
            suggestion_replacement="某种改写",
        )

        buckets = delta_review.carry_forward(prev, _new_bytes())

        assert buckets["present"] == [still_there.id]
        assert buckets["moot"] == [already_done.id]
        assert buckets["stale"] == [anchor_gone.id]

        still_there.refresh_from_db()
        already_done.refresh_from_db()
        anchor_gone.refresh_from_db()
        # 仍存在的保持待决（等律师再决策），其余两个是终态
        assert still_there.status == FindingStatus.PROPOSED
        assert already_done.status == FindingStatus.MOOT
        assert anchor_gone.status == FindingStatus.STALE

    def test_already_decided_findings_are_left_alone(self) -> None:
        prev = _prev_run()
        rejected = _finding(prev, status=FindingStatus.REJECTED, reject_reason_code="commercial")
        buckets = delta_review.carry_forward(prev, _new_bytes())
        assert rejected.id not in buckets["present"] + buckets["moot"] + buckets["stale"]


class TestRunDeltaReview:
    def test_second_round_reviews_only_delta_and_carries_forward(self) -> None:
        prev = _prev_run()
        kept = _finding(
            prev, quote=UNCHANGED_3, suggestion_original=UNCHANGED_3, suggestion_replacement="改成别的写法"
        )

        run = delta_review.run_delta_review(
            prev, caller=_caller([]), new_bytes=_new_bytes(), old_bytes=_old_bytes()
        )

        assert run.parent_run_id == prev.id
        assert run.summary["delta"]["total_paragraphs"] == 5
        assert run.summary["delta"]["paragraphs_reviewed"] == 1
        assert run.summary["delta"]["carried"] == 1
        # 上一轮的结论被带进新一轮，律师看到的是完整待办
        assert run.findings.count() == 1
        assert run.findings.first().title == kept.title

    def test_prompt_only_contains_changed_text(self) -> None:
        prev = _prev_run()
        seen: list[str] = []

        def caller(messages: list[dict[str, str]]) -> str:
            seen.append("\n".join(m["content"] for m in messages))
            return "[]"

        delta_review.run_delta_review(prev, caller=caller, new_bytes=_new_bytes(), old_bytes=_old_bytes())

        assert NEW_TARGET in seen[0]
        assert UNCHANGED_1 not in seen[0]

    def test_unchanged_document_is_idempotent_and_skips_model(self) -> None:
        """文件没变：不调模型，清单不翻倍。"""
        prev = _prev_run()
        _finding(prev)

        def caller(_messages: list[dict[str, str]]) -> str:
            raise AssertionError("文档没变时不应该调模型")

        first = delta_review.run_delta_review(prev, caller=caller, new_bytes=_old_bytes(), old_bytes=_old_bytes())
        assert first.summary["delta"]["unchanged"] is True
        assert first.summary["delta"]["paragraphs_reviewed"] == 0
        assert first.findings.count() == 1

        second = delta_review.run_delta_review(prev, caller=caller, new_bytes=_old_bytes(), old_bytes=_old_bytes())
        assert second.findings.count() == 1  # 不会变成 2

    def test_inherits_previous_playbook_snapshot(self) -> None:
        """沿用上一轮的标准快照：标准改版不该改变对历史版本的判断。"""
        prev = _prev_run(playbook_snapshot=[{"rule_key": "only.one", "clause_type": "x", "standard_text": "旧标准"}])
        run = delta_review.run_delta_review(
            prev, caller=_caller([]), new_bytes=_new_bytes(), old_bytes=_old_bytes()
        )
        assert run.playbook_snapshot == prev.playbook_snapshot

    def test_new_findings_from_delta_are_added(self) -> None:
        prev = _prev_run()
        payload = [
            {
                "rule_key": "performance.deadline",
                "verdict": "deviation",
                "severity": "high",
                "quote": NEW_TARGET,
                "title": "十五日仍偏紧",
                "reason": "交付能力需确认",
                "impact": "逾期违约金 5 万元",
            }
        ]
        run = delta_review.run_delta_review(
            prev, caller=_caller(payload), new_bytes=_new_bytes(), old_bytes=_old_bytes()
        )
        assert run.summary["delta"]["new"] == 1
        assert any(f.title == "十五日仍偏紧" for f in run.findings.all())

    def test_previous_run_is_superseded(self) -> None:
        prev = _prev_run()
        delta_review.run_delta_review(prev, caller=_caller([]), new_bytes=_new_bytes(), old_bytes=_old_bytes())
        prev.refresh_from_db()
        assert prev.status == RunStatus.SUPERSEDED


class TestReviewPipelineStillSane:
    def test_full_review_unchanged(self) -> None:
        """delta 改动不该影响首轮全篇审查的行为。"""
        run = review_pipeline.run_review(
            kind="contract",
            owner_id=1118,
            subpath="1-合同/a.docx",
            caller=_caller([]),
            text=TARGET,
            raw_bytes=_old_bytes(),
        )
        assert run.status == RunStatus.DONE
        assert run.parent_run_id is None
