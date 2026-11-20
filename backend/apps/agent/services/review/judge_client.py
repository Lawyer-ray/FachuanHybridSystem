"""judge 调用：走统一 LLM 客户端，有限重试，绝不无限循环。

三条硬约束：

1. **只走** ``apps.core.llm.client``（经 ``get_llm_service()``）。判定请求和
   普通对话共用 provider 配置、key 池、降级与审计；自建 HTTP 客户端会让
   "这家 judge 到底花了多少钱"在账上消失。
2. **显式超时**：既把 ``timeout_seconds`` 传给后端（底层据此建 HTTP 客户端），
   又用 ``asyncio.wait_for`` 兜一层硬闸——后端若忽略 kwarg，单条判定也不会
   把整次评审挂住。
3. **重试上限 2 次**：第 2 次换下一个 judge 模型并指数退避。没有
   ``while True``——协议解析失败时无限重试只会把"judge 不稳定"变成"账单失控"。
"""

from __future__ import annotations

import asyncio
import random
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from apps.core.llm.exceptions import LLMTimeoutError
from apps.core.llm.service import get_llm_service

from .judge_prompt import ParsedVerdict, build_prompt, parse_verdict

#: 单条判定的总尝试次数（含首次）。
JUDGE_MAX_ATTEMPTS = 2
#: 单次调用的硬超时（秒）。计划文档 §6.3 的 ``JUDGE_PER_ITEM_TIMEOUT``。
JUDGE_TIMEOUT_SECONDS = 60.0
#: judge 输出很短（一个 JSON 对象），不需要长输出预算。
JUDGE_MAX_TOKENS = 512
#: 指数退避基数 / 上限 / 抖动（秒），口径见计划文档 §6.7。
JUDGE_BACKOFF_BASE = 0.5
JUDGE_BACKOFF_CAP = 4.0
JUDGE_BACKOFF_JITTER = 0.3

_REASON_TIMEOUT = "timeout"
_REASON_JUDGE_ERROR = "judge_error"
_REASON_EMPTY = "empty_response"


@dataclass(frozen=True)
class JudgeReply:
    """一次成功的 judge 调用（正文 + 成本）。"""

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class JudgeOutcome:
    """一条 rubric 的最终判定（含重试次数与累计成本）。"""

    parsed: ParsedVerdict
    judge_model: str
    attempts: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


#: 可注入的判定调用：``(prompt, judge_model) -> JudgeReply``。
#: 生产路径是 ``_llm_judge``；单测注入假实现，失败路径不依赖真实网关。
JudgeCall = Callable[[str, str], Awaitable[JudgeReply]]


async def _llm_judge(prompt: str, judge_model: str) -> JudgeReply:
    """走统一 LLM 门面调一次 judge（生产实现）。"""
    response = await get_llm_service().achat(
        messages=[{"role": "user", "content": prompt}],
        model=judge_model,
        temperature=0.0,
        max_tokens=JUDGE_MAX_TOKENS,
        # 后端用这个 kwarg 建 HTTP 客户端；不给就退回 provider 默认值。
        timeout_seconds=JUDGE_TIMEOUT_SECONDS,
        caller="agent.review.judge",
    )
    return JudgeReply(
        content=str(getattr(response, "content", "") or ""),
        model=str(getattr(response, "model", "") or judge_model),
        prompt_tokens=int(getattr(response, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(response, "completion_tokens", 0) or 0),
        total_tokens=int(getattr(response, "total_tokens", 0) or 0),
    )


async def judge_once(*, prompt: str, judge_model: str, call_judge: JudgeCall | None = None) -> JudgeReply:
    """调一次 judge（不重试）；超时闸门对注入实现同样生效。"""
    call = call_judge or _llm_judge
    return await asyncio.wait_for(call(prompt, judge_model), timeout=JUDGE_TIMEOUT_SECONDS)


def _reason_for_error(error: BaseException) -> str:
    if isinstance(error, (TimeoutError, LLMTimeoutError)):
        return _REASON_TIMEOUT
    return _REASON_JUDGE_ERROR


def _backoff_seconds(attempt: int) -> float:
    """第 ``attempt`` 次失败后的等待时间（0 起，含抖动）。"""
    base = min(JUDGE_BACKOFF_BASE * (2**attempt), JUDGE_BACKOFF_CAP)
    return float(base + random.uniform(0, JUDGE_BACKOFF_JITTER))


async def judge_with_retry(
    *,
    channel: str,
    task: str,
    submission: str,
    criterion: str,
    judge_models: list[str],
    call_judge: JudgeCall | None = None,
) -> JudgeOutcome:
    """判定一条 rubric：最多 ``JUDGE_MAX_ATTEMPTS`` 次，失败时换 judge。

    每次尝试都生成新 nonce（重发同一段被判正文时，旧的 prompt 可能已经被
    上游缓存或污染）；第 2 次循环取 ``judge_models`` 里的下一个模型。
    """
    models = [model for model in judge_models if model.strip()]
    if not models:
        return JudgeOutcome(parsed=ParsedVerdict(unscored_reason=_REASON_JUDGE_ERROR), judge_model="", attempts=0)

    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    last = ParsedVerdict(unscored_reason=_REASON_JUDGE_ERROR)
    used_model = ""

    for attempt in range(JUDGE_MAX_ATTEMPTS):
        used_model = models[attempt % len(models)]
        prompt = build_prompt(
            channel,
            secrets.token_hex(4),
            task=task,
            submission=submission,
            criterion=criterion,
        )
        try:
            reply = await judge_once(prompt=prompt, judge_model=used_model, call_judge=call_judge)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            last = ParsedVerdict(unscored_reason=_reason_for_error(error))
        else:
            prompt_tokens += reply.prompt_tokens
            completion_tokens += reply.completion_tokens
            total_tokens += reply.total_tokens
            used_model = reply.model
            if not reply.content.strip():
                last = ParsedVerdict(unscored_reason=_REASON_EMPTY)
            else:
                parsed = parse_verdict(reply.content)
                if parsed.scored:
                    return JudgeOutcome(
                        parsed=parsed,
                        judge_model=used_model,
                        attempts=attempt + 1,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    )
                last = parsed

        if attempt + 1 < JUDGE_MAX_ATTEMPTS:
            await asyncio.sleep(_backoff_seconds(attempt))

    return JudgeOutcome(
        parsed=last,
        judge_model=used_model,
        attempts=JUDGE_MAX_ATTEMPTS,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
