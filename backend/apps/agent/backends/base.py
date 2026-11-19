"""Agent 后端抽象：一个「能跑一轮对话」的运行时。

为接入多个 agent（pi / DeepSeek Harness / …）提供统一接缝。
本模块只定义协议与能力声明，不包含任何具体实现。

## 分工边界（谁负责什么）

本抽象只把「跑一轮、吐 SSE 事件」这件事收进接口，**其余全部留在编排层**
（``services/chat/stream.py``）。刻意如此：

- **落库**（``AgentMessage``）归编排层。后端自己写库就会出现两套审计来源，
  同一轮对话在库里出现两份或零份，回放与成本归因都无从对齐。
- **审批**（``approval_request``）走后端自带的回调链路，再由编排层注入事件流。
  pi 走 extension → Redis → SSE 队列，别的后端可能走 webhook；协议不假设传输方式。
- **池化 / 排队 / 取消**归编排层。后端可以是常驻服务（HTTP）或一次性子进程
  （pi 就是每请求一个进程），协议不假设生命周期形态。
- **工具面**（MCP 工具选择、技能注入）归编排层配置，``RunContext`` 只传选择结果。

## 为什么 ``stream()`` 只管一轮

pi 的模型是「每次 prompt 起一个新进程，跑完即关」，DeepSeek Harness 更可能是
常驻连接。把 ``start/close`` 放进协议会让两者互相迁就——pi 要多一层假常驻，
Harness 要为每次运行重连。只要求 ``stream()`` 自包含，两种形态都能实现。

## 三个必须在本层显式化的缝

只收 ``stream()`` 是不够的，以下三处在接入第二个 agent 时会立刻爆出「遗漏假设是 pi」：

1. **运行中控制**（:class:`LiveBackendHandle`）。编排层的 ``live_sessions`` 表
   存的是「正在跑的那个对象」，HTTP 的 steer / abort / compact 端点直接调它的
   方法。存具体对象就意味着同一张表里会混两种不兼容的类型，端点无法区分。
2. **错误分类**（:class:`BackendError` / :class:`BackendErrorKind`）。编排层靠
   ``except PiNotAvailableError / PiError / PoolQueueTimeoutError`` 决定给用户
   看哪句话——这是把 ``if agent == "pi"`` 搬进了 except 子句。
3. **同会话并发**（:attr:`BackendCapabilities.concurrent_in_session`）。
   「同一会话同时只允许一个运行」是 pi 的实现事实，但此前只写在
   ``live_sessions`` 的注释里。想开「两个 agent 同题并行」就必须让后端
   自己声明能不能，而不是编排层假设所有后端都和 pi 一样。

第 1 条的可选工厂钩子是 ``make_handle``（见 :data:`MAKE_HANDLE_METHOD`）。
"""

from __future__ import annotations

import enum
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

#: 后端产出的一帧：``dict`` 是要转发给前端的 SSE 事件；``None`` 是「本 tick
#: 无事件」的让位信号（编排层借这个间隙把外部总线里的审批事件推进来）。
#:
#: 为什么把 ``None`` 写进契约：pi 的读取循环在「暂时没有新事件」时必须让出一次
#: 控制权，否则同一个协程会一直占着事件循环，审批事件永远进不来。用空 dict 表达
#: 「无事件」的话，它和「类型未知的事件」无法区分；``None`` 在类型上就是「没有」。
StreamFrame = dict[str, Any] | None


