"""综合结论 —— MoA aggregator 那一步：多份候选回答 → 一份可引用的合成稿。

## 口径来源

system prompt 抄 togethercomputer/MoA 的 aggregator 常量（``moa.py:17-19`` /
``utils.py:144-150``：要求聚合者**批判性评估**每份候选、不要简单复述某一份），
但补它缺的三件事（`docs/analysis/adjudication-2026-11-20/02-aggregation.md` §8）：

1. **候选带来源头**。MoA 只把候选编号成 ``1./2./3.``（``utils.py:150``），聚合者
   不知道哪份来自哪个模型，也没法在正文里标出来源。这里每份候选都带
   ``【栏名 · 模型】``，并要求正文逐条标 ``[来源：栏名]``——否则与
   ``services/chat/citations.py`` 的引用链断掉，律师没法回溯"这句话谁说的"。
2. **空 / 失败候选不进 prompt**。MoA 的 ``utils.py:47-51`` 把空字符串照样编号塞
   进 prompt，聚合者于是"参考"了一份空回答（还可能把它的沉默当成默认意见）。
   这里把它们挑出来放进 ``Synthesis.dropped``，附封闭集原因，**不静默丢**。
3. **不截断**（2026-11-22 改）。此前有 6000 字截断 + 2.4 万字整栏丢弃两档，
   前提是"窗口装不下"。现在模型声明 1M 上下文（见
   ``pi/model_config.DEFAULT_CONTEXT_WINDOW``），五栏全文一次喂进去绰绰有余，
   再截断只会让聚合者看不到后文的论证——那是**静默的质量损失**。

## 两种"没进 prompt"的表示

- ``Candidate.text is None`` → ``failed``：该栏本轮没落库正文（跑了但失败 / 崩了）；
- ``Candidate.text`` 全空白 → ``empty``：落了库但一个字都没有。

契约关闭集里还有 ``too_long``，那是**历史取值**：窗口只有 128K 的时代，超长候选
会被整栏丢弃。1M 窗口生效后本模块不再产出它——但保留在关闭集里，因为历史
``AgentSynthesis`` 快照按它落过库，``model_validate`` 回放时不能因为"现在的代码
不产出"就判定旧数据非法。

## 为什么分成两半

``build_aggregate_messages`` 是纯函数：不联网、不建库、不读 settings，prompt 装配
的全部规则（来源头 / 丢弃 / 截断）都能被单测逐条钉住。``synthesize`` 只负责"调
一次，失败换温度重来一次"，调用本身可注入（``call_model``），单测不碰真实网关。
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from apps.core.llm.exceptions import LLMError, LLMTimeoutError

from ..adjudication.contracts import DroppedCandidate, Synthesis, SynthesisCitation
from .citation_check import extract_case_refs, extract_statute_refs

logger = logging.getLogger(__name__)

#: **不再有单栏字数上限**（2026-11-22）。
#:
#: 曾经有 ``MAX_CANDIDATE_CHARS``（6000，截断并标注）与 ``HARD_CANDIDATE_CHARS``
#: （2.4 万，整栏丢弃）两档，前提是"1M 窗口不存在"。现在五栏全文一次进 prompt，
#: 截断带来的唯一后果是**聚合者读不到后文的论证**——它仍然会写出一段看似完整的
#: 结论，只是依据少了一半，且没有任何报错。这类静默降级比报错危险。
#:
#: 真正的闸门留在两处：``MAX_CANDIDATES``（栏数）与网关的上下文窗口（硬上限，
#: 超了会 400 而不是静默截断）。
#: 一次最多综合几栏。与多答运行时的 ``MAX_ANSWERS``（``services/chat/multi.py``）
#: 同值 5——**不 import 它**：那会把后端注册与 Django 模型拖进这个纯函数模块，
#: 让 prompt 装配的单测必须先起 Django。两处不同值会让「选满 5 栏」时的综合
#: 静默只取前 4 栏（用户看不出少了一栏）。
MAX_CANDIDATES = 5
#: 合成正文的 token 预算（**输出**上限，不是 prompt 预算）。
#:
#: 2026-11-22 从 8192 抬到 32768，与 ``pi/model_config.DEFAULT_MAX_TOKENS`` 同口径：
#:
#: 1. 不再限制正文字数（见 :data:`AGGREGATE_SYSTEM_PROMPT` 规则 4），结论该多长就多长；
#: 2. 推理模型的思考与正文**共用**这份预算——实测 kimi-2.6 在 6144 上限下吃到
#:    5958（96.9%），8192 时一次综合用掉 5723（正文仅 2042 字）。放开字数后，
#:    8192 会立刻变成"每次都顶满 → 判定没写完 → 重试一次 → 整条失败"。
#:
#: 上限只是闸门，不是开销：按实际 token 计费，模型不写就不花钱；它同时是截断
#: 闸门的阈值（顶到它 = 没写完，不许当结论）。
SYNTHESIS_MAX_TOKENS = 32768
#: 单次调用的硬超时（秒）。合成要输出上千字，比 judge 的 60s 宽一倍。
SYNTHESIS_TIMEOUT_SECONDS = 120.0
#: 总尝试次数（含首次）。**没有 ``while True``**：协议不稳定时的无限重试
#: 只会把"模型抽风"变成"账单失控"。
SYNTHESIS_MAX_ATTEMPTS = 2
#: 首次调用的温度：合成要稳，不要花。
SYNTHESIS_TEMPERATURE = 0.3
#: 重试时的温度：第一次拿不到正文通常是踩了某种退化循环，同一参数再问一遍
#: 大概率同样失败，换个温度才有信息量。
SYNTHESIS_RETRY_TEMPERATURE = 0.7
#: 退避（秒）：基数 / 上限 / 抖动，口径同 ``review/judge_client``。
SYNTHESIS_BACKOFF_BASE = 0.5
SYNTHESIS_BACKOFF_CAP = 4.0
SYNTHESIS_BACKOFF_JITTER = 0.3

#: 模型没在 metadata 里留下模型名时，来源头写这个——**不猜**（猜出来的是假来源）。
UNKNOWN_MODEL_LABEL = "未标注模型"

#: 正文必须出现的来源锚点前缀（system prompt 规则 1 要求每条实质结论都带它）。
#:
#: 它同时是**唯一的合规信号**：真跑出来的教训——推理型模型（kimi-2.6）会把
#: 「我们需要回答用户问题……需要综合三份候选……」这类**思考过程当成正文吐出来**，
#: 而且把 2048 的输出预算全吃光，律师看到的是一段没写完的自我对话。这种文本
#: 里必然一个 ``[来源：`` 都没有，所以「缺锚点」是它的可靠指纹。
ANCHOR_MARKER = "[来源："

#: 重试时追加到 system 末尾的加强语（第一次已证明这条路径会退化）。
STRICT_RETRY_SUFFIX = (
    "\n\n再次强调：第一句话就是结论正文，直接输出最终 Markdown；"
    "不要输出思考过程、分析步骤、自我提问或任何复述本指令的内容；"
    "每条实质结论后必须标 [来源：栏名]。"
)

#: aggregator 的 system prompt（MoA 口径 + 本仓库的三条补充，见模块 docstring）。
AGGREGATE_SYSTEM_PROMPT = """你是一名资深中国律师，手上有多份 AI 对同一个法律问题给出的回答。你的任务是把它们综合成一份可以直接给律师用的回答。

