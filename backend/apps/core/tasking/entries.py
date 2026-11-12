"""Module for entries."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from typing import Any, cast

from .context import TaskContext, set_current_request_id

logger = logging.getLogger("apps.core.tasking")

# 单个字段在单行日志里的最大长度（console 一眼能看完，不刷屏）
_LOG_MESSAGE_MAX = 300

# 可预期的外部环境异常：只落一行 WARNING 摘要，不刷整段 traceback。
#
# 背景：定时同步类任务（IMAP 收件箱、法院一张网抓取等）在断网 / 对方主机
# 解析失败 / 自己手滑填错域名时必然失败，且每轮轮询都会重来一次。这类失败
# 不是「系统出 bug」，只是「外部依赖当前不可用」，打全栈只会让终端看起来像
# 系统崩了，并把真正的代码缺陷埋掉。完整 traceback 仍然可以通过
# ``logger.debug("task_failed_detail", exc_info=True)`` 打开（DEBUG 级）。
_EXPECTED_ERROR_TYPES: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    ConnectionAbortedError,
)

_EXPECTED_MESSAGE_TOKENS: tuple[str, ...] = (
    "name or service not known",
    "nodename nor servname provided",
    "temporary failure in name resolution",
    "connection refused",
    "connection reset",
    "network is unreachable",
    "no route to host",
    "temporarily unavailable",
    "err_internet_disconnected",
    "err_name_not_resolved",
    "err_connection_refused",
    "err_connection_timed_out",
    "timed out",
    "timeout",
    "cannot switch to a different thread",  # Playwright Sync API 跨线程 greenlet
    "sync api inside the asyncio loop",  # Playwright Sync API 在 asyncio 中误用
    "target closed",
    "browser has been closed",
)


def _is_expected_task_error(exc: BaseException) -> bool:
    """判断是否为可预期的外部环境异常（网络不可达 / 主机解析失败 / 超时等）。"""
    if isinstance(exc, _EXPECTED_ERROR_TYPES):
        return True
    # socket.gaierror 是 OSError 子类，按需导入避免模块级 socket 依赖
    import socket

    if isinstance(exc, socket.gaierror):
        return True

    message = str(exc).lower()
    return any(token in message for token in _EXPECTED_MESSAGE_TOKENS)


def _shorten(value: Any, *, limit: int = _LOG_MESSAGE_MAX) -> str:
    """把异常消息压成单行摘要，超长截断。"""
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…（共 {len(text)} 字符）"


def _log_task_failure(target: str, task_ctx: TaskContext, exc: Exception) -> None:
    """统一处理任务失败日志：可预期故障降噪为单行，真缺陷保留完整栈。"""
    extra = {
        "target": target,
        "task_name": task_ctx.task_name,
        "entity_id": task_ctx.entity_id,
        "correlation_id": task_ctx.correlation_id,
        "error_type": type(exc).__name__,
        "error": _shorten(exc),
        **(task_ctx.extra or {}),
    }

    if _is_expected_task_error(exc):
        # 外部依赖不可用：一行摘要即可，堆栈降级到 DEBUG
        logger.warning("任务因外部环境失败（可重试）: %s -> %s", target, _shorten(exc), extra=extra)
        logger.debug("task_failed_detail", extra=extra, exc_info=exc)
        return

    logger.error("task_failed: %s -> %s", target, _shorten(exc), extra=extra, exc_info=True)


def _report_task_key(task_name: str | None, fallback: str) -> str:
    """把 django-q 的随机 task_name（如 finch-asparagus-indigo-montana）换成可读任务名。"""
    return task_name if task_name else fallback


def _import_callable(dotted_path: str) -> Callable[..., Any]:
    module_path, attr = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return cast(Callable[..., Any], getattr(module, attr))


def run_task(
    target: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> Any:
    task_ctx = TaskContext.from_dict(context)
    request_id = task_ctx.request_id or task_ctx.correlation_id
    set_current_request_id(request_id)

    # 设置 task_name 到 ContextVar，供日志和 Sentry 追踪
    if task_ctx.task_name:
        from apps.core.infrastructure.request_context import set_request_context

        set_request_context(task_name=task_ctx.task_name)

    fn = _import_callable(target)
    try:
        return fn(*(args or []), **(kwargs or {}))
    except Exception as e:
        _log_task_failure(target, task_ctx, e)
        raise