@dataclass(frozen=True)
class BackendCapabilities:
    """后端能力声明。

    前端与编排层据此决定「能不能显示逐字动画」「支不支持插话」等，
    而不是硬编码 `if agent == "pi"`。

    新增后端时先如实声明能力：缺哪一块一眼看到，也倒逼编排层做降级。

    各字段是**事实陈述，不是愿望**：声明 ``True`` 就必须真的产出对应行为，
    否则调用方按 ``True`` 写的代码路径会在运行期静默走空（例如声明了
    ``streaming`` 却不发 ``delta``，前端只会看到长时间空白后突然出现整段文字）。
    ``frozen=True`` 是刻意的——能力是后端的静态属性，运行期不可变；允许可变
    会让「同一个后端在不同请求上表现出不同能力」，前端无法预判 UI 形态。
    """

    #: 是否产出增量 token（``delta`` / ``thinking`` 事件）。
    #: ``False`` 表示只能等整段回答完成再一次性给出（事件的 ``delta`` 一次性
    #: 满载或改用别的形状）。前端据此决定是否显示逐字动画、是否隐藏「正在输入」。
    streaming: bool

    #: 是否支持工具调用（``tool_call`` / ``tool_result`` 事件）。
    #: ``False`` 时编排层不需要准备工具面配置，也不能把「查了哪些法条」当
    #: 可展示证据——那些事件永远不会来。
    tool_calls: bool

    #: 是否支持人工审批拦截（高危工具调用前停下来等律师确认）。
    #: 审批回调经后端自带的链路路由回本会话，编排层只负责把
    #: ``approval_request`` 推进事件流。``False`` 的后端在高危动作上**没有**
    #: 人工闸门，启用前必须先由合规确认，不能当成「和 pi 一样」直接上线。
    approval: bool

    #: 是否自带上下文压缩（会话变长时自己裁剪/摘要，不需要编排层介入）。
    #: ``True`` 时编排层不渲染 transcript、不主动 compact，水位展示走 done 事件；
    #: ``False`` 时上下文长度由编排层负责，必须实现自己的裁剪策略，否则长会话
    #: 会因为超窗直接报错。
    compaction: bool

    #: 是否支持运行中插话（用户在一轮还没跑完时追加指令）。
    #: ``False`` 时前端必须禁用插话入口——否则用户敲进去的话会被丢弃而界面
    #: 毫无反馈，比直接禁用更糟。
    steer: bool

    #: 是否允许同一会话内多个运行（例如两个 agent 同题并行）。
    #: pi 是 ``False``：它靠进程内状态管会话，同会话两个进程会互相污染。
    #: 编排层开「双答」时必须同时拿到两个 backend 的这个标志都是 ``True``，
    #: 否则退化为串行（先跑完 A 再跑 B），而不是直接拒绝——用户的诉求是
    #: 「两个答案」，慢一点比没有好。
    #: 这个字段默认 ``False`` 的保守性很重要：新后端默认不能并发，想并发就
    #: 显式声明。反过来（默认 ``True``）会让新后端在没验证过的情况下被编排层
    #: 直接并行拉起，污染会话上下文且没有任何测试能提前发现。
    concurrent_in_session: bool = False


class BackendErrorKind(enum.StrEnum):
    """后端错误的粗分类——编排层据此选用户文案，不看具体异常类型。

    分类粒度只到「用户该看到哪句话」为止，不再细分：再细就会退回「按异常
    类型分支」，那正是本层要消除的耦合。
    """

    #: 后端没装 / 起不来（可执行文件缺失、服务未启动）。
    UNAVAILABLE = "unavailable"
    #: 执行位满 / 排队超时。属于「忙」不是故障，文案要引导稍后重试。
    BUSY = "busy"
    #: 凭据失效（token 过期、API key 被吊销）。重试无用，要让用户重新登录。
    AUTH = "auth"
    #: 被上游限流。``retryable=True`` 但需要退避。
    RATE_LIMITED = "rate_limited"
    #: 上下文超出模型窗口。重试无用，必须压缩或新开会话。
    CONTEXT_OVERFLOW = "context_overflow"
    #: 无法归类。默认值：宁可粗略，也不要为了塞进某个分类而误导用户。
    UNKNOWN = "unknown"