对每一份回答都要批判性评估：其中的法律依据、结论、数字都可能过时或错误，不要因为"多数份都这么说"就当成事实，也不要简单复述其中最完整的那一份。

硬性要求：
1. 每一条实质结论后面都要标来源锚点，格式 [来源：栏名]；栏名取自候选开头的【栏名 · 模型】。多个候选都主张的写 [来源：栏名1、栏名2]。
2. 只使用候选里出现过的法条、案号与数字。候选没给的依据不许补；确实缺依据时在正文里写明"候选未给出依据"。
3. 候选结论互相矛盾时，采用法律依据更充分的那一份，并用一句话说明分歧在哪；分不出高下就如实并列两种意见，不要只挑一个当结论。
4. 输出中文 Markdown 正文。**长度由内容需要决定**：该展开的论证写透，不要为凑长度
   重复或堆砌；也不要因为想简短而丢掉候选里的关键依据。不要 ``` 代码围栏，
   不要"以下是综合结论"这类开场白，也不要复述本指令。"""

#: 用户消息：问题 + 候选（每份带来源头）。
_AGGREGATE_USER_TEMPLATE = "问题：\n{task}\n\n候选回答（共 {count} 份，每份以【栏名 · 模型】开头）：\n\n{candidates}"

#: 整段被 ``` 围栏包住时的匹配（模型爱给 Markdown 加围栏，前端会把围栏当代码块）。
_FENCE_RE = re.compile(r"\A\s*```[\w-]*[ \t]*\r?\n(?P<body>.*?)\r?\n?[ \t]*```\s*\Z", re.DOTALL)


