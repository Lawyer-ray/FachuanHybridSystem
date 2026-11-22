"""网关协议层：网关认哪些字段 / 哪些档位 / 哪些模型能思考的唯一来源。

## 为什么需要这一层（5 处重复 → 1 处）

「网关认哪些字段、认哪些档位、认哪些模型能思考」这三件事，此前被各自复制在 5 个地方：

1. ``core/models/llm_provider._THINKING_CAPABLE_MARKERS`` —— **Agent 通道**用它（宽匹配）；
2. ``core/llm/backends/openai_compatible._DISABLE_THINKING_MODELS`` —— **服务通道**用它（窄匹配）；
3. ``agent/pi/model_config._GATEWAY_EFFORT_MAP`` —— pi 侧私有的档位映射；
4. ``agent/backends/dsh_config`` 自写的档位 tuple —— 语义与 3 不同；
5. ``openai_compatible`` 与 ``pi/model_config`` 各一份的降级候选解析。

## 分叉的真实后果（这就是本层存在的理由）

``kimi-k2`` 这类模型名：表 1 命中 ``"kimi"`` → Agent 通道判为可思考，下发
``thinking=true`` + ``reasoning_effort=max``；表 2 不命中 ``"kimi26"`` → 服务通道
**一个字段都不发** → 不思考。同一平台、同一模型、同一个 ``enable_thinking`` 开关，
copilot 里深度推理，诉状生成/合同审查里不推理，**且没有任何报错**。

另外服务通道即便命中表 2，也只发开关不发 ``reasoning_effort``，而「只发开关等于
永远停在默认深度」（见 ``pi/model_config`` 的实测记录）。

本模块把这三件事收敛成单一权威，并保持为**纯函数模块**：只做瞬时计算，不做任何
IO / DB / Django settings 读取 / 日志，因此可以被任何一层安全复用。

## 纯度约束（硬）

只允许 import 标准库与 :mod:`apps.core.llm.exceptions`。**禁止 import 任何 models
模块**——``core/models/llm_provider.py`` 会反向引用本模块（``supports_thinking``
委托 :func:`model_supports_thinking`），引入 models 即成环。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .exceptions import LLMAPIError, LLMNetworkError, LLMTimeoutError

__all__ = [
    "DEFAULT_THINKING_LEVEL",
    "GATEWAY_EFFORTS",
    "RETRYABLE_EXCEPTIONS",
    "ThinkingDirectives",
    "fallback_chain",
    "gateway_effort",
    "is_retryable",
    "model_supports_thinking",
    "normalize_model_key",
    "resolve_thinking",
    "selectable_efforts",
    "wire_fields",
]

# ── 1. 模型思考能力 ──────────────────────────────────────────────────

#: 支持 ``chat_template_kwargs.thinking`` 开关的推理模型名特征（小写子串匹配）。
#: 这些模型默认会「思考」，历史实现在请求里显式关闭以省延迟；配置项允许打开。
#:
#: ⚠️ ``"kimi"`` 是**宽匹配**（命中 ``kimi-k2`` / ``kimi-2.6`` / ``kimi26``），
#: 这正是本层要对齐的口径：服务通道原先只认 ``"kimi26"``，于是 ``kimi-k2``
#: 在两条通道上判出相反结论（见模块 docstring）。
_THINKING_CAPABLE_MARKERS: tuple[str, ...] = (
    "kimi",
    "mimo",
    "deepseekr1",  # 归一化后的 deepseek-r1 / deepseek_r1
    "deepseekreasoner",
    "qwq",
    "reasoner",
    "glmz",  # 归一化后的 glm-z
)

#: 归一化时要去掉的噪声字符：分隔符与括号后缀（``kimi-2.6(Anthropic)`` → ``kimi26anthropic``）。
_MODEL_KEY_NOISE_CHARS: tuple[str, ...] = ("-", "_", ".", " ", "(", ")", "/", ":")


def normalize_model_key(model: str) -> str:
    """小写 + 去掉 `-` `_` `.` 空格 `/` `:` 与括号，便于子串匹配。"""
    key = model.lower()
    for ch in _MODEL_KEY_NOISE_CHARS:
        key = key.replace(ch, "")
    return key


def model_supports_thinking(model: str | None) -> bool:
    """该模型是否属于「可开关思考模式」的推理模型（未知模型返回 False）。"""
    key = normalize_model_key(model or "")
    return any(marker in key for marker in _THINKING_CAPABLE_MARKERS)


# ── 2. 思考档位 ──────────────────────────────────────────────────────

#: 网关 `reasoning_effort` 真正接受的白名单（实测 2026-11，DeepSeek V4.1 走 vLLM 原话：
#: ``reasoning_effort must be low, high, xhigh, max, or an integer within [1, 100]``）。
GATEWAY_EFFORTS: tuple[str, ...] = ("low", "high", "xhigh", "max")

#: 平台开启思考时的默认档位。
#:
#: 取 ``max``：律师要的是「能想多深想多深」。这是**默认档位**，不是能力开关——
#: 是否真的思考仍由平台总开关 ``enable_thinking`` 与该模型是否推理模型决定。
#:
#: ⚠️ 档位取值受上游约束，不可照搬 pi 的七档全集。实测（2026-11，DeepSeek V4.1
#: 走 vLLM）服务端原话：
#:     ``reasoning_effort must be low, high, xhigh, max, or an integer within [1, 100]``
#: 也就是说 **``medium`` 会直接 400 失败**（曾经就是默认值，等于默认配置下
#: 「一开思考就报错」）。发往服务端前会经 :data:`_GATEWAY_EFFORT_MAP` 归一化。
DEFAULT_THINKING_LEVEL = "max"

#: pi 的思考等级 → 网关真正接受的 ``reasoning_effort``。
#:
#: 网关只认 ``low`` / ``high`` / ``xhigh`` / ``max``（及 1–100 整数），不认
#: ``minimal`` / ``medium``。这里把 pi 的七档收窄映射到服务端能吃的值：
#:
#: - ``medium`` 保留「不合法的事实」会炸，所以映射到 ``high``（最接近的中档）——
#:   原样下发会得到 400，整轮对话直接失败；
#: - ``minimal`` 服务端会静默降成 ``low``（实测回显已变 low），显式映射避免误导
#:   （「调了 minimal 以为更省，其实和 low 一模一样」）。
_GATEWAY_EFFORT_MAP: dict[str, str] = {
    "minimal": "low",
    "low": "low",
    "medium": "high",
    "high": "high",
    "xhigh": "xhigh",
    "max": "max",
}

#: 「关闭思考」在档位维度上的取值：各 harness 的档位枚举里都要有 ``off`` 这一档。
_OFF_EFFORT = "off"


def gateway_effort(level: str | None) -> str:
    """任意思考档位/等级 → 网关白名单内的 `reasoning_effort` 值（**永不返回白名单外的值**）。

    映射口径（保持现有两处实测结论）：

    - ``None`` / ``""``            → :data:`DEFAULT_THINKING_LEVEL`
    - ``"off"``                    → ``"low"``（关闭时不发 effort，见 :func:`wire_fields`）
    - ``"minimal"``                → ``"low"``（服务端会静默降成 low）
    - ``"medium"``                 → ``"high"``（**不能原样发**，服务端 400）
    - ``"low"/"high"/"xhigh"/"max"`` → 原样
    - 其他未知值                   → :data:`DEFAULT_THINKING_LEVEL`
    """
    cleaned = (level or "").strip().lower()
    if not cleaned:
        return DEFAULT_THINKING_LEVEL
    if cleaned == _OFF_EFFORT:
        # 关闭思考时 effort 不参与下发（见 wire_fields），这里只负责守住白名单。
        return "low"
    # 未知值不把它当合法 effort 传下去：fail-closed 到默认档
    return _GATEWAY_EFFORT_MAP.get(cleaned, DEFAULT_THINKING_LEVEL)


def selectable_efforts() -> tuple[str, ...]:
    """各 harness 配置里可枚举的档位：`("off",) + GATEWAY_EFFORTS`。"""
    return (_OFF_EFFORT, *GATEWAY_EFFORTS)


# ── 3. 中立指令 ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ThinkingDirectives:
    """一组与传输格式无关的思考指令。各 adapter 自己序列化成自己的配置格式。"""

    #: 该模型有没有这个开关
    supported: bool
    #: 这一轮要不要开
    enabled: bool
    #: 始终 ∈ :data:`GATEWAY_EFFORTS`
    effort: str


def resolve_thinking(
    model: str | None,
    *,
    enable_thinking: bool,
    level: str | None = None,
) -> ThinkingDirectives:
    """平台开关 + 模型能力 + 本轮档位 → 中立指令。

    生效语义（三档合一，唯一实现）：

    - ``enabled = supported and enable_thinking and level != "off"``
      —— 平台总开关与「本轮档位=off」是**与**关系，任一为否则不思考；开关打开但
      模型没有思考能力时，下发任何思考字段只会污染请求体；
    - ``effort = gateway_effort(level)``，``level is None`` 时取
      :data:`DEFAULT_THINKING_LEVEL`。``enabled=False`` 时 ``effort`` 仍必须是
      :data:`GATEWAY_EFFORTS` 内的值——``"off"`` 不在白名单里，不能拿来当占位。

    为什么要 ``level`` 入参：``pi``/``dsh`` 有会话级档位（``--thinking`` /
    ``thinkingLevelMap``），若 profile 只给出默认 ``max``，各 adapter 只能自己
    ``replace(effort=...)`` 再算一次映射——那又把档位知识散回 4 处。档位→白名单的
    映射必须只有这一处。

    ``"off"`` 的判定与 :func:`gateway_effort` 共用同一套归一化（去空白 + 小写），
    否则 ``"OFF"`` 会落到「按 off 映射 effort、却被判成开启」的自相矛盾状态。
    """
    supported = model_supports_thinking(model)
    thinking_off = (level or "").strip().lower() == _OFF_EFFORT
    return ThinkingDirectives(
        supported=supported,
        enabled=supported and enable_thinking and not thinking_off,
        effort=gateway_effort(level),
    )


def wire_fields(directives: ThinkingDirectives) -> dict[str, Any]:
    """中立指令 → 网关真正吃的请求字段。

    | supported | enabled | 返回 |
    |---|---|---|
    | False | * | `{}`（不下发任何开关：部分后端把未知 `chat_template_kwargs` 当 400） |
    | True | True | `{"chat_template_kwargs": {"thinking": True}, "reasoning_effort": effort}` |
    | True | False | `{"chat_template_kwargs": {"thinking": False}}`（**不带 effort**） |

    为什么关闭时必须显式发 `false`：实测省略开关 ≠ 关闭，省略后模型依旧按默认思考
    （``thinking=false`` → ``reasoning_tokens=0``；不下发开关 → 依旧思考）。

    两个参数是**互补**而非互斥：``thinking`` 管「要不要想」，``reasoning_effort``
    管「想多深」。只发前者等于永远停在默认深度，拖到 Max 也不生效。
    """
    if not directives.supported:
        return {}
    if not directives.enabled:
        return {"chat_template_kwargs": {"thinking": False}}
    return {"chat_template_kwargs": {"thinking": True}, "reasoning_effort": directives.effort}


# ── 4. 降级 ─────────────────────────────────────────────────────────

#: **粗筛**：这些类型的失败「可能」值得换模型重试。是否真该重试由 :func:`is_retryable` 判定。
#:
#: 为什么单靠这个 tuple 不够：``openai_compatible._raise_mapped_error`` 把**所有**
#: ``APIStatusError``（含 400）都映射成 :class:`LLMAPIError`，只把 HTTP 状态留在
#: ``status_code`` 字段里，于是 4xx 参数错与 5xx 服务端故障在**类型上无法区分**。
#: 拿这个 tuple 直接当 ``except`` 条件，等于「一次坏 prompt 把降级链上每个模型各打一遍」
#: （3 个 fallback = 4 倍计费，且结果必然一样是 400）。
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (LLMTimeoutError, LLMNetworkError, LLMAPIError)


def is_retryable(error: BaseException) -> bool:
    """这次失败该不该换模型重试（换模型能改变结果吗）。

    - :class:`LLMTimeoutError` / :class:`LLMNetworkError` → ``True``；
    - :class:`LLMAPIError` → 看 ``status_code``：**5xx / 无状态的兜底 → True**；
      ``400/422``（参数错：模型不认 ``reasoning_effort``、上下文超长、prompt 非法）、
      ``401/403``（鉴权）、``404``（模型不存在）→ **False**（换哪个模型都是同一个错）；
    - 其他异常 → ``False``

    修正的是一个真实浪费：旧实现把 400 也当可重试，一次坏 prompt 会把降级链上
    每个模型各打一遍（3 个 fallback = 4 倍计费，且结果必然一样是 400）。
    """
    if isinstance(error, (LLMTimeoutError, LLMNetworkError)):
        return True
    if isinstance(error, LLMAPIError):
        # ``status_code is None`` 是 ``_raise_mapped_error`` 最后那条兜底（非 HTTP 失败），
        # 无从归类，按可重试处理：换模型仍是合理的下一步。
        status_code = getattr(error, "status_code", None)
        return status_code is None or status_code >= 500
    return False


#: ``fallback_models`` 里允许混用的分隔符（逗号 / 分号 / 换行）。
_FALLBACK_SEPARATORS = re.compile(r"[,;\r\n]+")


def _split_fallback_names(raw_fallback: Sequence[str] | str | None) -> list[str]:
    """两种真实形态（DB 原串 / ``list[str]``）统一摊平成候选名（未去空去重）。

    ``list[str]`` 的**元素本身**也可能带分隔符与前后空格（Admin 填报历史数据），
    所以逐元素走同一套清洗规则，而不是只在字符串形态上 split。
    """
    if raw_fallback is None:
        return []
    chunks: Sequence[str] = (raw_fallback,) if isinstance(raw_fallback, str) else raw_fallback
    names: list[str] = []
    for chunk in chunks:
        names.extend(_FALLBACK_SEPARATORS.split(chunk or ""))
    return names


def fallback_chain(primary: str | None, raw_fallback: Sequence[str] | str | None) -> list[str]:
    """主模型 + Admin `fallback_models` → 去重后的降级链。

    ``raw_fallback`` 两种真实形态都要吃：服务通道给的是 ``list[str]``
    （``core/llm/backends/base.py`` 的 :attr:`OpenAIProviderConfig.fallback_models`），
    Agent 通道给的是 DB 原始字符串（``LLMProvider.fallback_models``，逗号/分号/换行混写）。

    ``primary`` 恒在首位（有值时），备选去空、去重、保持配置顺序；主模型重复出现在
    备选里只保留首位那一份（否则「降级到自己」空转，白烧一次请求）。
    ``primary`` 为空时返回仅含备选的列表——此时调用方本就没有主模型可退。
    """
    chain: list[str] = []
    seen: set[str] = set()
    for candidate in (primary or "", *_split_fallback_names(raw_fallback)):
        name = candidate.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        chain.append(name)
    return chain