class BackendError(RuntimeError):
    """所有后端的统一异常基类。

    实现方**必须**在边界处把自家异常转成它，否则编排层的 ``except`` 会重新
    变成 pi 专属（``except PiNotAvailableError`` 对第二个后端永远不触发，
    用户看到的是「未知错误」而不是「运行时不可用」）。

    用 ``RuntimeError`` 而不是 ``Exception``：与 pi 现有的 ``PiError`` /
    ``PoolQueueTimeoutError`` 同为 ``RuntimeError`` 子类，将来把 pi 异常收编成
    ``BackendError`` 子类时，只写了 ``except RuntimeError`` 的旧代码行为不变。

    ## pi 的映射表（``PiBackend`` 接线时写进它的边界处）

    ==============================================  =============================  ============
    原异常                                           ``BackendErrorKind``            ``retryable``
    ==============================================  =============================  ============
    ``PiNotAvailableError``                         ``UNAVAILABLE``                ``False``
    ``PoolQueueTimeoutError``                       ``BUSY``                       ``True``
    ``PiError``（消息含 ``auth`` / ``401`` / ``403``）  ``AUTH``                       ``False``
    ``PiError``（消息含 429 / ``rate limit``）        ``RATE_LIMITED``               ``True``
    ``PiError``（消息含 context / token 超限）        ``CONTEXT_OVERFLOW``           ``False``
    ``PiError``（其余）                              ``UNKNOWN``                     ``False``
    ==============================================  =============================  ============

    ``PiError`` 分四类的依据：pi 把子进程的失败原因包成同一个 ``PiError`` 类型，
    只能看消息。按消息字符串匹配确实粗糙，但它比现状（一律归「pi 运行失败」）
    好：至少 ``AUTH`` / ``CONTEXT_OVERFLOW`` 不会被提示成「请稍后重试」。
    后续应让 pi 侧在 JSON 响应里带 ``error.kind``，那时可以删掉消息匹配。

    **``asyncio.CancelledError`` / ``GeneratorExit`` 不得转化**：用户按停止不是错误，
    包成 ``BackendError`` 会让 ``AgentRun`` 把取消记成失败。
    """

    def __init__(self, kind: BackendErrorKind, message: str, *, retryable: bool = False):
        super().__init__(message)
        #: 错误分类；编排层只看它，不看异常类型本身。
        self.kind = kind
        #: 同一请求立刻重试是否可能成功。``True`` 只代表「可能」，不代表「值得」：
        #: ``RATE_LIMITED`` 仍需要退避，``AUTH`` / ``CONTEXT_OVERFLOW`` 恒为 ``False``
        #: ——把它们标成可重试会让编排层白白重放，用户等更久、账单更高。
        self.retryable = retryable
        #: 原始消息。父类 ``args[0]`` 已有，这里给个具名属性便于结构化日志。
        self.message = message

    def __str__(self) -> str:
        suffix = "（可重试）" if self.retryable else ""
        return f"[{self.kind}]{suffix} {self.message}"

    @classmethod
    def wrap(cls, exc: BaseException, kind: BackendErrorKind, *, retryable: bool = False) -> BackendError:
        """把一个后端私有异常转成 ``BackendError``，保留原始类型与堆栈作为 cause。

        保留 cause 而不是只留字符串：日志里要能看到 pi / Harness 的原始异常
        类型与 traceback，否则「转换」等于把排障信息丢掉。
        """
        error = cls(kind, str(exc) or exc.__class__.__name__, retryable=retryable)
        error.__cause__ = exc
        return error