@dataclass(frozen=True)
class Candidate:
    """一份进候选池的答案。

    ``text=None`` 表示**该栏本轮没有正文可用**（跑了但失败 / 没落库），与
    ``text=""``（落了库但是空的）是两件事：前者是"没跑成"，后者是"跑了没说话"，
    交给律师的 ``dropped[].reason`` 因此也不同（``failed`` / ``empty``）。
    """

    lane: str
    model: str
    text: str | None


@dataclass(frozen=True)
class SynthesisReply:
    """一次成功的合成调用（正文 + 成本）。"""

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


#: 可注入的合成调用：``(messages, model, temperature) -> SynthesisReply``。
#: 生产路径是 ``_llm_aggregate``；单测注入假实现，失败路径不依赖真实网关。
CallModel = Callable[[list[dict[str, str]], str, float], Awaitable[SynthesisReply]]


def _source_header(candidate: Candidate) -> str:
    """候选的来源头：``【栏名 · 模型】``（模型缺失时写"未标注模型"，不猜）。"""
    model = (candidate.model or "").strip() or UNKNOWN_MODEL_LABEL
    return f"【{candidate.lane} · {model}】"


def partition_candidates(candidates: Sequence[Candidate]) -> tuple[list[Candidate], list[DroppedCandidate]]:
    """把候选池拆成"进 prompt 的"与"被丢弃的（带原因）"，保持请求顺序。

    Returns:
        ``(used, dropped)``：``used`` 的顺序 = 请求顺序；``dropped`` 的 ``reason``
        取值见 :data:`apps.agent.services.adjudication.contracts.DROPPED_REASONS`。

    Raises:
        ValueError: 候选数超过 :data:`MAX_CANDIDATES`。**不静默截断**——少一栏
            会让律师以为那份观点压根没参与，而 ``dropped`` 的封闭集里没有
            "数量超限"这一项，编一个出来等于改契约。
    """
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError(f"一次最多综合 {MAX_CANDIDATES} 栏，收到 {len(candidates)} 栏")

    used: list[Candidate] = []
    dropped: list[DroppedCandidate] = []
    for candidate in candidates:
        if candidate.text is None:
            dropped.append(DroppedCandidate(lane=candidate.lane, reason="failed"))
        elif not candidate.text.strip():
            dropped.append(DroppedCandidate(lane=candidate.lane, reason="empty"))
        else:
            # 不再按长度丢弃/截断：唯一的上限是模型上下文窗口本身（见模块 docstring）。
            used.append(candidate)
    return used, dropped


def render_candidate(index: int, candidate: Candidate) -> str:
    """渲染一份候选：``序号. 【栏名 · 模型】`` + **完整正文**（不截断）。

    ``index`` 是**进 prompt 之后的序号**（1 起），不用原始请求下标——中间夹着
    被丢弃的栏时，用请求下标会出现 "1. 3. 4." 这种断号，聚合者会以为漏读了。
    """
    text = (candidate.text or "").strip()
    header = f"{index}. {_source_header(candidate)}"
    return f"{header}\n{text}"


def build_aggregate_messages(task: str, candidates: Sequence[Candidate]) -> list[dict[str, str]]:
    """装配 aggregator 的 ``messages``（纯函数：同样的输入永远同样的输出）。

    空 / 失败候选**不进 prompt**（它们的去向见 :func:`partition_candidates`）；
    一份可用候选都没有时抛 ``ValueError``——让调用方先决定"没有可综合的东西"
    该怎么呈现，而不是拿一段空 prompt 去问模型（那只会换来一段幻觉）。

    Raises:
        ValueError: 没有任何可用候选，或候选数超过 :data:`MAX_CANDIDATES`。
    """
    used, _dropped = partition_candidates(candidates)
    if not used:
        raise ValueError("没有可综合的候选：全部为空或失败")

    blocks = "\n\n".join(render_candidate(index, candidate) for index, candidate in enumerate(used, start=1))
    return [
        {"role": "system", "content": AGGREGATE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _AGGREGATE_USER_TEMPLATE.format(task=task.strip(), count=len(used), candidates=blocks),
        },
    ]


def strip_code_fences(text: str) -> str:
    """去掉模型误加的 Markdown 代码围栏（整段被 ``` 包住时），并去首尾空白。"""
    raw = text or ""
    match = _FENCE_RE.match(raw)
    if match is None:
        return raw.strip()
    return match.group("body").strip()


