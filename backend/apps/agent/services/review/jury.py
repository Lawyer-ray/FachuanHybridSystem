"""评审编排：多栏 × 多 rubric 的并发判定。

口径（与 ``docs/analysis/adjudication-2026-11-20/01-rubric.md`` §6.3/§6.7）：

- **失败票不进分母**：判不了/调用失败落 ``criteria_met=None``，既不进
  ``LaneReview.valid``，也不会被当成"答错"；``valid == 0`` 时分数是 null，
  绝不回落成 0 分。
- **全局 Semaphore**：N 栏 × M 条会同时产生 N×M 个 judge 调用，不给闸门会
  把 provider 的并发额度一次打满。闸门是进程级全局的，多个请求共享同一个上限。
- **多数门槛**：``passed = yes * 2 > valid``（见 ``score.majority_passed``）。
- **成团是打分之后的独立阶段**：有效栏 ≥2 才跑（单栏没有"跨栏立场"可判），失败一律
  ``clusters=[]`` + ``clusters_error=<原因>``，**绝不把失败展示成"三份全异"**。

本模块只做编排与契约转换；prompt 拼装、调用重试、分数结算分别在
``judge_prompt`` / ``judge_client`` / ``rubric`` / ``score``，判等实现与并发口径在 ``entail``。
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import cast

from apps.core.llm.exceptions import LLMError

from ..adjudication.contracts import CriteriaVerdict, EquivalenceCluster, Review
from ..chat.equivalence import EntailsFn, cluster_answers
from .entail import describe_failures, make_entails
from .judge_client import JudgeCall, JudgeOutcome, judge_with_retry
from .judge_prompt import ParsedVerdict
from .rubric import RubricItem
from .score import build_review

#: 同时在飞的 judge 调用上限。``01-rubric.md`` §6.7 的 ``JUDGE_CONCURRENCY=8``。
JUDGE_CONCURRENCY = 8
#: 进程级全局闸门（不是每请求一个）：并发额度属于 provider，不属于某次评审。
JUDGE_SEMAPHORE = asyncio.Semaphore(JUDGE_CONCURRENCY)
#: ``Review.clusters_error`` 的上限（模型列是 200 字符）。
CLUSTERS_ERROR_LIMIT = 200


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


def _failure_reason(error: BaseException) -> str:
    """成团阶段的异常 → 一句给律师看的原因（前端显示「未成团：<原因>」）。"""
    if isinstance(error, TimeoutError):
        return "判等阶段超时"
    message = str(error).strip()
    name = type(error).__name__
    return f"成团异常（{name}）：{message}" if message else f"成团异常（{name}）"


async def _cluster_lanes(
    answers: Mapping[str, str],
    judge_models: Sequence[str],
    call_judge: JudgeCall | None,
) -> tuple[list[EquivalenceCluster], str]:
    """把有效栏的回答成团（``clusters_error`` 空串 = 成功）。

    三态：

    - 有效栏 < 2：**不跑**成团，也不报错（``([], "")``）——单栏没有跨栏立场可判；
    - 跑成功且每条边都判出来：返回簇，错误空串（含"真的全异 / 平票"，那是 ``tie``）；
    - 判等有边没判出来 / 抛异常 / 阶段超时：``([], 原因)``。

    最后一条是重点：``cluster_answers`` 拿到 None 只会不连边，全判不了时它诚实返回
    "全是单例 + tie"，但那与"三份真的全异"是两件事。所以有 ``entails.failed`` 就整段
    作废并报原因，宁可这一栏不展示共识，也不能让律师把"没判出来"读成"三家各说各的"。
    """
    usable = [lane for lane, answer in answers.items() if answer.strip()]
    if len(usable) < 2:
        return [], ""
    models = [model for model in judge_models if model.strip()]
    if not models:
        return [], "无可用评审模型"

    entails = make_entails(models, call_judge=call_judge)
    try:
        # 判等是 I/O，先并发预取；cluster_answers 只是纯查表（微秒级），不需要开线程。
        await entails.prefetch(usable)
        clusters = cluster_answers(usable, cast(EntailsFn, entails))
    except asyncio.CancelledError:
        raise
    except (LLMError, OSError, ValueError, RuntimeError) as error:
        return [], _failure_reason(error)[:CLUSTERS_ERROR_LIMIT]

    if entails.failed:
        return [], describe_failures(entails)[:CLUSTERS_ERROR_LIMIT]
    return clusters, ""


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

    打分完成后才跑成团：判等要拿两份完整回答两两比，先跑打分能让分数先出来，
    也让成团的失败只影响 ``clusters`` / ``clusters_error`` 两个字段（不影响打分结果）。
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
    review = build_review(
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
    clusters, clusters_error = await _cluster_lanes(answers, judge_models, call_judge)
    # build_review 是纯汇总（无 I/O），成团要调 judge，不能塞进那个纯函数；
    # 用 model_copy 而不是就地赋值，让"成团结果是在汇总之后补上的"这件事留在代码里。
    return review.model_copy(update={"clusters": clusters, "clusters_error": clusters_error})
