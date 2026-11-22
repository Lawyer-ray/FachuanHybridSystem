"""综合结论的候选装配 —— MoA aggregator 那一步的**纯函数**部分。

综合本身由 agent 运行时执行（``services/synthesis/agent_runner``）；本模块只提供
与运行时无关、可逐条单测的规则：system prompt、候选来源头、丢弃口径、引用锚点。

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
3. **不截断**。候选全文原样进 prompt（模型声明 1M 上下文，见
   ``pi/model_config.DEFAULT_CONTEXT_WINDOW``）；截断只会让聚合者看不到后文的论证，
   却仍写出一段看似完整的结论——那是**静默的质量损失**。

## 两种"没进 prompt"的表示

- ``Candidate.text is None`` → ``failed``：该栏本轮没落库正文（跑了但失败 / 崩了）；
- ``Candidate.text`` 全空白 → ``empty``：落了库但一个字都没有。

契约关闭集里还有 ``too_long``，那是**历史取值**（早期按长度整栏丢弃）。本模块不再
产出它，但保留在关闭集里：历史 ``AgentSynthesis`` 快照按它落过库，``model_validate``
回放时不能判旧数据非法。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..adjudication.contracts import DroppedCandidate, SynthesisCitation
from .citation_check import extract_case_refs, extract_statute_refs

#: 一次最多综合几栏。与多答运行时的 ``MAX_ANSWERS``（``services/chat/multi.py``）
#: 同值——**不 import 它**：那会把后端注册与 Django 模型拖进这个纯函数模块，
#: 让单测必须先起 Django。两处不同值会让「选满」时的综合静默少取一栏。
MAX_CANDIDATES = 5

#: 模型没在 metadata 里留下模型名时，来源头写这个——**不猜**（猜出来的是假来源）。
UNKNOWN_MODEL_LABEL = "未标注模型"

#: 正文必须出现的来源锚点前缀（system prompt 规则 1 要求每条实质结论都带它）。
#:
#: 它同时是**唯一的合规信号**：推理型模型（实测 kimi-2.6）会把「我们需要回答用户
#: 问题……」这类**思考过程当成正文吐出来**，这种文本里必然一个 ``[来源：`` 都没有，
#: 所以「缺锚点」是它的可靠指纹（校验见 ``services/synthesis/agent_runner.validate_synthesis_text``）。
ANCHOR_MARKER = "[来源："

#: 综合 agent 的 system prompt（MoA aggregator 口径 + 本仓库的三条补充，见模块 docstring）。
AGGREGATE_SYSTEM_PROMPT = """你是一名资深中国律师，手上有多份 AI 对同一个法律问题给出的回答。你的任务是把它们综合成一份可以直接给律师用的回答。

对每一份回答都要批判性评估：其中的法律依据、结论、数字都可能过时或错误，不要因为"多数份都这么说"就当成事实，也不要简单复述其中最完整的那一份。

硬性要求：
1. 每一条实质结论后面都要标来源锚点，格式 [来源：栏名]；栏名取自候选开头的【栏名 · 模型】。多个候选都主张的写 [来源：栏名1、栏名2]。
2. 只使用候选里出现过的法条、案号与数字。候选没给的依据不许补；确实缺依据时在正文里写明"候选未给出依据"。
3. 候选结论互相矛盾时，采用法律依据更充分的那一份，并用一句话说明分歧在哪；分不出高下就如实并列两种意见，不要只挑一个当结论。
4. 输出中文 Markdown 正文。**长度由内容需要决定**：该展开的论证写透，不要为凑长度
   重复或堆砌；也不要因为想简短而丢掉候选里的关键依据。不要 ``` 代码围栏，
   不要"以下是综合结论"这类开场白，也不要复述本指令。"""


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


__all__ = [
    "AGGREGATE_SYSTEM_PROMPT",
    "ANCHOR_MARKER",
    "MAX_CANDIDATES",
    "UNKNOWN_MODEL_LABEL",
    "Candidate",
    "extract_citations",
    "partition_candidates",
    "render_candidate",
]