def validate_reply(text: str, completion_tokens: int, *, max_tokens: int = SYNTHESIS_MAX_TOKENS) -> str:
    """正文是否可用；可用返回空串，否则返回封闭原因（``truncated`` / ``no_anchor``）。

    两道闸门都来自真机缺陷（不是假想）：

    - ``truncated``：``completion_tokens`` 顶到输出上限 = **没写完**，不是"干净结果"。
      真跑时 2048 全被思考过程吃掉，正文停在半句上；这种文本绝不能当结论展示。
    - ``no_anchor``：提示词要求每条实质结论带 ``[来源：栏名]``，一段合规正文不可能
      一个都没有——缺它就是"模型没在写结论"（思考过程 / 拒答 / 复述指令）。
      把无锚点文本当结论，等于让律师看一段无法回溯到任何一栏的话。
    """
    if completion_tokens >= max_tokens:
        return "truncated"
    if ANCHOR_MARKER not in text:
        return "no_anchor"
    return ""


def extract_citations(used: Sequence[Candidate]) -> list[SynthesisCitation]:
    """从各栏原文抽法条 / 案号做**来源锚点**（只标出处，不做核验）。

    按 ``(栏, 引用原文)`` 去重、保持出现顺序；同一句引用出现在两栏里会得到两条
    ——那正是"两栏都提到了这条法条"的证据，合并掉就看不出来了。
    """
    citations: list[SynthesisCitation] = []
    seen: set[tuple[str, str]] = set()
    for candidate in used:
        text = candidate.text or ""
        # 法条在前、案号在后（同 ``citation_check.verify_references`` 的清单顺序）。
        raws = [ref.raw for ref in extract_statute_refs(text)] + [ref.raw for ref in extract_case_refs(text)]
        for raw in raws:
            quote = raw.strip()
            key = (candidate.lane, quote)
            if not quote or key in seen:
                continue
            seen.add(key)
            citations.append(SynthesisCitation(lane=candidate.lane, quote=quote))
    return citations


#: 三种"拿到了但不可用"的对外文案（律师看到的是这一类，不是模型原文）。
_UNUSABLE_MESSAGES: dict[str, str] = {
    "empty": "综合结论为空",
    "truncated": f"综合结论在 {SYNTHESIS_MAX_TOKENS} token 输出上限处被截断，未写完",
    "no_anchor": "综合结论缺少来源锚点（疑似输出的是思考过程而非结论）",
}


