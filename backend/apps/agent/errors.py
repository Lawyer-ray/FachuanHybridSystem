"""Agent 错误码：typed error → SSE ``error`` 帧的**唯一**投影点。

## 为什么需要它

``ErrorEvent`` 原来只有 ``message: str``，前端 ``domain/error.ts`` 只能对中文
文案做 ``includes`` 归类——后端改一个字（「当前使用人数较多」→「当前使用的人
较多」）前端就静默退回「未知错误」，而且「服务端知道但没说」的东西（哪个后端、
哪个模型、还能等几秒、是哪把 key）前端一个都拿不到，律师也没法把问题描述清楚
去求助（只能截屏）。

## 形状：typed error + 边缘投影（不是全局错误码枚举表）

照 magpie ``internal/gui/api.go:3774`` 的 ``fail()``：那里**没有**一个集中的
错误码枚举，而是每个 domain 定义 typed error 结构体（``RuntimeUnavailableError``
/ ``NoModelsError`` / ``ShareError`` …），HTTP 边缘用 ``errors.As`` 把它们投影成
``code`` + 若干「人能拿去修」的字段。这样做的好处是：错误**发生时**才知道的
上下文（哪个后端、哪个模型、还能等几秒）留在抛出点，边缘只做纯粹的翻译，不
需要回头去猜。

本模块就是那个边缘：:func:`project` 是异常 → 线路帧的唯一出口。**不要在其它
地方手写 ``{"type": "error", ...}``**：手写一次就多一份 code 拼写，而 code 是
前端分支的依据。

## 红线：``code`` 一旦发出就不能改语义

前端按 ``code`` 决定图标 / 是否可重发 / 该找谁（律师、管理员、还是上游网关）。
改一个已发布 code 的含义，等于让线上旧前端对着一份新字典做事——而且不会有
任何报错。要表达新情况就**新增** code，不复用旧 code。

## 与 ``_record_run`` 的 ``error_kind`` 的关系

``AgentRun.error_kind`` 是**历史账本**（DB 里的短串，如 ``queue_timeout``），
改名等于历史数据对不上；``code`` 是**线路契约**。两者刻意分开：前者可以继续
按运维口径演进，后者向前端承诺稳定。
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from .backends.base import BackendError, BackendErrorKind
from .sse_types import ErrorScope

#: ``detail["reason"]`` 的长度上限。技术原文只用于排障，不该把整段 traceback /
#: 上游 HTML 错误页顺着 SSE 推给浏览器。
_REASON_LIMIT = 240

#: 疑似密钥的片段（``sk-...`` / ``Bearer ...``）。``detail`` 会进前端日志与用户
#: 截图，而上游错误消息里偶尔会把 Authorization 头原样回显——这一步是兜底，
#: 不是许可：**调用方仍然不得主动把 key 放进 detail**。
_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{4,})|(Bearer\s+[A-Za-z0-9._\-]{8,})", re.IGNORECASE)

#: 网关 429 的 ``retry-after``（pi / SDK 常把它拼进异常消息）。
_RETRY_AFTER_RE = re.compile(r"retry[-_ ]?after[\"'=:\s]+(\d+)", re.IGNORECASE)


class AgentError(RuntimeError):
    """所有可投影错误的基类。

    ``code`` / ``scope`` 是**类级常量**：同一类错误在任何路径下必须给出同一个
    code，否则前端映射表又要退化成猜。上下文用 ``detail`` 带（实例级）。
    """

    #: 稳定线路错误码（snake_case，英文机器串，不是给人读的句子）。
    code: ClassVar[str] = "unknown"
    #: 谁来修：``account``（律师/账号）、``model``（后端或模型侧）、
    #: ``request``（这次请求本身）、``tool``（工具调用参数）、``unknown``。
    scope: ClassVar[ErrorScope] = "unknown"
    #: 兜底文案（中文，面向律师）。抛出时可用构造参数覆盖成更具体的说法。
    default_message: ClassVar[str] = "Agent 运行失败，请稍后重试"

    def __init__(self, message: str = "", **detail: Any) -> None:
        super().__init__(message or self.default_message)
        # 空值不占位：前端拿到 ``{"model": ""}`` 只会多一次无意义判断。
        # 字符串值一律过 ``_clip``（脱敏 + 截断）：``detail`` 会进前端日志与
        # 用户截图，抛错点未必意识到原文里可能有 key 或整段 traceback。
        self._detail: dict[str, Any] = {
            key: _clip(value) if isinstance(value, str) else value
            for key, value in detail.items()
            if value not in (None, "")
        }

    def detail(self) -> dict[str, Any]:
        """「人能拿去修」的参数（哪个后端 / 哪个模型 / 还能等几秒 / 哪把 key）。"""
        return dict(self._detail)


class RateLimitedError(AgentError):
    """上游限流（网关 429 / 每 key 并发上限）。

    ``scope="account"`` 而不是 ``model``：这不是「模型坏了」，而是「这个账号
    这一刻用得太快」——换一把 key 或退避几十秒就能过，律师自己能等。
    """

    code: ClassVar[str] = "rate_limited"
    scope: ClassVar[ErrorScope] = "account"
    default_message: ClassVar[str] = "模型网关限流，请稍后重试"


class QuotaExceededError(AgentError):
    """本地或租户级闸门已满（进程池排队超时 / 对比栏席位满）。

    与 :class:`RateLimitedError` 分开：那个是**上游**说「你太快」，这个是**我们
    自己**说「现在没有执行位」。前者要退避，后者只需等到有人跑完。
    """

    code: ClassVar[str] = "quota_exceeded"
    scope: ClassVar[ErrorScope] = "account"
    default_message: ClassVar[str] = "当前使用人数较多，请稍后重试"


class BackendUnavailableError(AgentError):
    """后端根本跑不起来（可执行文件缺失、runtime 未启动、网关未配置）。"""

    code: ClassVar[str] = "backend_unavailable"
    scope: ClassVar[ErrorScope] = "model"
    default_message: ClassVar[str] = "Agent 运行时不可用，请联系管理员（详见服务端日志）"


class CapabilityUnsupportedError(AgentError):
    """请求的能力这个后端没有（未知 agent kind、能力位为 ``False``）。"""

    code: ClassVar[str] = "capability_unsupported"
    scope: ClassVar[ErrorScope] = "request"
    default_message: ClassVar[str] = "当前后端不支持该能力，请换一栏或改用支持的后端"


class ContextOverflowError(AgentError):
    """上下文超出模型窗口。重试无用——必须压缩上下文或新开会话。"""

    code: ClassVar[str] = "context_overflow"
    scope: ClassVar[ErrorScope] = "request"
    default_message: ClassVar[str] = "上下文已超出模型窗口，请先压缩上下文或新开会话"


class UpstreamTimeoutError(AgentError):
    """上游超时（模型网关/推理服务没在时限内回应）。"""

    code: ClassVar[str] = "upstream_timeout"
    scope: ClassVar[ErrorScope] = "model"
    default_message: ClassVar[str] = "上游模型响应超时，请稍后重试"


class ToolArgumentsError(AgentError):
    """工具参数不合法（模型生成的参数过不了工具自己的校验）。

    当前没有线路发射点：工具参数错误先回给**模型**让它改（``tool_result
    .is_error``），并不直接给律师看。保留它是为了让工具边缘将来能直接投影，
    而不必临时发明一个 code。
    """

    code: ClassVar[str] = "tool_args_invalid"
    scope: ClassVar[ErrorScope] = "tool"
    default_message: ClassVar[str] = "工具调用参数不合法，已回给模型重试"


class AuthFailedError(AgentError):
    """身份/凭证问题（铸不出律师凭证、上游 401/403）。重试无用，要重新登录或找管理员。"""

    code: ClassVar[str] = "auth_failed"
    scope: ClassVar[ErrorScope] = "account"
    default_message: ClassVar[str] = "无法为当前用户签发工具访问凭证，请联系管理员"


class SessionNotFoundError(AgentError):
    """会话不存在或不属于当前用户（两者同一文案：不向试探者泄露归属）。"""

    code: ClassVar[str] = "session_not_found"
    scope: ClassVar[ErrorScope] = "request"
    default_message: ClassVar[str] = "会话不存在"


class TooManyAgentsError(AgentError):
    """一次选了太多栏（超过 ``multi.MAX_ANSWERS``）。"""

    code: ClassVar[str] = "too_many_agents"
    scope: ClassVar[ErrorScope] = "request"
    default_message: ClassVar[str] = "一次同时问的 agent 太多"


#: 全部错误类型（顺序 = 文档顺序）。新增错误必须登记：``ERROR_CODES`` 与
#: ``test_agent_error_codes`` 都从这里取，漏登记 = 它没有稳定 code。
ERROR_TYPES: tuple[type[AgentError], ...] = (
    RateLimitedError,
    QuotaExceededError,
    BackendUnavailableError,
    CapabilityUnsupportedError,
    ContextOverflowError,
    UpstreamTimeoutError,
    ToolArgumentsError,
    AuthFailedError,
    SessionNotFoundError,
    TooManyAgentsError,
    AgentError,  # unknown：兜底，排最后
)

#: 已发布的全部 code（前端可据此做穷举映射）。
ERROR_CODES: frozenset[str] = frozenset(cls.code for cls in ERROR_TYPES)

#: ``BackendErrorKind`` → ``(code, scope)``。
#:
#: 后端在边界处已经把自家异常收敛成 :class:`BackendError`（见 ``base.py`` 的
#: 映射表），这里再把它的粗分类翻成线路 code——两跳而不是一跳，是因为
#: ``BackendErrorKind`` 服务于「编排层选哪句文案」，它的取值可以随运维口径变，
#: 而 code 是向前端承诺过的稳定契约。两者混成一个枚举会让其中一方被迫冻结。
_BACKEND_KIND_CODES: dict[BackendErrorKind, tuple[str, ErrorScope]] = {
    BackendErrorKind.UNAVAILABLE: (BackendUnavailableError.code, BackendUnavailableError.scope),
    BackendErrorKind.BUSY: (QuotaExceededError.code, QuotaExceededError.scope),
    BackendErrorKind.AUTH: (AuthFailedError.code, AuthFailedError.scope),
    BackendErrorKind.RATE_LIMITED: (RateLimitedError.code, RateLimitedError.scope),
    BackendErrorKind.CONTEXT_OVERFLOW: (ContextOverflowError.code, ContextOverflowError.scope),
    BackendErrorKind.UNKNOWN: (AgentError.code, AgentError.scope),
}

#: ``PiError`` 只能看消息（pi 把子进程的失败原因包成同一个类型，见 ``base.py``
#: 的映射表说明）。顺序即优先级：429 的原文里常同时出现 ``timeout`` 的说明，
#: 先认限流才不会把「等 60 秒」讲成「上游超时」。
_PI_MESSAGE_RULES: tuple[tuple[re.Pattern[str], type[AgentError]], ...] = (
    (re.compile(r"retry[-_ ]?after|\b429\b|rate.?limit|too many requests", re.IGNORECASE), RateLimitedError),
    (re.compile(r"\b401\b|\b403\b|unauthor|forbidden|invalid.?api.?key", re.IGNORECASE), AuthFailedError),
    (
        re.compile(r"context.?length|context.?window|maximum context|too many tokens", re.IGNORECASE),
        ContextOverflowError,
    ),
    (re.compile(r"timed?\s?out|\btimeout\b", re.IGNORECASE), UpstreamTimeoutError),
)


def _clip(text: str) -> str:
    """技术原文脱敏 + 截断（见 ``_SECRET_RE`` / ``_REASON_LIMIT`` 的理由）。"""
    cleaned = _SECRET_RE.sub("***", text or "").strip()
    return cleaned[:_REASON_LIMIT]


def _retry_after_seconds(text: str) -> int | None:
    """从上游原文里取 ``retry-after`` 秒数；取不到返回 ``None``（不编造）。"""
    match = _RETRY_AFTER_RE.search(text or "")
    if match is None:
        return None
    value = int(match.group(1))
    return value if 0 < value <= 3600 else None


def default_message_for(code: str) -> str:
    """code 的兜底中文文案（新增 code 忘了登记时退回最泛的一句）。"""
    for cls in ERROR_TYPES:
        if cls.code == code:
            return cls.default_message
    return AgentError.default_message


def _classify(exc: BaseException) -> tuple[str, ErrorScope, dict[str, Any], str]:
    """异常 → ``(code, scope, detail, message)``。

    四段 ``isinstance`` 对应四类来源，不是 ``switch``：一个异常只会命中第一个
    （``BackendError`` 与 pi 异常都是 ``RuntimeError`` 的子类，但彼此不继承）。
    """
    if isinstance(exc, AgentError):
        return exc.code, exc.scope, exc.detail(), str(exc)

    if isinstance(exc, BackendError):
        code, scope = _BACKEND_KIND_CODES.get(exc.kind, (AgentError.code, AgentError.scope))
        detail: dict[str, Any] = {"reason": _clip(exc.message), "retryable": exc.retryable}
        retry_after = _retry_after_seconds(exc.message)
        if retry_after is not None:
            detail["retry_after_seconds"] = retry_after
        return code, scope, detail, default_message_for(code)

    # pi 的两个专用异常排在他的父类前面（``PiNotAvailableError`` 是 ``PiError``
    # 的子类，顺序反了会被父类分支吞掉，用户看到的是「运行失败」而不是「不可用」）。
    # 延迟导入：``errors`` 会被 API 层与测试直接 import，而 pi 包会连带拉起
    # 子进程相关依赖（``pool`` / ``shared_mcp``）。这里只在真的要翻译时才用。
    from .pi.pool import PoolQueueTimeoutError
    from .pi.rpc_client import PiError, PiNotAvailableError

    if isinstance(exc, PiNotAvailableError):
        # 文案逐字保留：「pi 运行时不可用」是律师与运维都已经认得的说法
        # （集成测试也断言这一句），换措辞要同时改三处，收益不如稳定。
        detail = {"reason": _clip(str(exc))}
        message = "pi 运行时不可用，请联系管理员（详见服务端日志）"
        return BackendUnavailableError.code, BackendUnavailableError.scope, detail, message

    if isinstance(exc, PoolQueueTimeoutError):
        detail = {"reason": _clip(str(exc)), "limit": "agent_pool"}
        return QuotaExceededError.code, QuotaExceededError.scope, detail, "当前使用人数较多，请稍后重试"

    if isinstance(exc, PiError):
        text = str(exc)
        error_type: type[AgentError] = AgentError
        for pattern, candidate in _PI_MESSAGE_RULES:
            if pattern.search(text):
                error_type = candidate
                break
        detail = {"reason": _clip(text)}
        retry_after = _retry_after_seconds(text)
        if retry_after is not None:
            detail["retry_after_seconds"] = retry_after
        # 除限流/鉴权/上下文/超时以外，仍是 pi 的通用失败文案（与引入 code 前一致）。
        message = "pi 运行失败，请稍后重试（详见服务端日志）"
        if error_type is RateLimitedError:
            message = error_type.default_message
        return error_type.code, error_type.scope, detail, message

    if isinstance(exc, LookupError):
        # ``get_backend`` 对未知 kind 抛 LookupError（见 ``multi.py`` 的失败矩阵：
        # 不在这里把整轮拒掉，只让那一栏报「这个后端不认识」）。
        detail = {"reason": _clip(str(exc))}
        return (
            CapabilityUnsupportedError.code,
            CapabilityUnsupportedError.scope,
            detail,
            CapabilityUnsupportedError.default_message,
        )

    return (
        AgentError.code,
        AgentError.scope,
        {"reason": _clip(str(exc)), "exc_type": type(exc).__name__},
        (AgentError.default_message),
    )


def project(
    exc: BaseException,
    *,
    agent: str = "",
    run_id: str = "",
    message: str | None = None,
) -> dict[str, Any]:
    """异常 → 一帧 ``error`` 事件（**唯一**投影点）。

    Args:
        exc: 任意异常（``AgentError`` / ``BackendError`` / pi 异常 / 其它）。
        agent: 产出这帧的后端 kind。空串时不写该键——多答路径的
            ``_tag`` 会按栏补，写个空串反而会让它 ``setdefault`` 失效。
        run_id: 本轮寻址键；同上，空串不写。
        message: 覆盖文案（**只**在调用方知道比默认更准确的说法时用）。

    Returns:
        可直接 ``yield`` 的 dict；字段与 ``sse_types.ErrorEvent`` 一一对应。
    """
    code, scope, detail, text = _classify(exc)
    frame: dict[str, Any] = {
        "type": "error",
        "message": message or text,
        "code": code,
        "scope": scope,
        "detail": detail,
    }
    if agent:
        frame["agent"] = agent
    if run_id:
        frame["run_id"] = run_id
    return frame


__all__ = [
    "ERROR_CODES",
    "ERROR_TYPES",
    "AgentError",
    "AuthFailedError",
    "BackendUnavailableError",
    "CapabilityUnsupportedError",
    "ContextOverflowError",
    "QuotaExceededError",
    "RateLimitedError",
    "SessionNotFoundError",
    "ToolArgumentsError",
    "TooManyAgentsError",
    "UpstreamTimeoutError",
    "default_message_for",
    "project",
]