@runtime_checkable
class LiveBackendHandle(Protocol):
    """一个正在运行的后端的控制柄。

    ``stream()`` 跑到一半时，HTTP 端点靠它插话 / 中止 / 看统计。
    实现方可以是 pi 子进程的包装、也可以是远程会话的客户端。

    为什么单独定义而不是让 ``stream()`` 直接返回自己：``stream()`` 的返回值
    必须是一个干净的事件迭代器（便于实现方直接交出下游迭代器）。控制柄是
    「另一条通道」——它从 HTTP 请求进来，和正在跑的这条流并发使用，两者
    生命周期也不同（流结束时句柄就该失效）。合成一个对象会让「流已结束但
    句柄被当成有效」这类竞态无从表达。

    ## 迁移路径（PiBackend 接线时的活，不在本抽象里做）

    1. ``PiBackend`` 实现可选钩子 :data:`MAKE_HANDLE_METHOD`
       （``make_handle(ctx, pi_session)``），返回一个薄包装：
       ``run_id`` 取 ``ctx.run_id``，``kind = "pi"``，五个方法与
       ``PiRpcSession`` 同名方法一一转调（``get_stats`` → ``get_session_stats``），
       并把 ``PiError`` 按 :class:`BackendErrorKind` 映射后抛出（见
       :class:`BackendError` 的映射说明）。
    2. ``live_sessions`` 的表值类型从 ``PiRpcSession`` 改成 ``LiveBackendHandle``，
       ``register(session_id, handle)``；表里从此不出现具体后端对象。
    3. ``live_control`` / ``compact_service`` 只调 ``LiveBackendHandle`` 的五个方法。
       ``clear_queue`` 不在本协议里：它是 pi 的排队模型特有的，要保留就走
       ``capabilities`` 新增字段或另开可选协议，别混进最小控制面。
    4. ``live_sessions`` 的同会话唯一约束改为读
       ``capabilities.concurrent_in_session``：``False`` 时维持 ``SessionBusyError``，
       ``True`` 时允许同一会话挂多个句柄（按 ``run_id`` 索引）。

    ## 实现方注意

    ``steer`` / ``follow_up`` 的返回值是后端自定的 disposition 字符串
    （pi 是 ``queued`` / ``handled``），编排层只透传给前端、不做语义分支。
    """

    #: 本轮的运行 id（= ``RunContext.run_id``）。两个 agent 同题并行时，
    #: HTTP 端点靠它确认「我操作的是哪一条流」，而不是靠会话 id 猜。
    run_id: str

    #: 后端标识（= ``AgentBackend.kind``）。端点据此回报「谁被中止了」。
    kind: str

    async def steer(self, message: str) -> str:
        """运行中插话：当前 turn 的工具调用跑完后、下次 LLM 调用前生效。"""
        ...

    async def follow_up(self, message: str) -> str:
        """追加一轮：后端干完当前所有活（无工具调用、无排队消息）后再跑。"""
        ...

    async def abort(self) -> bool:
        """中止当前运行；返回是否成功送达（``False`` 表示进程已退出等）。"""
        ...

    async def get_stats(self) -> dict[str, Any]:
        """取运行统计（token 计数 / 成本 / 上下文水位）。尽力而为：拿不到返回 ``{}``。"""
        ...