def _with_strict_retry(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """重试时在 system 末尾追加加强语（幂等：已经加过就不再加）。"""
    if not messages or messages[0].get("role") != "system":
        return messages
    content = messages[0].get("content", "")
    if STRICT_RETRY_SUFFIX in content:
        return messages
    return [{**messages[0], "content": content + STRICT_RETRY_SUFFIX}, *messages[1:]]


def _backoff_seconds(attempt: int) -> float:
    """第 ``attempt`` 次失败后的等待时间（0 起，含抖动）。"""
    base = min(SYNTHESIS_BACKOFF_BASE * (2**attempt), SYNTHESIS_BACKOFF_CAP)
    return float(base + random.uniform(0, SYNTHESIS_BACKOFF_JITTER))


async def _llm_aggregate(messages: list[dict[str, str]], model: str, temperature: float) -> SynthesisReply:
    """走统一 LLM 门面调一次聚合（生产实现）。

    与 ``review/judge_client._llm_judge`` 同一套门面与坑：**不能**用同步的
    ``get_llm_service()``——它在 async 上下文里首次读配置会走同步 ORM，抛
    ``SynchronousOnlyOperation``，并被 fallback 策略吞成"后端不可用"（见
    ``docs/harness/backend/agent-runtime.md`` 的 SyncToAsync 坑）。这里用官方异步
    工厂 ``LLMService.create()``；合成是"律师点一次"的端点（一次调用），不像评审
    那样 N×M 次，所以不做进程级缓存。
    """
    from apps.core.llm.service import LLMService

    service = await LLMService.create()
    response = await service.achat(
        messages=list(messages),
        model=model,
        temperature=temperature,
        max_tokens=SYNTHESIS_MAX_TOKENS,
        # 后端用这个 kwarg 建 HTTP 客户端；不给就退回 provider 默认值。
        timeout_seconds=SYNTHESIS_TIMEOUT_SECONDS,
        caller="agent.synthesis",
    )
    return SynthesisReply(
        content=str(getattr(response, "content", "") or ""),
        model=str(getattr(response, "model", "") or model),
        prompt_tokens=int(getattr(response, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(response, "completion_tokens", 0) or 0),
        total_tokens=int(getattr(response, "total_tokens", 0) or 0),
    )


async def call_once(
    *,
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    call_model: CallModel | None = None,
) -> SynthesisReply:
    """调一次模型（不重试）；超时闸门对注入实现同样生效。"""
    call = call_model or _llm_aggregate
    try:
        return await asyncio.wait_for(call(messages, model, temperature), timeout=SYNTHESIS_TIMEOUT_SECONDS)
    except TimeoutError as error:
        # 统一成 LLMTimeoutError：裸 TimeoutError 在异常处理器里没有对应分支，
        # 会变成 500（"我们写错了"），而超时是上游慢（504，可重试）。
        raise LLMTimeoutError(timeout_seconds=SYNTHESIS_TIMEOUT_SECONDS) from error


async def synthesize(
    task: str,
    candidates: Sequence[Candidate],
    *,
    model: str,
    call_model: CallModel | None = None,
) -> Synthesis:
    """把多份候选综合成一份正文（一次调用；失败换温度再试一次）。

    ``session_id`` / ``turn`` 留空（``""`` / ``0``）：本函数与"哪一轮"无关，
    落库前由调用方 ``model_copy(update={...})`` 补齐——保持纯函数可单测，
    也避免把 Django 拖进这里。

    Raises:
        ValueError: 候选数超上限（见 :func:`partition_candidates`）。
        LLMError: 两次尝试都没拿到正文（含超时）。
    """
    used, dropped = partition_candidates(candidates)
    citations = extract_citations(used)
    synthesis_id = uuid.uuid4().hex

    if not used:
        # 一份可用候选都没有：不调模型（省一次无意义的钱），正文留空 + 交全部原因。
        return Synthesis(
            synthesis_id=synthesis_id,
            session_id="",
            turn=0,
            text="",
            model=model,
            lanes_used=[],
            dropped=dropped,
            citations=[],
            unverified=[],
            tokens={},
        )

    messages = build_aggregate_messages(task, used)
    last_error: BaseException | None = None
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    for attempt in range(SYNTHESIS_MAX_ATTEMPTS):
        temperature = SYNTHESIS_TEMPERATURE if attempt == 0 else SYNTHESIS_RETRY_TEMPERATURE
        try:
            reply = await call_once(messages=messages, model=model, temperature=temperature, call_model=call_model)
        except asyncio.CancelledError:
            raise
        except (LLMError, OSError, ValueError, RuntimeError) as error:
            # 只吞"这次调用没结果"的四类（网关 / 网络 / 超时 / 注入实现自报不可用）。
            # 其它异常（TypeError / AttributeError / KeyError）故意不接：多是我们
            # 自己写错，宽 except 基类会把 bug 变成"综合总是失败"。
            last_error = error
        else:
            prompt_tokens += reply.prompt_tokens
            completion_tokens += reply.completion_tokens
            total_tokens += reply.total_tokens
            used_model = reply.model or model
            text = strip_code_fences(reply.content)
            reason = validate_reply(text, reply.completion_tokens) if text else "empty"
            if not reason:
                return Synthesis(
                    synthesis_id=synthesis_id,
                    session_id="",
                    turn=0,
                    text=text,
                    model=used_model,
                    lanes_used=[candidate.lane for candidate in used],
                    dropped=dropped,
                    citations=citations,
                    unverified=[],
                    tokens={"prompt": prompt_tokens, "completion": completion_tokens, "total": total_tokens},
                )
            # 空正文 / 被输出上限截断 / 缺来源锚点：都算"这次没拿到可用结论"，
            # 换温度重来一次，并把"只输出最终正文"的加强语补进 system。
            last_error = LLMError(_UNUSABLE_MESSAGES[reason])
            logger.warning(
                "综合结论未通过校验（第 %s 次）：%s，completion=%s / max=%s",
                attempt + 1,
                reason,
                reply.completion_tokens,
                SYNTHESIS_MAX_TOKENS,
            )
            messages = _with_strict_retry(messages)

        if attempt + 1 < SYNTHESIS_MAX_ATTEMPTS:
            await asyncio.sleep(_backoff_seconds(attempt))

    if last_error is not None:
        raise last_error
    raise LLMError("综合结论：两次尝试都没有拿到正文")


__all__ = [
    "AGGREGATE_SYSTEM_PROMPT",
    "ANCHOR_MARKER",
    "STRICT_RETRY_SUFFIX",
    "MAX_CANDIDATES",
    "SYNTHESIS_MAX_ATTEMPTS",
    "SYNTHESIS_MAX_TOKENS",
    "SYNTHESIS_RETRY_TEMPERATURE",
    "SYNTHESIS_TEMPERATURE",
    "SYNTHESIS_TIMEOUT_SECONDS",
    "UNKNOWN_MODEL_LABEL",
    "CallModel",
    "Candidate",
    "SynthesisReply",
    "build_aggregate_messages",
    "call_once",
    "extract_citations",
    "partition_candidates",
    "render_candidate",
    "strip_code_fences",
    "synthesize",
    "validate_reply",
]
