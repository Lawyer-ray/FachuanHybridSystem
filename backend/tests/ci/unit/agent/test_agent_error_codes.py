"""``error`` 事件的具名错误码（``apps/agent/errors.py`` 的投影表）。

为什么单独守它：``code`` 是前端分支的**唯一**依据（``domain/error.ts`` 按它
决定图标、是否可重发、该找谁）。后端改语义或改拼写时，前端不会有任何报错——
只会静默走错分支，而错误恰恰是律师最需要看清的那一屏。

本文件把「异常 → code / scope / detail」钉成表：

- 全部 code 逐字列举（改语义必须先改这张表，评审时看得见）；
- 每条来源（typed error / ``BackendError`` / pi 异常 / 兜底）各自的投影；
- 投影结果必须能被 ``ErrorEvent`` 校验通过（契约与投影不脱节）；
- ``detail`` 里的技术原文必须脱敏 + 截断（它会进前端日志与用户截图）。
"""

from __future__ import annotations

import json

import pytest

from apps.agent.backends.base import BackendError, BackendErrorKind
from apps.agent.errors import (
    ERROR_CODES,
    ERROR_TYPES,
    AgentError,
    AuthFailedError,
    BackendUnavailableError,
    CapabilityUnsupportedError,
    ContextOverflowError,
    QuotaExceededError,
    RateLimitedError,
    SessionNotFoundError,
    ToolArgumentsError,
    TooManyAgentsError,
    UpstreamTimeoutError,
    default_message_for,
    project,
)
from apps.agent.pi.pool import PoolQueueTimeoutError
from apps.agent.pi.rpc_client import PiError, PiNotAvailableError
from apps.agent.sse_types import ErrorEvent

#: 已发布的 code 全表。**改这个集合等于改线路契约**：新增可以（同时让前端加
#: 映射），改已有条目的语义不行（见 ``errors.py`` 顶部的红线）。
_PUBLISHED_CODES = {
    "rate_limited",
    "quota_exceeded",
    "backend_unavailable",
    "capability_unsupported",
    "context_overflow",
    "upstream_timeout",
    "tool_args_invalid",
    "auth_failed",
    "session_not_found",
    "too_many_agents",
    "unknown",
}


def test_published_code_table_is_frozen() -> None:
    """code 全表逐字比对：新增/删除/改名都必须显式改这里。"""
    assert frozenset(_PUBLISHED_CODES) == ERROR_CODES


def test_every_error_type_has_unique_snake_case_code() -> None:
    """每个错误类一个唯一 code，且是 snake_case（前端要能直接当字典键）。"""
    codes = [cls.code for cls in ERROR_TYPES]
    assert len(codes) == len(set(codes)), f"code 有重复：{codes}"
    for cls in ERROR_TYPES:
        assert cls.code.islower(), f"{cls.__name__}.code 必须是小写：{cls.code}"
        assert " " not in cls.code and "-" not in cls.code, f"{cls.__name__}.code 必须是 snake_case：{cls.code}"
        assert cls.scope in {"account", "model", "request", "tool", "unknown"}
        assert cls.default_message, f"{cls.__name__} 缺兜底文案（前端拿不到 message 时会显示空白）"


def test_default_message_lookup_falls_back_to_generic() -> None:
    assert default_message_for("rate_limited") == RateLimitedError.default_message
    assert default_message_for("no_such_code") == AgentError.default_message


def test_typed_error_projects_code_scope_and_detail() -> None:
    """typed error 的上下文（哪个后端/模型/还能等几秒）原样进 detail。"""
    exc = RateLimitedError("网关限流", backend="pi", model="kimi-2.6", retry_after_seconds=60)

    frame = project(exc, agent="pi", run_id="s-1:pi:3")

    assert frame["type"] == "error"
    assert frame["code"] == "rate_limited"
    assert frame["scope"] == "account"
    # message 用类级文案（不再取 ``str(exc)``：抛错点可能把上游原文塞进构造参数）
    assert frame["message"] == "模型网关限流，请稍后重试"
    assert frame["detail"] == {"backend": "pi", "model": "kimi-2.6", "retry_after_seconds": 60}
    assert frame["agent"] == "pi"
    assert frame["run_id"] == "s-1:pi:3"


