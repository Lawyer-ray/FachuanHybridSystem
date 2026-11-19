"""SSE 事件契约类型（P1-12）——pydantic 定义 → 前端 TS 同源的单一来源。

用法：
    python -m apps.agent.sse_types --ts > frontend/src/features/copilot/sse-events.ts

前端 import type { AgentStreamEvent } from './sse-events' 替代手写 types.ts
中的同名类型（后续批次切换 import 路径即可）。

**生成器不再是手写模板**。原先 ``generate_ts()`` 是一段手抄的 TS 字符串，于是
契约实际上有三个源：pydantic 模型、这段模板、以及真正发事件的运行时
（``stream.py`` / ``multi.py`` / ``*_backend.py``）。三者各自漂移，而生成物永远
"看起来是对的"——重生成只是把模板抄一遍。现在 TS 由 ``model_fields`` 反射生成：
字段名与可选性只有一个来源，模板写法上的偏差在结构上不再可能。

**运行时仍可能多发字段**（例如编排层给每条已声明事件的帧补 ``agent``）。所以纯
反射还不够，另有一条 ``test_sse_contract_same_source.py`` 断言「生成物与仓库里的
``sse-events.ts`` 逐字节一致」并且「每个事件类都声明了 ``agent``」——两条一起才
能同时挡住模板漂移和运行时漂移。
"""

from __future__ import annotations

import sys
import types
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, Field

#: ``done.finish_reason`` 与 ``AgentMessage.metadata["finish_reason"]`` **共用**。
#:
#: 一份枚举、两种载体：SSE 上的 ``done`` 只可能取到 ``ok`` / ``degraded`` /
#: ``error``；``cancelled`` 只出现在落库 metadata 里——客户端断开时生成器已被
#: 关闭，根本没有通道发 ``done``。可达性事实写在 :data:`WIRE_UNREACHABLE`，
#: 由同源测试锁死，避免前后端各猜一套枚举（历史上两端各写一套，前端等
#: ``error`` 而后端永远发 ``ok``）。
FinishReason = Literal["ok", "degraded", "error", "cancelled"]

#: SSE 上**不可达**的 ``finish_reason``：只在落库 metadata 里出现。
WIRE_UNREACHABLE: frozenset[str] = frozenset({"cancelled"})


class _RunScoped(BaseModel):
    """「属于某次运行」的公共信封。

    三个后端对每一帧都在补这两个键（``pi_backend.py`` / ``dsh_backend.py`` /
    ``openai_agents_backend.py`` 都在转发处 ``{**event, "agent": kind, "run_id": ...}``），
    契约只是把它显式化——**不是新增行为**，是把运行时既成事实写进类型。

    不声明它的代价是真实的：前端只能靠属性探测绕过联合类型
    （``domain/dual.ts`` 的 ``agentOf``），而「这帧是谁发的」在多栏并答时是
    分流到哪一栏的唯一依据；一个没进类型的字段随时可能被当成冗余删掉。
    """

    #: 二级寻址键：``{session_id}:{agent_kind}:{turn}``。空串 = 旧数据 / 编排层代发。
    run_id: str = ""
    #: 产这帧的后端 kind（``pi`` / ``dsh`` / …）。空串 = 旧数据 / 未标注。
    agent: str = ""


class MetaEvent(_RunScoped):
    """会话元信息（流开始时一次）"""

    type: Literal["meta"]
    session_id: str
    #: 本轮参与的栏（多答时 2~4 个）。单栏为空 → 前端按 `agent` 单值处理。
    agents: list[str] = []


class ActivityEvent(_RunScoped):
    """活动状态（queued / thinking / degraded）"""

    type: Literal["activity"]
    status: str
    #: 本轮参与的栏（``status="queued"`` 时前端据此预置占位栏）
    agents: list[str] = []
    position: int | None = None
    #: 仅 ``status="degraded"``：降级原因（多答只跑了主后端时，律师需要知道
    #: 「另外两栏没跑」而不是看到两个空白栏头）。空串 = 正常路径。
    reason: str = ""


class DeltaEvent(_RunScoped):
    """正文增量"""

    type: Literal["delta"]
    content: str


class ThinkingEvent(_RunScoped):
    """思考增量（不计入正文）"""

    type: Literal["thinking"]
    content: str


