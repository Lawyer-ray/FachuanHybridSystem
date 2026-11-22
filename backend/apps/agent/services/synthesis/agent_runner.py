"""综合结论 —— 交给**指定的 agent 运行时**生成（而不是一次裸 LLM 调用）。

## 为什么改成跑 agent

裸调用（`chat/aggregate._llm_aggregate`）只能"转述候选"：它没有工具，无法核实
候选里的法条与案号，`Synthesis.unverified` 因此恒为 `[]`（契约里有字段、
前端有渲染块，却永远不出现）。

跑 agent 之后它能：

1. 在**新开的上下文**里读下五栏全文（模型窗口声明 1M，
   见 `pi/model_config.DEFAULT_CONTEXT_WINDOW`），不受会话历史干扰；
2. 自己调 `verify_citations` / 检索工具去核引用；
3. 像普通一栏那样带审批闸门与审计（走的是同一个 `AgentBackend`）。

## 三个刻意的口径

- **不落 assistant 消息**：综合结果只进 `AgentSynthesis`，不进会话转录。落成
  "第 6 栏"会和五栏并答的语义混在一起（`agent_kind` 写什么都不对），而且历史
  回放靠合成表已经够了。
- **不记成本**：不写 `AgentRun`。综合是"律师点一次"的动作，成本归因价值低，
  而多一张运行记录会让"本轮几栏/多少钱"的统计口径变复杂。
- **默认 `pi`**：后端注册表里最稳的一个；调用方可以换成任意已注册 kind。

## 失败口径

- 拿不到正文 → `LLMError`（API 转 502）；
- 正文缺来源锚点（`[来源：`）→ 视为没拿到可用结论，重试一次；仍缺就报错
  —— 宁可让律师重试，也不要给一份"看不出谁说的"综合稿。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from apps.agent.services.chat.aggregate import AGGREGATE_SYSTEM_PROMPT, ANCHOR_MARKER, Candidate, render_candidate
from apps.core.llm.exceptions import LLMError

logger = logging.getLogger(__name__)

#: 默认用哪个 agent 跑综合。可被请求覆盖。
DEFAULT_SYNTHESIS_KIND = "pi"

#: 综合 agent 的最大轮数。比普通一栏小：它是"读五份稿 + 必要时核引用"，
#: 不需要几十轮工具循环；太大只会在跑偏时烧更多钱。
SYNTHESIS_MAX_TURNS = 8

#: 一次综合最多允许的尝试次数（缺锚点 / 空正文时重试）。与裸调用同口径。
SYNTHESIS_AGENT_ATTEMPTS = 2


@dataclass(frozen=True)
class SynthesisRun:
    """一次成功的综合运行（正文 + 实际模型）。"""

    text: str
    model: str


def build_synthesis_prompt(
    task: str,
    candidates: Sequence[Candidate],
    *,
    review_summary: str = "",
) -> str:
    """装配综合 agent 的**输入正文**（纯函数，便于单测）。

    system prompt 复用 `chat/aggregate.AGGREGATE_SYSTEM_PROMPT`——那份是 MoA
    aggregator 的口径加本仓库三条补充（来源锚点 / 只用候选里的依据 / 分歧要写明），
    换运行时不该换规则。这里只负责把"问题 + 评审结论 + 各栏全文"拼成一段用户输入。

    评审结论放在候选**之前**：先给"哪栏更可靠"，再让 agent 读原文，避免它读完五份
    才开始想"该信谁"而忽略分数。
    """
    parts: list[str] = [f"问题：\n{task}"]
    if review_summary.strip():
        parts.append(
            "以下是**已完成的评审结论**（含每栏分数与共识/分歧）。请以它作为取舍依据；"
            "评审与你的判断冲突时，说明你为什么不采纳评审：\n\n" + review_summary.strip()
        )
    blocks = "\n\n".join(render_candidate(index, candidate) for index, candidate in enumerate(candidates, start=1))
    parts.append(f"候选回答（共 {len(candidates)} 份，每份以【栏名 · 模型】开头）：\n\n{blocks}")
    parts.append("现在输出综合结论正文。")
    return "\n\n".join(parts)


def synthesis_system_prompt() -> str:
    """综合 agent 的 system prompt（**全量替换**运行时的默认预设）。

    为什么要写死在代码里而不是交给调用方：pi / claude-agent 这类 harness 默认是
    "命令行编码助手"（antigravity 就踩过——不全量替换它会自称 DeepMind 的编程助手）。
    综合这一轮的身份是"资深中国律师做多稿合并"，任何残留的编码助手人格都会污染结论。
    """
    return AGGREGATE_SYSTEM_PROMPT


def validate_synthesis_text(text: str) -> str:
    """校验综合正文；返回**不通过的原因**（`""` = 通过）。

    只有两条硬门槛，都不涉及内容质量（质量没法在代码里判）：

    1. 非空；
    2. 含来源锚点 ``[来源：`` —— 它是"这段结论可回溯到具体某一栏"的唯一信号。
       缺锚点的文本可能是模型把思考过程当正文吐了（实测过），也可能是它自己
       编了一段没有出处的结论；两种都不能当综合稿。
    """
    if not text.strip():
        return "empty"
    if ANCHOR_MARKER not in text:
        return "no_anchor"
    return ""


async def run_synthesis_agent(
    *,
    session: Any,
    user_id: int | None,
    kind: str,
    model: str | None,
    prompt: str,
    run_id: str,
) -> SynthesisRun:
    """跑一轮综合 agent，收齐正文。

    Args:
        kind: agent 后端标识（注册表键）。未注册时抛 ``LLMError``（API 转 422）。
        model: 指定模型；``None`` 让后端自己按平台默认解析。
        run_id: 本轮归因串。综合不写 ``AgentRun``，但审批与日志仍用它。

    Raises:
        LLMError: 后端不可用 / 未注册 / 两轮都没拿到带锚点的正文。
    """
    from apps.agent.backends import registry
    from apps.agent.backends.base import BackendError, RunContext
    from apps.agent.backends.builtin import ensure_registered
    from apps.agent.services.chat import env

    ensure_registered()
    try:
        backend = registry.get(kind)
    except LookupError as exc:
        raise LLMError(f"综合用的 agent 未注册: {kind}") from exc

    last_reason = ""
    for attempt in range(SYNTHESIS_AGENT_ATTEMPTS):
        attempt_prompt = prompt if attempt == 0 else prompt + "\n\n再次强调：每条实质结论后必须标 [来源：栏名]。"
        ctx = RunContext(
            run_id=f"{run_id}:{attempt + 1}" if attempt else run_id,
            session=session,
            user_id=user_id,
            prompt=attempt_prompt,
            # 工具凭证：综合要能调 verify_citations。铸不出来就整轮拒绝——不能让
            # 工具退回超管服务账号（见 pi/user_token.py 的 confused deputy 说明）。
            user_token=await env.mint_user_token(user_id),
            model=model,
            tool_selection=None,
        )
        chunks: list[str] = []
        try:
            async for frame in backend.stream(ctx):
                if not frame:
                    continue
                if frame.get("type") == "delta":
                    chunks.append(str(frame.get("content") or ""))
                elif frame.get("type") == "error":
                    raise LLMError(f"综合 agent 报错: {frame.get('message') or frame.get('detail') or '未知错误'}")
        except BackendError as exc:
            raise LLMError(f"综合 agent 失败: {exc}") from exc

        text = "".join(chunks).strip()
        reason = validate_synthesis_text(text)
        if not reason:
            result = getattr(backend, "result_for", None)
            used = ""
            if callable(result):
                run_result = result(ctx.run_id)
                used = str(getattr(run_result, "model", "") or "")
            return SynthesisRun(text=text, model=used or (model or ""))
        last_reason = reason
        logger.warning("综合结论未通过校验（第 %s 次）：%s kind=%s", attempt + 1, reason, kind)

    raise LLMError(f"综合结论未通过校验（{last_reason}），请重试或换一个 agent")