def test_every_typed_error_projects_its_own_code() -> None:
    """10 类 + 兜底：各自投影成自己的 code，不会互相串。"""
    cases: list[tuple[AgentError, str, str]] = [
        (RateLimitedError(), "rate_limited", "account"),
        (QuotaExceededError(), "quota_exceeded", "account"),
        (BackendUnavailableError(), "backend_unavailable", "model"),
        (CapabilityUnsupportedError(), "capability_unsupported", "request"),
        (ContextOverflowError(), "context_overflow", "request"),
        (UpstreamTimeoutError(), "upstream_timeout", "model"),
        (ToolArgumentsError(), "tool_args_invalid", "tool"),
        (AuthFailedError(), "auth_failed", "account"),
        (SessionNotFoundError(), "session_not_found", "request"),
        (TooManyAgentsError(), "too_many_agents", "request"),
        (AgentError(), "unknown", "unknown"),
    ]
    for exc, code, scope in cases:
        frame = project(exc)
        assert frame["code"] == code, exc
        assert frame["scope"] == scope, exc
        # 无参构造时用类自带的中文兜底文案，绝不把空串发给前端
        assert frame["message"] == exc.default_message


def test_detail_drops_empty_values() -> None:
    """空值不占位：``{"model": ""}`` 只会让前端多一次无意义判断。"""
    frame = project(RateLimitedError("限流", backend="pi", model="", retry_after_seconds=None))
    assert frame["detail"] == {"backend": "pi"}


def test_detail_is_redacted_and_truncated() -> None:
    """技术原文进 detail 前必须脱敏 + 截断。

    真实来源：上游错误页/网关回显里偶尔带厂商密钥串或 Authorization 头，而
    ``detail`` 会被前端渲染、也会被律师截图发到群里求助。
    """
    # 拼出来而不是写字面量：仓库的 detect-secrets 闸门按「形似密钥的串」匹配，
    # 而这里要测的正是「任意形似密钥的串都会被脱敏」。用无信息量的重复串既满足
    # 正则（`sk-` + 4 位以上），又不会让测试文件本身触发那道闸门。
    # 变量名刻意不叫 secret：仓库的 detect-secrets 会把「赋值给 secret/password/
    # token 之类名字的字符串」直接判成 Secret Keyword，与值本身无关。
    suspected = "sk-" + "x0" * 6
    frame = project(AgentError("失败", reason=f"bad key {suspected} " + "x" * 1000))

    reason = frame["detail"]["reason"]
    assert suspected not in reason
    assert "***" in reason
    assert len(reason) <= 240


def test_agent_and_run_id_omitted_when_unknown() -> None:
    """空 agent / run_id **不写键**：多答的 ``_tag`` 靠 ``setdefault`` 补栏。

    写成空串会让 ``tagged.setdefault("agent", kind)`` 变成 no-op，那一帧就永远
    没有 ``agent``——前端只能把它塞进错误的栏（或丢掉）。
    """
    frame = project(ValueError("boom"))
    assert "agent" not in frame
    assert "run_id" not in frame


def test_message_override_wins() -> None:
    """调用方知道更准确的说法时能覆盖文案，但 code 仍由异常决定。"""
    frame = project(PiError("429 too many requests"), message="流处理异常，请稍后重试")
    assert frame["message"] == "流处理异常，请稍后重试"
    assert frame["code"] == "rate_limited"


@pytest.mark.parametrize("kind", list(BackendErrorKind), ids=lambda k: k.value)
def test_backend_error_kind_maps_to_stable_code(kind: BackendErrorKind) -> None:
    """``BackendError``（dsh / openai-agents 的边界异常）按 kind 投影。

    这两个后端在边界处已经把 SDK 异常收敛成 ``BackendError``，编排层只看 kind
    就能给出「等一会儿」/「找管理员」的结论——不用再按具体异常类型分支。
    """
    frame = project(BackendError(kind, "底层原文", retryable=kind is BackendErrorKind.RATE_LIMITED))

    expected = {
        BackendErrorKind.UNAVAILABLE: ("backend_unavailable", "model"),
        BackendErrorKind.BUSY: ("quota_exceeded", "account"),
        BackendErrorKind.AUTH: ("auth_failed", "account"),
        BackendErrorKind.RATE_LIMITED: ("rate_limited", "account"),
        BackendErrorKind.CONTEXT_OVERFLOW: ("context_overflow", "request"),
        BackendErrorKind.UNKNOWN: ("unknown", "unknown"),
    }[kind]
    assert (frame["code"], frame["scope"]) == expected
    # 用户看到的是中文兜底文案；Go/SDK 的原话放 detail（magpie 的 detail 同款用法）
    assert frame["message"] == default_message_for(frame["code"])
    # 客户端只拿分类结论；异常原文不得出现在整帧任何字段（防 SSE 堆栈外泄）
    assert frame["detail"]["reason"] == "upstream_error"
    assert "底层原文" not in json.dumps(frame, ensure_ascii=False)
    assert frame["detail"]["retryable"] is (kind is BackendErrorKind.RATE_LIMITED)