class ToolCallEvent(_RunScoped):
    """工具调用开始"""

    type: Literal["tool_call"]
    tool_call_id: str
    name: str
    #: 调用参数。**三种形状都真的出现过**：pi 的 ``input`` 是对象、dsh/openai 是
    #: JSON 字符串、工具无参时是 None。所以只能 ``Any``——写成 ``str`` 会逼前端
    #: 对对象做 ``JSON.parse``，写成 ``dict`` 会在字符串上直接抛。
    arguments: Any = None


class ToolResultEvent(_RunScoped):
    """工具调用结果"""

    type: Literal["tool_result"]
    tool_call_id: str
    name: str
    result: str | None = None
    is_error: bool = False


class ApprovalRequestEvent(_RunScoped):
    """审批请求（高危工具）"""

    type: Literal["approval_request"]
    approval_id: str
    tool_name: str
    tool_args: dict[str, object] = Field(default_factory=dict)
    message: str = ""
    risk_level: str = ""
    needs_second_confirmation: bool = False


class UsageEvent(_RunScoped):
    """token 用量（pi 精确计数）。

    ``cache_read_tokens`` / ``cache_write_tokens`` 是 2026-10-25 新增：
    法穿把「AGENTS.md 逐轮字节稳定 → 命中 provider prompt cache」当核心设计，
    但之前账上看不到它到底生效没（``input_tokens`` 只装未命中部分）。
    前端可用 ``cache_read/(input+cache_read+cache_write)`` 算命中率。

    两个 cache 字段带默认 0：旧版 pi / 某些 provider 不上报时不至于断流。
    """

    type: Literal["usage"]
    output_tokens: int
    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class QuestionRequestEvent(_RunScoped):
    """模型向律师提问（不是审批：超时不阻断，模型按假设继续）。"""

    type: Literal["question_request"]
    question_id: str
    questions: list[dict[str, Any]] = []
    timeout_seconds: int = 180


class CompactionEvent(_RunScoped):
    """上下文压缩进行中（pi 自动压缩或手动压缩触发）。

    ``phase="start"``：压缩开始（前端可显示「正在压缩上下文…」）；
    ``phase="end"``：压缩完成（历史已被摘要替代，前端提示「已压缩」）。
    """

    type: Literal["compaction"]
    phase: Literal["start", "end"]


class ErrorEvent(_RunScoped):
    """流内错误（已翻译成人话）"""

    type: Literal["error"]
    message: str


class UnknownEvent(_RunScoped):
    """后端透传的未识别上游事件（当前仅 dsh 产出）。

    存在的理由：dsh 的 SDK 事件名会随版本变，作者刻意「不静默吞」以便排查。
    声明它 = 让前端能**类型安全地忽略**，而不是让一个未声明的 ``type`` 悄悄
    穿过 ``parseSseEvent``（那里只做类型断言，不做校验）。前端已有
    ``default: break`` 会忽略它 → 零前端改动。
    """

    type: Literal["unknown"]
    raw: dict[str, Any] = Field(default_factory=dict)


class DoneEvent(_RunScoped):
    """流结束（**每栏各一条**）。

    ``context_*`` 两个字段（2026-10-25 新增）来自 pi 的 ``get_session_stats``
    （本轮结束后、进程关闭前取一次）：律师需要看到会话上下文水位，
    否则自动压缩「无声发生」、模型突然失忆却没有任何解释。
    拿不到（旧数据 / pi 异常）时为 ``None``，前端隐藏水位显示即可。

    为什么 ``context_*`` 必须**每栏都带**：多答时前端按栏写水位，只给主栏带
    会让另外几栏停在上一轮的旧值——那比不显示更糟（显示的是错的数）。
    """

    type: Literal["done"]
    session_id: str
    #: 本轮参与的栏（多答时多值）
    agents: list[str] = []
    #: 本轮落库的助手消息主键；``None`` = 未拿到（取消 / 落库失败）。
    #: 前端据此把实时气泡与可评分/可续写的落库行对上——没有它就只能在
    #: 刷新后才点得动「评分」「继续生成」。
    message_id: int | None = None
    #: 本轮怎么结束的。只有 :data:`WIRE_UNREACHABLE` 之外的值会出现在这里。
    finish_reason: FinishReason = "ok"
    context_used_tokens: int | None = None
    context_total_tokens: int | None = None


AgentStreamEvent = (
    MetaEvent
    | ActivityEvent
    | DeltaEvent
    | ThinkingEvent
    | ToolCallEvent
    | ToolResultEvent
    | ApprovalRequestEvent
    | UsageEvent
    | QuestionRequestEvent
    | CompactionEvent
    | ErrorEvent
    | UnknownEvent
    | DoneEvent
)

