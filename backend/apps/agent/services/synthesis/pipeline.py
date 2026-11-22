"""综合结论的完整流水线：**(可选)评审 → 组 prompt → 跑 agent → 核验引用 → 落库**。

它在后台任务里执行（见 ``jobs.py``），不在 HTTP 请求里：评审（多 judge，约 5 万 token）
+ agent 综合（最多 2 次）+ 威科核验串起来常常超过几分钟，同步请求必然先被前端或反代
超时掐断，而后端照样跑完、照样花钱。

## 取消

流水线里每一处「失败不阻断」的降级（前置评审、写转录；核验在 ``verify.py``）都先放行
:data:`control_flow.MUST_PROPAGATE`：取消必须一路上抛到任务边界（``jobs._supervise``），
在那里记为 ``cancelled``。吞掉取消等于取消无效。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from ..adjudication.contracts import DroppedCandidate, Review, Synthesis
from ..chat.aggregate import Candidate, extract_citations, partition_candidates
from .agent_runner import DEFAULT_SYNTHESIS_KIND, build_synthesis_prompt, run_synthesis_agent
from .control_flow import MUST_PROPAGATE
from .store import load_turn_candidates, resolve_model, save_synthesis, save_synthesis_message
from .verify import verify_synthesis_citations

logger = logging.getLogger(__name__)

#: 流水线阶段（落到任务的 ``stage`` 上，前端据此显示「评审中 / 综合中 / 核验中」）。
STAGE_REVIEW = "review"
STAGE_SYNTHESIS = "synthesis"
STAGE_VERIFY = "verify"
STAGE_SAVING = "saving"

#: 阶段回调：每进入一个阶段调用一次（任务层借它写 stage 并刷新心跳）。
StageCallback = Callable[[str], Awaitable[None]]


class NoUsableCandidatesError(ValueError):
    """本轮所有候选都为空或失败：没有可综合的内容（不调模型，省一次无意义的钱）。"""


@dataclass(frozen=True)
class SynthesisRequest:
    """一次综合的参数（落在任务的 ``params`` 里，后台按它重放）。"""

    turn: int
    lanes: list[str]
    model: str = ""
    kind: str = DEFAULT_SYNTHESIS_KIND
    review: bool = True
    credential_id: int | None = None

    def to_params(self) -> dict[str, Any]:
        """→ 任务 ``params``（``turn`` 单独存在任务行上）。"""
        return {
            "agents": list(self.lanes),
            "model": self.model,
            "kind": self.kind,
            "review": self.review,
            "credential_id": self.credential_id,
        }

    @classmethod
    def from_params(cls, turn: int, params: dict[str, Any]) -> SynthesisRequest:
        credential_id = params.get("credential_id")
        return cls(
            turn=int(turn),
            lanes=[str(lane) for lane in params.get("agents") or []],
            model=str(params.get("model") or ""),
            kind=str(params.get("kind") or DEFAULT_SYNTHESIS_KIND),
            review=bool(params.get("review", True)),
            credential_id=int(credential_id) if credential_id else None,
        )


async def load_usable_candidates(
    session: Any, turn: int, lanes: Sequence[str]
) -> tuple[str, list[Candidate], list[DroppedCandidate]]:
    """读本轮问题与候选，并按 empty / failed 分出不进 prompt 的栏。

    Raises:
        LookupError: 该轮次不存在。
        NoUsableCandidatesError: 全部候选为空或失败。
    """
    task, candidates = await load_turn_candidates(session, turn, lanes)
    used, dropped = partition_candidates(candidates)
    if not used:
        raise NoUsableCandidatesError("没有可综合的候选：全部为空或失败")
    return task, used, dropped


async def _noop_stage(_stage: str) -> None:
    return None


async def run_synthesis_pipeline(
    *,
    session: Any,
    user_id: int | None,
    user: Any,
    request: SynthesisRequest,
    run_id: str,
    on_stage: StageCallback = _noop_stage,
) -> Any:
    """跑完一次综合并落库，返回落库的 ``AgentSynthesis`` 行。

    Args:
        user: 发起人（核验与凭证解析按它判律所归属）。后台任务里由 ``user_id`` 重新
            加载，不依赖 HTTP 请求对象。
        run_id: 本次归因串（按任务唯一，审批与日志用它区分并发的两次综合）。
        on_stage: 阶段回调，见 :data:`StageCallback`。

    Raises:
        LookupError / NoUsableCandidatesError: 轮次不存在 / 没有可综合的候选。
        LLMError: 综合 agent 失败或两次都没产出带来源锚点的正文。
        asyncio.CancelledError: 被取消（原样上抛，由任务边界记为 cancelled）。
    """
    task, used, dropped = await load_usable_candidates(session, request.turn, request.lanes)

    review_summary = ""
    if request.review:
        await on_stage(STAGE_REVIEW)
        review_summary = await run_review_summary(
            session=session, user_id=user_id, turn=request.turn, lanes=request.lanes
        )

    model = (request.model or "").strip()
    if not model:
        # 「自动」：先取本轮某栏实际用过的模型（resolve_model）；本轮没有任何一栏留下
        # 模型名时交给所选 agent 按平台默认解析——那一步解析不出，运行时会给出可读错误。
        try:
            model = await resolve_model(session, request.turn, "")
        except ValueError:
            model = ""

    await on_stage(STAGE_SYNTHESIS)
    prompt = build_synthesis_prompt(task, used, review_summary=review_summary)
    run = await run_synthesis_agent(
        session=session,
        user_id=user_id,
        kind=request.kind,
        model=model or None,
        prompt=prompt,
        run_id=run_id,
    )

    await on_stage(STAGE_VERIFY)
    unverified, verify_note = await verify_synthesis_citations(
        text=run.text, credential_id=request.credential_id, user=user
    )
    # 有逐条未核验项时 note 是冗余的（它就是"共 N 条未通过"）；没有逐条项时
    # note 才是唯一信息（"未配置凭证" / "核验未执行：…"），必须留给前端。
    if verify_note and not unverified:
        unverified = [verify_note]

    synthesis = Synthesis(
        synthesis_id=uuid.uuid4().hex,
        session_id=str(session.session_id),
        turn=request.turn,
        text=run.text,
        model=run.model or model,
        lanes_used=[candidate.lane for candidate in used],
        dropped=dropped,
        citations=extract_citations(used),
        unverified=unverified,
        # 不记成本（业务方口径）：综合是一次点击动作，成本归因价值低。
        tokens={},
    )

    await on_stage(STAGE_SAVING)
    record = await save_synthesis(session=session, user_id=user_id, synthesis=synthesis)
    # 转录里也写一条 ``agent_kind="synthesis"``：历史回放 / 检索 / 后续追问都按消息表走。
    # 写失败只降级为"检索不到"，不影响已落库的快照；取消照样上抛。
    try:
        await save_synthesis_message(session=session, synthesis=synthesis)
    except MUST_PROPAGATE:
        raise
    except BaseException:
        logger.warning("综合结论写入转录失败（结论本身已落快照）session=%s", session.session_id, exc_info=True)
    return record


async def run_review_summary(*, session: Any, user_id: int | None, turn: int, lanes: list[str]) -> str:
    """跑一轮评审、**落库**，并把结论压成一段给综合看的文字；跑不成返回空串。

    **不阻断综合**：评审是"更准"的手段，不是前置条件。判官模型没配、评审报错，
    综合照样跑（只是少了取舍依据）。取消不是"报错"，原样上抛。

    **为什么要落库**：前端只有「生成综合结论」一个按钮，评审是它的第一步。不落库的话
    这份打分只喂给模型，律师看不到，审计里也查不到"这份综合是基于什么评的"。
    """
    from ..review.judge_models import configured_judge_models, resolve_judge_models
    from ..review.jury import run_jury
    from ..review.rubric import DEFAULT_RUBRIC_ID, load_rubric
    from ..review.store import load_turn_answers, load_turn_models, save_review

    try:
        rubric = load_rubric(DEFAULT_RUBRIC_ID)
        task, answers = await load_turn_answers(session, turn, lanes)
        turn_models = await load_turn_models(session, turn, lanes)
        judge_models = resolve_judge_models(requested=[], configured=configured_judge_models(), turn_models=turn_models)
        if not judge_models:
            return ""
        review = await run_jury(
            session_id=str(session.session_id),
            turn=turn,
            task=task,
            answers=answers,
            rubric=rubric,
            judge_models=judge_models,
            rubric_id=DEFAULT_RUBRIC_ID,
        )
        await save_review(
            session=session,
            user_id=user_id,
            rubric_id=DEFAULT_RUBRIC_ID,
            judge_models=judge_models,
            review=review,
        )
    except MUST_PROPAGATE:
        raise
    except BaseException:
        logger.warning("综合前置评审失败（不阻断综合）session=%s turn=%s", session.session_id, turn, exc_info=True)
        return ""
    return format_review(review)


def format_review(review: Review) -> str:
    """评审结果 → 一段纯文本（给 agent 读，不是给前端渲染）。"""
    lines: list[str] = []
    if review.headline:
        lines.append(f"一句话结论：{review.headline}")
    for lane in review.lanes:
        score = "" if lane.score is None else f"｜得分 {lane.score:.2f}"
        line = (lane.one_line or "").strip()
        lines.append(f"- {lane.lane}{score}" + (f"｜{line}" if line else ""))
    for cluster in review.clusters:
        lanes_in = "、".join(getattr(cluster, "lanes", []) or [])
        if lanes_in:
            lines.append(f"立场相同：{lanes_in}")
    if review.unverified:
        lines.append("本轮评审提到但没核到的引用：" + "；".join(review.unverified))
    return "\n".join(lines)


__all__ = [
    "STAGE_REVIEW",
    "STAGE_SAVING",
    "STAGE_SYNTHESIS",
    "STAGE_VERIFY",
    "NoUsableCandidatesError",
    "SynthesisRequest",
    "format_review",
    "load_usable_candidates",
    "run_review_summary",
    "run_synthesis_pipeline",
]