@runtime_checkable
class AgentBackend(Protocol):
    """一个可运行一轮对话的 agent 后端。

    契约（实现方必须满足）：

    - ``stream()`` 产出的事件必须符合 ``sse_types.py`` 定义的 SSE 契约
      （``type`` 取 ``meta`` / ``activity`` / ``delta`` / ``thinking`` /
      ``tool_call`` / ``tool_result`` / ``usage`` / ``approval_request`` /
      ``question_request`` / ``compaction`` / ``error`` / ``done``）；
    - 事件体必须带 ``agent`` 字段（= ``kind``）与 ``run_id``：两个 agent 同题
      并行时，前端靠这两个字段把交错的事件分流到不同栏。``meta`` / ``done``
      另需带 ``session_id``；
    - 不得自行写 ``AgentMessage``（落库归编排层，保证审计单一来源）；
    - 不得自行处理审批（审批走后端自带的回调链路或编排层注入）；
    - 一轮结束时**必须**产出且只产出一个 ``done``（或一个 ``error``）。
      ``stream()`` 自然结束时若没发过 ``done``，编排层会当成截断——前端会一直
      显示「生成中」，所以要显式收尾，不要靠迭代器结束表达「跑完了」。
    - 异常必须在边界处转成 :class:`BackendError`（见 :meth:`stream` 的 Raises）。

    **另有一个可选约定**（故意不写进本协议，见 :data:`MAKE_HANDLE_METHOD`）：
    声明了 ``capabilities.steer`` 的后端应实现 ``make_handle(ctx, inner)``，
    把本次运行的具体对象包成 :class:`LiveBackendHandle` 交给编排层登记。
    """

    #: 后端标识（``"pi"`` / ``"deepseek-harness"`` …）。
    #: 同时是注册表的键与事件 ``agent`` 字段的取值，必须是稳定的短标识：
    #: 它会进事件流、进 ``AgentRun`` 归因，改名等于历史数据对不上。
    kind: str

    #: 静态能力声明（见 :class:`BackendCapabilities`）。
    capabilities: BackendCapabilities

    def stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        """跑一轮，产出 ``StreamFrame`` 序列（SSE 事件字典，或表示「本 tick 无事件」的 ``None``）。

        返回的是**异步生成器**句柄（``AsyncGenerator``）而不是 ``AsyncIterator``：
        编排层在客户端断开时需要调 ``aclose()`` 主动关掉上游（否则子进程要等到
        GC 才收），而 ``AsyncIterator`` 协议里没有这个方法。

        声明成普通 ``def`` 而不是 ``async def``，是为了让实现方直接把下游迭代器
        交出去（``return some_async_gen()`` 只能写在普通方法里）。

        Args:
            ctx: 本轮输入（见 :class:`RunContext`）。

        Yields:
            符合 ``sse_types.py`` 契约的事件字典。

        Raises:
            BackendError: 后端在边界处把自家异常转成它抛给编排层——这是
                **唯一**能让编排层写后端无关 ``except`` 的方式。抛别的异常
                编排层只能落到兜底的「未知错误」文案。

                例外：用户主动中止（``asyncio.CancelledError`` / ``GeneratorExit``）
                必须原样上抛，不要包成 ``BackendError``——包了会让编排层把
                「用户按了停止」记成运行失败，``AgentRun`` 的成功率统计就废了。
            这里不要把堆栈塞给前端，堆栈只进日志。
        """
        ...


#: 可选的「把本次运行的具体后端对象包成控制柄」工厂方法名。
#: 签名::
#:
#:     def make_handle(self, ctx: RunContext, inner: Any) -> LiveBackendHandle | None
#:
#: 返回值 ``None`` 表示这一轮不支持运行中控制。``inner`` 的类型由实现方自定
#: （pi 是 ``PiRpcSession``），用 ``Any`` 是因为本层不能 import 任何具体后端
#: 模块——那会让「导入抽象层」连带拉起 pi 依赖。
#:
#: **为什么不放进 ``AgentBackend`` 协议（尽管它是本层的一部分）**：
#: ``runtime_checkable`` 只查属性存在性，写进协议就变成了必填——不支持插话的
#: 后端（声明 ``capabilities.steer = False``，甚至没有句柄概念）会直接
#: ``isinstance(..., AgentBackend)`` 失败、被注册表拒之门外。因此它是
#: **可选约定**，调用方一律 ``getattr(backend, MAKE_HANDLE_METHOD, None)`` 探测。
#: 也不用 ``Protocol`` 继承 + 默认方法：Python 3.12 的 ``runtime_checkable``
#: 对带默认实现的协议成员仍按「必须存在」处理，绕不掉这个陷阱。
#:
#: pi 的实现就是把 ``PiRpcSession`` 薄薄包一层：``kind = "pi"``、
#: ``run_id = ctx.run_id``，``steer`` / ``follow_up`` / ``abort`` 直接转调，
#: ``get_stats`` 转调 ``get_session_stats``。
MAKE_HANDLE_METHOD = "make_handle"