#: 生成 TS 联合类型的顺序（也是 JSON Schema 导出的顺序）。
#: 新增事件必须同时登记，否则它不在联合类型里、前端一律当未知事件丢掉。
EVENT_MODELS: list[type[BaseModel]] = [
    MetaEvent,
    ActivityEvent,
    DeltaEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
    ApprovalRequestEvent,
    UsageEvent,
    QuestionRequestEvent,
    CompactionEvent,
    ErrorEvent,
    UnknownEvent,
    DoneEvent,
]


# ── TS 生成（反射，不是模板）────────────────────────────────────────────


def _ts_literal(values: tuple[object, ...]) -> str:
    parts = []
    for value in values:
        parts.append(f"'{value}'" if isinstance(value, str) else str(value).lower())
    return " | ".join(parts)


def _ts_type(annotation: Any) -> str:
    """把一个 Python 注解映射成 TS 类型；未知一律 ``unknown``（宁可松，不可错）。"""
    if annotation is type(None):
        return "null"
    if annotation is str:
        return "string"
    if annotation is bool:
        return "boolean"
    if annotation in (int, float):
        return "number"
    origin = get_origin(annotation)
    if origin is Literal:
        return _ts_literal(get_args(annotation))
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        rendered = " | ".join(_ts_type(a) for a in args)
        return f"{rendered} | null" if len(args) != len(get_args(annotation)) else rendered
    if origin in (list, set, tuple):
        args = get_args(annotation)
        inner = _ts_type(args[0]) if args else "unknown"
        # 联合类型做元素要加括号，否则 `a | b[]` 的优先级是错的
        return f"({inner})[]" if " | " in inner else f"{inner}[]"
    if origin is dict:
        return "Record<string, unknown>"
    return "unknown"


def _is_optional(model: type[BaseModel], name: str) -> bool:
    """字段在 TS 里是否可省：有默认值、或注解里含 ``None``。

    ``type`` 永远必填（判别式），其余按 pydantic 的默认值判定——这样「后端能不发
    这个键」与「前端可以不给这个键」是同一个事实，不会出现 TS 要求必填而线上
    旧数据缺字段的裂缝。
    """
    field = model.model_fields[name]
    if name == "type":
        return False
    if field.is_required():
        return False
    return True


def _ts_model(model: type[BaseModel]) -> str:
    """单个事件模型 → 一段 TS 对象类型。

    ``type`` 排第一（它是判别式，读代码时先看到才知道这是哪种帧），其余按
    ``model_fields`` 的声明序——声明序就是文档顺序，前端读生成的 TS 时上下文一致。
    """
    names = list(model.model_fields)
    if "type" in names:
        names.remove("type")
        names.insert(0, "type")
    lines: list[str] = []
    for name in names:
        optional = _is_optional(model, name)
        rendered = _ts_type(model.model_fields[name].annotation)
        if optional and rendered.endswith(" | null"):
            rendered = rendered[: -len(" | null")]
        lines.append(f"    {name}{'?' if optional else ''}: {rendered}")
    body = "\n".join(lines)
    return "{\n" + body + "\n  }"


def generate_ts() -> str:
    """生成 TypeScript 类型定义文件内容（从 ``model_fields`` 反射）。"""
    members = "\n  | ".join(_ts_model(model) for model in EVENT_MODELS)
    return (
        "/**\n"
        " * SSE 流事件类型（自动生成——python -m apps.agent.sse_types --ts）\n"
        " * 后端单一来源：apps/agent/sse_types.py；修改须同步重新生成。\n"
        " *\n"
        " * 生成器是**反射**而不是手写模板：字段名与可选性只有 pydantic 一个来源。\n"
        " * 改契约请改 pydantic 模型再重跑上面那条命令，不要手改本文件\n"
        " * （CI 的 test_sse_contract_same_source.py 会逐字节比对）。\n"
        " */\n\n"
        "export type AgentStreamEvent =\n"
        f"  | {members}\n"
    )


if __name__ == "__main__":
    if "--ts" in sys.argv:
        sys.stdout.write(generate_ts())
    else:
        # JSON Schema 导出（供 jsonschema 校验）
        import json

        for model in EVENT_MODELS:
            sys.stdout.write(json.dumps(model.model_json_schema(), indent=2) + "\n")
