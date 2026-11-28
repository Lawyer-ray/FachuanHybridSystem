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

#: ``error.scope``：这错该由**谁**来修。
#:
#: 为什么不只给一个 code：律师看到「限流」时该做的是等 15 秒，看到「后端不可用」
#: 时该做的是找管理员——两者都能用 code 区分，但前端还要决定「这句话该不该带
#: 一个『联系管理员』按钮」。scope 就是这个粗粒度结论，它比 code 稳定得多
#: （新增 code 时不必回头改前端的分组逻辑）。
#:
#: - ``account``：律师/账号侧（限流、配额、凭证）——通常等一等或重新登录就能过；
#: - ``model``：后端或模型侧（不可用、上游超时）——律师改不了，要报给管理员；
#: - ``request``：这次请求本身（上下文超限、参数太多、会话不存在）——换问法/新开会话；
#: - ``tool``：工具调用参数（模型生成错了，先回给模型改）；
#: - ``unknown``：兜底（保持与引入 scope 之前的旧前端兼容）。
ErrorScope = Literal["account", "model", "request", "tool", "unknown"]


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


class QuestionOption(BaseModel):
    """一个可选项（字段与 ``question.normalize_questions`` 的产物逐字对应）。

    声明它而不是让 questions 继续写成 ``list[dict[str, Any]]``：后者在 OpenAPI/
    TS 里只有 ``Record<string, unknown>``，前端只能照着后端代码猜字段名——而
    「查 OpenAPI 才能写前端」是硬约定。字段名来自 ``normalize_questions`` 的
    实际产物，由 ``test_agent_question_spec_contract`` 逐字段比对（漂移会红）。
    """

    label: str
    #: 补充说明（模型可留空）；前端渲染成选项下的灰字。
    description: str = ""


class QuestionSpec(BaseModel):
    """一道待回答的问题。

    **不做运行时校验**：这是线路契约声明，不是入口校验器。真正的归一化在
    ``services/question.normalize_questions``（它要宽容解析模型的多种写法），
    在这里再套一层 pydantic 只会把「模型写法怪」变成「提问直接失败」。
    """

    #: 答案回填的对齐键（服务端生成，模型给的可能重复）
    id: str
    question: str
    #: 为什么问这个（模型给的上下文，可空）
    context: str = ""
    options: list[QuestionOption] = []
    #: 是否允许自由文本作答（默认允许：律师常常要补充选项外的情况）
    allow_freeform: bool = True
    #: 是否允许多选
    allow_multiple: bool = False
    #: 是否允许附加评论
    allow_comment: bool = False


class QuestionRequestEvent(_RunScoped):
    """模型向律师提问（不是审批：超时不阻断，模型按假设继续）。"""

    type: Literal["question_request"]
    question_id: str
    questions: list[QuestionSpec] = []
    timeout_seconds: int = 180


class UiActionEvent(_RunScoped):
    """前端动作下发帧（T1 单向通道）。

    **它不是工具结果**，也没有对应的 ``tool_result``：后端发完即返回
    ``observed: False``，执行结果不回传（理由见 ``services/ui_action`` 模块 docstring）。

    ``call_id`` / ``sequence`` 是前端的两条防线：前者做幂等（模型重试 / 事件重放命中
    LRU 直接跳过），后者让「跳号」可见（**只记 warning、不重排**——动作语义有先后，
    重排会把「先归案再跳页」变成「先跳页再归案」）。

    ``batch_id`` / ``batch_index`` 是**批量下发**（``ui_action_batch``）的帧身份：同一批的
    帧共享一个 id、序号从 0 递增。前端靠它串行执行、并在「停下」时把同批剩余步骤一起终止
    ——不让它自带身份，前端就只能按到达顺序猜，猜错一次就是两个批次互相阻塞。两个键
    **恒在**（单步动作是 ``None`` / ``0``），前端才只有一套读取逻辑。
    """

    type: Literal["ui_action"]
    call_id: str
    action: str
    arguments: dict[str, Any]
    #: 期望路由前缀（清单里的 ``route``）；``None`` = 任意页面
    route: str | None = None
    #: 同会话内递增的动作序号。进程内计数，跨 worker 不保证连续。
    sequence: int = 0
    #: 同一批次的 id（``ui_action_batch`` 生成）；``None`` = 单步动作。
    batch_id: str | None = None
    #: 该批次内的序号（0 起）；单步动作为 0。
    batch_index: int = 0


