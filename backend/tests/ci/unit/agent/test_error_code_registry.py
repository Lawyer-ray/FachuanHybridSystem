"""``error`` 事件的 code 登记表：每个 code 都必须带**可执行**的 ``detail``。

## 为什么需要这条守卫

``test_agent_error_codes`` 已经把「异常 → code/scope」钉住了，但它守不住一件更
隐蔽的事：**这个 code 有没有给出「人能拿去修」的参数**。

真实退化路径：新增一个 code（比如「对比席位满」），只写了文案和 scope 就上线。
前端拿到 ``{"code": "x", "scope": "request"}`` 只能显示一句话，律师看完仍然不知道
该做什么——而同一个错误如果带上 ``{"max": 4, "requested": 6}``，前端能直接提示
「最多 4 栏，你选了 6 栏」。**错误没变少，只是变得好像坏了。**

所以本文件守三件事：

1. 每个已发布的 ``code`` 都在 :data:`apps.agent.errors.ERROR_DETAIL_KEYS` 里登记
   （空集 = 显式声明无需 detail，不是漏填）；
2. 每条**真实投影路径**产出的 ``detail`` 至少命中该 code 的一个登记键；
3. 仓库里没有第二处手写 ``{"type": "error"}``——那是最容易长出「同一件事两个
   code」的口子（本次收口前，pi 与 dsh 各手写了一份）。
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from apps.agent.backends.base import BackendError, BackendErrorKind
from apps.agent.errors import (
    ERROR_CODES,
    ERROR_DETAIL_KEYS,
    AuthFailedError,
    CapabilityUnsupportedError,
    ContextOverflowError,
    QuotaExceededError,
    RateLimitedError,
    SessionNotFoundError,
    TooManyAgentsError,
    UpstreamTimeoutError,
    project,
    project_message,
)
from apps.agent.pi.pool import PoolQueueTimeoutError
from apps.agent.pi.rpc_client import PiError, PiNotAvailableError
from apps.agent.sse_types import ErrorEvent

#: ``backend/apps/agent``（本文件在 backend/tests/ci/unit/agent/，上推 4 层到 backend）
_AGENT_ROOT = Path(__file__).resolve().parents[4] / "apps" / "agent"

#: 允许出现 ``"type": "error"`` 字面量的唯一文件（投影的唯一出口）。
_PROJECTION_HOME = "errors.py"


def _wire_emitters() -> Iterator[tuple[str, dict[str, Any]]]:
    """仓库里**每一条**真实会发出 ``error`` 帧的路径。

    这是全表审计的可执行版本：加新的发射点就加一行，否则「这条路径的 detail 够
    不够用」永远没人验证。每条的名字进 ``pytest`` 的用例 id，红的时候一眼知道
    是哪条路径退化了。
    """
    yield "typed.rate_limited", project(RateLimitedError(backend="pi", model="kimi", retry_after_seconds=60))
    yield "typed.quota_exceeded", project(QuotaExceededError(reason="池子满了", limit="agent_pool"))
    yield "typed.auth_failed", project(AuthFailedError(reason="user 被停用"))
    yield "typed.context_overflow", project(ContextOverflowError(reason="window 128k"))
    yield "typed.upstream_timeout", project(UpstreamTimeoutError(reason="12s 未响应"))
    yield "typed.capability_unsupported", project(CapabilityUnsupportedError(reason="unknown backend 'dsh2'"))
    yield (
        "api.session_not_found",
        project(SessionNotFoundError(session_id="s-1234")),
    )
    yield (
        "api.too_many_agents",
        project(TooManyAgentsError("太多栏", requested=6, max=4)),
    )
    yield "backend.unavailable", project(BackendError(BackendErrorKind.UNAVAILABLE, "gateway 未配置"))
    yield "backend.busy", project(BackendError(BackendErrorKind.BUSY, "池子满"))
    yield "backend.auth", project(BackendError(BackendErrorKind.AUTH, "401"))
    yield "backend.rate_limited", project(BackendError(BackendErrorKind.RATE_LIMITED, "429 retry-after: 60"))
    yield "backend.context_overflow", project(BackendError(BackendErrorKind.CONTEXT_OVERFLOW, "too many tokens"))
    yield "backend.unknown", project(BackendError(BackendErrorKind.UNKNOWN, "SDK 内部错误"))
    yield "pi.not_available", project(PiNotAvailableError("找不到可执行文件"))
    yield "pi.queue_timeout", project(PoolQueueTimeoutError("排队 30s 超时"))
    yield "pi.error_unclassified", project(PiError("child process exited with code 1"))
    yield "pi.error_rate_limited", project(PiError("429 too many requests, retry-after: 30"))
    yield "lookup.unknown_backend", project(LookupError("unknown backend 'x'"))
    yield "fallback.unexpected", project(ValueError("boom"))
    # 上游只给一句话的两条路径（pi 的 error 事件 / dsh 的 turn/end 失败）
    yield "upstream.message_classified", project_message("上游 429", agent="dsh")
    yield "upstream.message_silent", project_message("", agent="pi")


@pytest.mark.parametrize(("name", "frame"), list(_wire_emitters()), ids=[n for n, _ in _wire_emitters()])
def test_every_emitter_carries_actionable_detail(name: str, frame: dict[str, Any]) -> None:
    """每条真实发射路径的 ``detail`` 必须命中该 code 登记的键之一。"""
    code = frame["code"]
    assert code in ERROR_CODES, f"{name} 发出了一个未登记的 code：{code}"

    required = ERROR_DETAIL_KEYS[code]
    if not required:
        # 显式声明「无需 detail」的 code：detail 可以为空，但必须**声明过**。
        assert code in ERROR_DETAIL_KEYS
        return

    keys = set(frame["detail"])
    assert keys & required, (
        f"{name} 的 detail={sorted(keys)} 没有给出 {sorted(required)} 中任何一个——"
        "前端只能把律师退回「未知错误」，错误仍然没被修好。"
    )


def test_every_published_code_is_registered() -> None:
    """登记表与 code 全表必须一一对应（少登记 / 残留旧键都不行）。"""
    assert set(ERROR_DETAIL_KEYS) == ERROR_CODES, (
        "ERROR_DETAIL_KEYS 与 ERROR_CODES 不一致：新增 code 时请同时登记它「人能拿去修」"
        "的 detail 键（或显式写空集合表示无需 detail）。"
    )


def test_registered_keys_are_declared_in_the_wire_contract() -> None:
    """``detail`` 是自由 dict，但登记键必须是能真的出现在帧里的字符串键。"""
    for code, keys in ERROR_DETAIL_KEYS.items():
        for key in keys:
            assert isinstance(key, str) and key and " " not in key, f"{code} 的 detail 键不合法：{key!r}"


def test_frames_validate_against_the_wire_contract() -> None:
    """登记表里的每条路径产出的帧都要能被 ``ErrorEvent`` 校验通过。"""
    for name, frame in _wire_emitters():
        event = ErrorEvent.model_validate({**frame, "run_id": "s-1:pi:1"})
        assert event.type == "error", name
        assert event.code in ERROR_CODES, name


def _error_frame_dicts(path: Path) -> int:
    """统计一个文件里**真正构造出来的** ``{"type": "error", ...}`` 字面量个数。

    用 ``ast`` 而不是文本搜索：docstring / 注释里引用这个形状是为了解释「不要
    这么写」（``errors.py`` 与 ``stream.py`` 的开头都写了），文本匹配会把它们
    当成违规——一条永远红的守卫等于没有守卫。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        pairs = {
            key.value: value.value
            for key, value in zip(node.keys, node.values, strict=False)
            if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)
        }
        if pairs.get("type") == "error":
            count += 1
    return count


def test_no_handwritten_error_frames_outside_errors_module() -> None:
    """仓库里只允许 ``errors.py`` 一个出口写 ``{"type": "error"}``。

    这条断言是本次收口的**防复发**闸门：收口前 ``pi/bridge.py`` 与
    ``backends/dsh_backend.py`` 各自手写了一份 ``{"type": "error", "message": ...}``
    ——于是同一个 429 在编排层叫 ``rate_limited``（提示「等 60 秒」），在这两条
    路径上却是一个没有 code 的裸帧（前端归到「未知错误」）。同一件事两个结论。
    """
    offenders: list[str] = []
    for path in sorted(_AGENT_ROOT.rglob("*.py")):
        if path.name == _PROJECTION_HOME:
            continue
        if _error_frame_dicts(path):
            offenders.append(str(path.relative_to(_AGENT_ROOT)))

    assert offenders == [], (
        f"这些文件手写了 error 帧：{offenders}。请改用 apps.agent.errors.project（或 "
        "project_message 处理「上游只给一句话」的场景），否则该路径的错误在前端没有 code。"
    )
