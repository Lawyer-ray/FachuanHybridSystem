"""评审编排：多栏 × 多 rubric 的并发判定。

口径（与 ``docs/analysis/adjudication-2026-11-20/01-rubric.md`` §6.3/§6.7）：

- **失败票不进分母**：判不了/调用失败落 ``criteria_met=None``，既不进
  ``LaneReview.valid``，也不会被当成"答错"；``valid == 0`` 时分数是 null，
  绝不回落成 0 分。
- **全局 Semaphore**：N 栏 × M 条会同时产生 N×M 个 judge 调用，不给闸门会
  把 provider 的并发额度一次打满。闸门是进程级全局的，多个请求共享同一个上限。
- **多数门槛**：``passed = yes * 2 > valid``（见 ``score.majority_passed``）。

本模块只做编排与契约转换；prompt 拼装、调用重试、分数结算分别在
``judge_prompt`` / ``judge_client`` / ``rubric`` / ``score``。
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence

from ..adjudication.contracts import CriteriaVerdict, Review
from .judge_client import JudgeCall, JudgeOutcome, judge_with_retry
from .judge_prompt import ParsedVerdict
from .rubric import RubricItem
from .score import build_review

#: 同时在飞的 judge 调用上限。``01-rubric.md`` §6.7 的 ``JUDGE_CONCURRENCY=8``。
JUDGE_CONCURRENCY = 8
#: 进程级全局闸门（不是每请求一个）：并发额度属于 provider，不属于某次评审。
JUDGE_SEMAPHORE = asyncio.Semaphore(JUDGE_CONCURRENCY)


def _criterion_text(item: RubricItem) -> str:
    """把分值拼进判定项文本（负分项要让 judge 看到符号，它才知道极性）。"""
    return f"[{item.points:g}] {item.criterion}"


async def _judge_lane_item(
    *,
    lane: str,
    item: RubricItem,
    task: str,
    submission: str,
    judge_models: list[str],
    call_judge: JudgeCall | None,
) -> tuple[CriteriaVerdict, JudgeOutcome]:
    """判定一条 rubric；空候选正文不浪费调用，直接记 ``empty_response``。"""
    if not submission.strip():
        outcome = JudgeOutcome(
            parsed=ParsedVerdict(unscored_reason="empty_response"),
            judge_model="",
            attempts=0,
        )
        return _to_contract(lane, item, outcome), outcome

    async with JUDGE_SEMAPHORE:
        outcome = await judge_with_retry(
            channel=lane,
            task=task,
            submission=submission,
            criterion=_criterion_text(item),
            judge_models=judge_models,
            call_judge=call_judge,
        )
    return _to_contract(lane, item, outcome), outcome


def _to_contract(lane: str, item: RubricItem, outcome: JudgeOutcome) -> CriteriaVerdict:
    parsed = outcome.parsed
    return CriteriaVerdict(
        rubric_id=item.id,
        lane=lane,
        criteria_met=parsed.criteria_met,
        explanation=parsed.explanation,
        evidence_quote=parsed.evidence_quote,
        judge_model=outcome.judge_model,
        attempts=outcome.attempts,
        unscored_reason=parsed.unscored_reason if parsed.criteria_met is None else "",
    )


async def run_jury(
    *,
    session_id: str,
    turn: int,
    task: str,
    answers: Mapping[str, str],
    rubric: Sequence[RubricItem],
    judge_models: Sequence[str],
    call_judge: JudgeCall | None = None,
    review_id: str | None = None,
    rubric_id: str = "",
    rubric_version: str = "",
) -> Review:
    """对一轮多栏回答跑完整评审。

    ``answers`` 的键是栏名（``agent_kind``），顺序即 ``Review.lanes`` 的顺序。
    每条 rubric 对每栏独立判定——**不做跨栏投票**：不同模型的不同回答没有
    共同的"正确答案"可投。
    """
    lanes = list(answers)
    jobs = [
        _judge_lane_item(
            lane=lane,
            item=item,
            task=task,
            submission=answers[lane],
            judge_models=list(judge_models),
            call_judge=call_judge,
        )
        for lane in lanes
        for item in rubric
    ]
    results = await asyncio.gather(*jobs)

    verdicts = [verdict for verdict, _ in results]
    prompt_tokens = sum(outcome.prompt_tokens for _, outcome in results)
    completion_tokens = sum(outcome.completion_tokens for _, outcome in results)
    total_tokens = sum(outcome.total_tokens for _, outcome in results)
    return build_review(
        session_id=session_id,
        turn=turn,
        items=rubric,
        verdicts=verdicts,
        lanes=lanes,
        tokens={
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens,
        },
        review_id=review_id,
        rubric_id=rubric_id,
        rubric_version=rubric_version,
    )