class UiSnapshotRequestEvent(_RunScoped):
    """页面状态快照请求（AI 想知道「现在页面上是什么」）。

    与 ``UiActionEvent`` 方向相反：那条是**让**页面动，这条是**问**页面。前端读完
    ``ui-tools/page-state.ts`` 注册的结构化状态后 POST ``/agent/ui-snapshots/{request_id}``
    回传；读不到就带 ``note`` 明说没声明（后端转成 ``no_page_state``，不许假装空对象）。

    **超时不是错误**：模型按「没问到」继续（同 ``ask_user`` 的 ``timed_out``），所以帧上
    带 ``timeout_seconds`` 让前端知道这次等待窗口有多长。
    """

    type: Literal["ui_snapshot_request"]
    request_id: str
    #: 期望读哪一页；``None`` = 前端取最近注册且已挂载的那个页面。
    page: str | None = None
    timeout_seconds: int = 3


class CitationRef(BaseModel):
    """一条**入站引用**（AI → 材料）——正文 `[K<cite_no>]` 角标指向的来源。

    字段名与 ``services/chat/citations.py`` 的投影产物逐字对应；**前端已按
    这批 snake_case 名消费**（TS 生成物里也是 ``cite_no``，由前端映射成
    ``citeNo``）。改名前先想清楚：它是历史回放的一部分，落库在
    ``AgentMessage.metadata["citations"]`` 里，旧数据不会跟着改名。

    ``cite_no`` 必须由**后端**分配（本轮检索命中的出现顺序，1 起单调递增），
    前端不得自己按出现顺序重编号——历史回放时正文与来源表的对应关系只能靠它。
    """

    #: 与正文 ``[K<cite_no>]`` 一一对应；本轮内从 1 开始（跨轮重新从 1 开始）。
    cite_no: int
    #: 来源种类（决定角标点开时显示哪套字段与跳转动作）。
    kind: Literal["case", "contract", "statute", "judgment", "file"]
    #: 业务主键（能跳转到案件/合同/文书详情时才有）。
    ref_id: int | None = None
    #: 显示名：案件名 / 合同名 / 法条名（《民法典》）/ 判决书标题 / 文件名。
    name: str
    #: 定位：页（**解析器分段页码**，不等于打印页；前端 ``pageSpanNote`` 措辞不同）。
    page: int | None = None
    #: 定位：条款号（法条「第 X 条」/ 判决书案号）。
    clause: str | None = None
    #: 定位：检索切片主键（精确回溯用；本仓库当前检索工具都不返回，留作扩展位）。
    chunk_id: int | None = None
    #: 原文片段（角标点开时显示；空串 = 未随本轮保存，角标仍可点）。
    text: str = ""


class CitationsEvent(_RunScoped):
    """本轮**新增**的引用（一次工具调用一批，一轮内可多次）。

    为什么必须有这个事件：前端早已做好 ``[Kn]`` 角标与引用卡的渲染层
    （``domain/knowledge.ts`` / ``CitationMark.tsx``），但后端从不发引用，
    整条链路是死的——律师只能看到「AI 说『根据判决』」，却点不开是哪一份。

    为什么是「新增」而不是「全量重发」：每帧只带这一次工具调用产出的那几条，
    帧大小与工具输出同阶；全量重发会让一轮里第十次检索的帧无限膨胀。
    前端按 ``cite_no`` 合并即可（后来的同号覆盖前面的，编号不会变）。

    落库不走这里：``AgentMessage.metadata["citations"]`` 存的是**本轮全部**
    （历史回放没有 SSE，只有 metadata）。
    """

    type: Literal["citations"]
    citations: list[CitationRef] = []


class CompactionEvent(_RunScoped):
    """上下文压缩进行中（pi 自动压缩或手动压缩触发）。

    ``phase="start"``：压缩开始（前端可显示「正在压缩上下文…」）；
    ``phase="end"``：压缩完成（历史已被摘要替代，前端提示「已压缩」）。
    """

    type: Literal["compaction"]
    phase: Literal["start", "end"]