@dataclass(frozen=True)
class RunContext:
    """一次运行的输入。

    `run_id` 是本轮的唯一寻址维度（会话 + 后端 + 轮次），
    事件、审批、成本统计都靠它归因。两个 agent 同题并行时，
    前端靠它把交错的事件分流到不同栏。

    ``frozen=True``：本轮输入是一次运行的快照。中途改字段会造出「前半轮用
    旧 prompt、后半轮用新 token」这种查不出来的错配，宁可让实现方显式构造
    新的 ctx。
    """

    #: 本轮运行 id（会话 + 后端 + 轮次）。事件里的 ``run_id``、审批归属、
    #: ``AgentRun`` 成本记录都用它归因。**必须每轮唯一**：复用上一轮的值会让
    #: 两次运行的成本与审批串到一条记录上。
    run_id: str

    #: 所属会话（``AgentSession`` 实例）。用 ``Any`` 是为了避免
    #: ``backends`` ↔ ``models`` 的循环 import；实现方按需自己 import 类型。
    #: 只读使用——后端的落库职责已被剥掉（见协议契约），改会话字段归编排层。
    session: Any

    #: 发起本轮的用户 id；``None`` 表示无用户身份（测试 / 后台任务）。
    #: 用它铸造工具访问凭证：**不要**在 ``None`` 时回退成超管账号，那会让
    #: 工具以越权身份执行。
    user_id: int | None

    #: 本轮要发给 agent 的文本。
    #: 注意它**未必等于用户原话**：编排层在会话缺上下文时会把历史渲染成
    #: transcript 附在前面；标题生成、锚点剥离等也在上游做完。后端应当原样发送，
    #: 不要再自己拼接历史——那会让会话里同时存在两套上下文来源。
    prompt: str

    #: 代表当前用户调用工具的身份凭证（由编排层预先铸造；铸不出时整轮都不会开始）。
    #: 后端必须把它注入工具调用链路（pi 是 ``FACHUAN_USER_TOKEN`` 环境变量），
    #: 否则工具要么无凭证失败、要么退回服务账号越权执行。**不得写进日志**。
    user_token: str

    #: 本轮使用的模型名；``None`` 表示由后端按自身默认策略选择。
    #: 编排层会在运行结束后把实际使用的模型回写会话，所以实现方应尽量回报
    #: 真实值（事件或 stats），不要静默换模型。
    model: str | None

    #: 本轮的工具面选择（pi 的 ``--tools`` 白名单，如子 agent 传只读集合）；
    #: ``None`` 表示用后端的默认全量业务工具集。作为运行参数而不是全局常量：
    #: 主会话与只读子 agent 必须能在同一进程内并发存在，全局常量会让两边互相覆盖。
    #: 声明 ``capabilities.tool_calls = False`` 的后端可忽略此字段。
    tool_selection: str | None

    #: 本轮**指定**的网关 API key；``None`` 表示由后端按自己的轮转口径选。
    #:
    #: ## 为什么 key 要由编排层指定而不是后端自己轮转
    #:
    #: 网关对每把 key 限 ``max_parallel_requests = 3``（实测 429 + ``retry-after: 60``）。
    #: 后端的 ``_next_key`` 是**全局轮转计数**：它只保证「先后两次通常不同」，
    #: 不保证同一轮的三个 agent 不同，也不知道哪把 key 已经满了。所以「三 agent
    #: 用三把 key」必须由编排层在**轮次级别**显式分配（见 ``key_scheduler``）。
    #:
    #: 后端实现方：**有这个值就照着用**，不要再调 ``_next_key`` 覆盖它——那会让
    #: 编排层的分配白做，且两个 agent 撞回同一把 key 时没有任何报错，只表现为
    #: 「偶尔某栏卡 60 秒」。
    #:
    #: 安全：**不得写进日志**（与 ``user_token`` 同级）。需要标识时用
    #: ``key_scheduler.fingerprint``。
    api_key: str | None = None
