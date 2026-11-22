"""综合结论 —— 交给**指定的 agent 运行时**生成（而不是一次裸 LLM 调用）。

## 为什么改成跑 agent

裸调用只能"转述候选"：它没有工具，无法核实候选里的法条与案号。跑 agent 之后它能：

1. 在**隔离的上下文**里读五栏全文（``RunContext.isolated=True``：不读也不写本会话
   在运行时侧的对话历史，见下）；
2. 自己调 `verify_citations` / 检索工具去核引用；
3. 像普通一栏那样带审批闸门与审计（走的是同一个 `AgentBackend`）。

## 本轮下发给运行时的三个参数

- ``system_prompt``：`chat/aggregate.AGGREGATE_SYSTEM_PROMPT`，**全量替换**运行时默认人格
  （来源锚点 / 只用候选依据 / 分歧写明这三条规则只靠它下发）；
- ``max_turns``：:data:`SYNTHESIS_MAX_TURNS`；
- ``isolated=True``：综合要读五栏全文、写一份长结论，落进某一栏的会话历史会污染那一栏的
  下一轮（pi 曾按会话 id 续接同一份 session 文件）。审批路由仍用真实会话。

做不到这三条的后端（如 dsh）在入口报 ``BackendError``，这里转成 ``LLMError``。

## 落库口径（由调用方完成，本模块只产出正文）

- 快照进 `AgentSynthesis`；正文另写一条 ``agent_kind="synthesis"`` 的 assistant 消息进
  会话转录（见 ``store.save_synthesis_message``），不算任何一栏的回答；
- 不写 `AgentRun`（不记成本）。

## 失败口径

- 拿不到正文 / 后端报错 → `LLMError`；
- 正文缺来源锚点（`[来源：`）→ 视为没拿到可用结论，重试一次；仍缺就报错；
- 取消（``asyncio.CancelledError``）原样上抛，不转成 `LLMError`。
"""

from __future__ import annotations

import contextlib
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

#: 一次综合最多允许的尝试次数（缺锚点 / 空正文时重试一次）。
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

    经 ``RunContext.system_prompt`` 下发：openai-agents / antigravity / claude-agent 替换
    整段 system prompt；pi 替换的是隔离目录里的 ``AGENTS.md``（法穿给 pi 注入人格的
    唯一挂载点，pi 自带的基础提示仍在）。
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
    """跑一轮综合 agent（隔离运行），收齐正文。

    Args:
        kind: agent 后端标识（注册表键）。未注册时抛 ``LLMError``。
        model: 指定模型；``None`` 让后端自己按平台默认解析。
        run_id: 本轮归因串。综合不写 ``AgentRun``，但审批与日志仍用它。

    Raises:
        LLMError: 后端不可用 / 未注册 / 不支持隔离运行 / 两轮都没拿到带锚点的正文。
        asyncio.CancelledError: 调用方取消时原样上抛（不转成 ``LLMError``）。
    """
    from apps.agent.backends import registry
    from apps.agent.backends.base import BackendError, RunContext
    from apps.agent.backends.builtin import ensure_registered
    from apps.agent.pi.pool import PoolQueueTimeoutError
    from apps.agent.pi.rpc_client import PiError
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
            system_prompt=synthesis_system_prompt(),
            max_turns=SYNTHESIS_MAX_TURNS,
            isolated=True,
        )
        chunks: list[str] = []
        try:
            # ``aclosing``：提前退出（报错帧 / 取消）时立刻收掉后端生成器，让它的
            # finally（关进程、删隔离目录）当场执行，而不是等垃圾回收。
            async with contextlib.aclosing(backend.stream(ctx)) as frames:
                async for frame in frames:
                    if not frame:
                        continue
                    if frame.get("type") == "delta":
                        chunks.append(str(frame.get("content") or ""))
                    elif frame.get("type") == "error":
                        raise LLMError(f"综合 agent 报错: {frame.get('message') or frame.get('detail') or '未知错误'}")
        except (BackendError, PiError, PoolQueueTimeoutError) as exc:
            # pi 后端把 PiError / 排队超时原样外抛（由聊天编排层翻译），综合没有那一层，
            # 在这里一并转成 LLMError。取消是 BaseException，不在此列，原样上抛。
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