class ErrorEvent(_RunScoped):
    """流内错误（已翻译成人话 + 稳定错误码）。

    ``message`` 是给律师看的句子（可改、可润色）；``code`` 是给程序分支的稳定
    枚举串（**一旦发出就不能改语义**，见 ``errors.py`` 的红线）。

    历史教训：此前只有 ``message``，前端 ``domain/error.ts`` 只能对中文文案做
    ``includes`` 归类——后端把「当前使用人数较多」改一个字，前端的「限流」分类
    就静默退回「未知错误」，没有任何测试会红。
    """

    type: Literal["error"]
    message: str
    #: 稳定错误码（``errors.ERROR_CODES`` 之一；空串 = 引入 code 之前的旧数据）。
    code: str = ""
    #: 这错该由谁修（见 :data:`ErrorScope`）。
    scope: ErrorScope = "unknown"
    #: 「人能拿去修」的参数：哪个后端、哪个模型、还能等几秒、哪把 key。
    #: 形状按 code 而定（见 ``errors.py`` 的各类 ``detail()``），刻意不写成固定
    #: 模型：把 union 塞进契约会让前端为每个 code 各写一个分支才能读一个字段。
    detail: dict[str, Any] = Field(default_factory=dict)


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
    | UiActionEvent
    | UiSnapshotRequestEvent
    | CompactionEvent
    | CitationsEvent
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
    UiActionEvent,
    UiSnapshotRequestEvent,
    CompactionEvent,
    CitationsEvent,
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


def _ts_type(annotation: Any, depth: int = 1) -> str:
    """把一个 Python 注解映射成 TS 类型；未知一律 ``unknown``（宁可松，不可错）。

    ``depth`` 只影响**嵌套模型**的缩进（见 :func:`_ts_object`）：``QuestionSpec``
    这类嵌套对象展开成内联对象字面量，缩进必须跟调用处对齐，否则读起来像另一
    个字段。
    """
    if annotation is type(None):
        return "null"
    if annotation is str:
        return "string"
    if annotation is bool:
        return "boolean"
    if annotation in (int, float):
        return "number"
    # 嵌套 pydantic 模型 → 内联对象字面量。不能退化成 ``unknown``：那样
    # ``question_request.questions`` 的字段名又只剩前端猜（这正是本次要修的）。
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _ts_object(annotation, depth)
    origin = get_origin(annotation)
    if origin is Literal:
        return _ts_literal(get_args(annotation))
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        rendered = " | ".join(_ts_type(a, depth) for a in args)
        return f"{rendered} | null" if len(args) != len(get_args(annotation)) else rendered
    if origin in (list, set, tuple):
        args = get_args(annotation)
        inner = _ts_type(args[0], depth) if args else "unknown"
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


def _ts_object(model: type[BaseModel], depth: int = 1) -> str:
    """一个 pydantic 模型 → 一段 TS 对象类型（顶层的 ``type`` 排第一）。

    ``type`` 排第一（它是判别式，读代码时先看到才知道这是哪种帧），其余按
    ``model_fields`` 的声明序——声明序就是文档顺序，前端读生成的 TS 时上下文一致。

    ``depth`` 是缩进层级：顶层事件是 1（字段 4 空格、右花括号 2 空格，与历史
    生成物逐字一致），嵌套模型逐层 +1。
    """
    names = list(model.model_fields)
    if "type" in names:
        names.remove("type")
        names.insert(0, "type")
    pad = "  " * depth
    inner_pad = "  " * (depth + 1)
    lines: list[str] = []
    for name in names:
        optional = _is_optional(model, name)
        rendered = _ts_type(model.model_fields[name].annotation, depth + 1)
        if optional and rendered.endswith(" | null"):
            rendered = rendered[: -len(" | null")]
        lines.append(f"{inner_pad}{name}{'?' if optional else ''}: {rendered}")
    body = "\n".join(lines)
    return "{\n" + body + "\n" + pad + "}"


def generate_ts() -> str:
    """生成 TypeScript 类型定义文件内容（从 ``model_fields`` 反射）。"""
    members = "\n  | ".join(_ts_object(model) for model in EVENT_MODELS)
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