def test_backend_error_retry_after_is_extracted() -> None:
    frame = project(BackendError(BackendErrorKind.RATE_LIMITED, "429 retry-after: 60"))
    assert frame["detail"]["retry_after_seconds"] == 60


def test_pi_not_available_is_backend_unavailable() -> None:
    """pi 不可用：code 让前端找管理员，文案逐字保留（集成测试也断言这一句）。"""
    frame = project(PiNotAvailableError("找不到 pi 可执行文件"), agent="pi")
    assert frame["code"] == "backend_unavailable"
    assert frame["scope"] == "model"
    assert frame["message"] == "pi 运行时不可用，请联系管理员（详见服务端日志）"
    assert frame["detail"]["reason"] == "pi_unavailable"
    assert "找不到 pi 可执行文件" not in json.dumps(frame, ensure_ascii=False)


def test_pool_queue_timeout_is_quota_exceeded() -> None:
    """排队超时是「忙」不是故障：code 指向配额，前端提示「稍后重试」。"""
    frame = project(PoolQueueTimeoutError("满了"))
    assert frame["code"] == "quota_exceeded"
    assert frame["scope"] == "account"
    assert frame["message"] == "当前使用人数较多，请稍后重试"
    assert frame["detail"]["limit"] == "agent_pool"


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("429 too many requests", "rate_limited"),
        # 429 的原文里常同时出现 timeout 的说明：先认限流，才不会把「等 60 秒」
        # 讲成「上游超时」（后者会让人以为要重发）。
        ("429 rate limited after timeout", "rate_limited"),
        ("401 unauthorized", "auth_failed"),
        ("maximum context length exceeded", "context_overflow"),
        ("connection timed out", "upstream_timeout"),
        ("child process exited with code 1", "unknown"),
    ],
)
def test_pi_error_message_classification(text: str, code: str) -> None:
    """``PiError`` 只能看消息（pi 把失败原因包成同一个类型），按优先级归类。"""
    frame = project(PiError(text))
    assert frame["code"] == code
    # reason 只记分类结论（异常原文只进 logger）
    assert frame["detail"]["reason"] == code
    assert text not in json.dumps(frame, ensure_ascii=False)


def test_pi_error_keeps_legacy_message_when_unclassified() -> None:
    frame = project(PiError("some weird failure"))
    assert frame["code"] == "unknown"
    assert frame["message"] == "pi 运行失败，请稍后重试（详见服务端日志）"


def test_lookup_error_is_capability_unsupported() -> None:
    """未知 agent kind（``get_backend`` 抛 ``LookupError``）→ 前端提示「换一栏」。"""
    frame = project(LookupError("unknown backend"), agent="nope")
    assert frame["code"] == "capability_unsupported"
    assert frame["scope"] == "request"
    assert frame["agent"] == "nope"


def test_unknown_exception_carries_exc_type_for_triage() -> None:
    frame = project(ValueError("boom"))
    assert frame["code"] == "unknown"
    assert frame["scope"] == "unknown"
    assert frame["detail"] == {"reason": "unclassified", "exc_type": "ValueError"}
    assert "boom" not in json.dumps(frame, ensure_ascii=False)


@pytest.mark.parametrize(
    "exc",
    [
        AgentError("x"),
        RateLimitedError("x"),
        BackendError(BackendErrorKind.BUSY, "x"),
        PiNotAvailableError("x"),
        PoolQueueTimeoutError("x"),
        PiError("x"),
        LookupError("x"),
        ValueError("x"),
    ],
    ids=lambda e: type(e).__name__,
)
def test_every_projection_validates_against_the_wire_contract(exc: BaseException) -> None:
    """投影结果必须能被 ``ErrorEvent`` 校验通过（契约与投影不能各写一套）。

    这是「同源」守卫：``code`` / ``scope`` / ``detail`` 的类型若在 ``sse_types``
    被改（比如 scope 改成枚举），这里会红，而不是等前端解析出 ``undefined``。
    """
    frame = project(exc, agent="pi", run_id="s-1:pi:1")
    event = ErrorEvent.model_validate(frame)
    assert event.code in ERROR_CODES or event.code == ""
    assert event.type == "error"
    assert '"code"' in event.model_dump_json()
