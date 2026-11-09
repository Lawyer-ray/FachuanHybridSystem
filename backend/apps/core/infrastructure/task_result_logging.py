"""django-q monitor 日志降噪过滤器。

django-q 的 monitor 进程（``django_q/monitor.py``）在任务失败时会把
``task["result"]`` 原样塞进日志消息，而这个 result 是完整的 Python traceback，
再被本项目的 ``logger.exception`` 附加一次栈——同一份堆栈在终端里出现 **两遍**，
且每轮轮询重复一次，长这样：

    ERROR - 'apps.core.tasking.entries.run_task' (finch-asparagus-indigo-montana) 失败 - IMAP 连接失败... : Traceback (most recent call last):
      File ".../imaplib.py", line 1315, in __init__
      ...（40+ 行）

本过滤器把这条日志压成一行摘要：

    WARN - 任务失败（外部环境不可用，可重试）: IMAP 主机无法解析: message_hub.sync_source_by_id -> IMAP 连接失败（已尝试: ...）

- 消息里以 ``Traceback (most recent call last):`` 开头的那截 traceback 整体剥离，
  只保留 ``<异常类型>: <异常摘要>``；
- 可预期的外部环境异常（断网 / DNS 解析失败 / 超时 / 连接被拒）降级为 WARNING，
  真代码缺陷保持 ERROR；
- 末尾的随机任务名（django-q 随机生成，如 ``finch-asparagus-indigo-montana``）替换为
  可读的任务名（能对齐到已注册的 Schedule 时），否则保留原样。
"""

from __future__ import annotations

import logging
import re

# django-q 随机 task_name 的形态：2~4 个纯小写英文单词用 '-' 连接
_RANDOM_TASK_NAME = re.compile(r"^[a-z]{3,12}(?:-[a-z]{3,12}){1,4}$")

# django-q 失败日志：'<func>' (<task_name>) 失败 - <result>
# 只切「失败 - 之前的那个 (<task_name>)」：消息体里满是括号（「（已尝试: a, b）」），
# 按引号切也会被消息里的引号带偏，所以锚定到 "失败 - " 再向前找。
_FAILED_LOG = re.compile(r"(?P<name>\([^()]*\))\s*失败 - (?P<tail>.*)$", re.DOTALL)

# 从 django-q 的 func 表示里取出 dotted path（'a.b.c' 或 <function a at 0x..>）
_FUNC_PATH = re.compile(r"'([\w.]+)'")

# result 里 traceback 段之后只剩异常末行：直接砍掉 traceback 段
_TRACEBACK_START = "Traceback (most recent call last):"

_EXPECTED_TOKENS: tuple[str, ...] = (
    "name or service not known",
    "nodename nor servname provided",
    "temporary failure in name resolution",
    "connection refused",
    "connection reset",
    "network is unreachable",
    "no route to host",
    "temporarily unavailable",
    "err_internet_disconnected",
    "timeout",
    "timed out",
    "target closed",
    "browser has been closed",
    "cannot switch to a different thread",
    "sync api inside the asyncio loop",
)

_TAIL_MESSAGE_MAX = 200


def _strip_traceback(text: str) -> str:
    """只保留 traceback 之后的最后一行（``异常类型: 摘要``）。"""
    if _TRACEBACK_START not in text:
        return text
    tail = text.rsplit(_TRACEBACK_START, 1)[-1]
    # 末行即 "<ExceptionType>: <msg>"，其后可能还跟着一段 "The above exception was..." 链
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    if not lines:
        return text.split(_TRACEBACK_START, 1)[0].strip()
    return lines[-1]


def _shorten(text: str, limit: int = _TAIL_MESSAGE_MAX) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[:limit]}…"


def _is_expected(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in _EXPECTED_TOKENS)


def _resolve_readable_task_name() -> str | None:
    """取当前任务的业务名（来自 request_context），拿不到就返回 None。"""
    try:
        from apps.core.infrastructure.request_context import get_task_name

        local = (get_task_name() or "").strip()
    except Exception:  # pragma: no cover - 上下文不可用时静默降级
        return None
    # 随机名不是业务名，当没有处理
    if not local or _RANDOM_TASK_NAME.match(local):
        return None
    return local


class TaskResultLogFilter(logging.Filter):
    """把 django-q monitor 的整段 traceback 失败日志压成单行。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.msg, str) or "失败 - " not in record.msg:
            return True

        original = record.msg
        try:
            record.msg = self._compact(original)
        except Exception:  # pragma: no cover - 任何解析异常都不应吞日志
            record.msg = original
            return True

        # 已经压成摘要，就不再让 Formatter 再吐一遍完整栈
        record.exc_info = None
        record.exc_text = None

        compacted = str(record.msg)
        if _is_expected(compacted):
            record.levelno = logging.WARNING
            record.levelname = "WARNING"
        return True

    @staticmethod
    def _compact(message: str) -> str:
        match = _FAILED_LOG.search(message)
        name = (match.group("name") if match else "").strip("() ")
        tail = match.group("tail") if match else message
        head = message[: match.start()] if match else ""
        func_match = _FUNC_PATH.search(head)
        func = func_match.group(1) if func_match else head.strip()

        tail = tail.replace("失败 - ", "", 1)
        tail = _strip_traceback(tail)
        tail = _shorten(tail)

        readable = _resolve_readable_task_name()
        # 优先级：业务任务名 > django-q 的具名 task_name > 函数路径 > 原消息
        if readable:
            label = readable
        elif name and not _RANDOM_TASK_NAME.match(name):
            label = name
        else:
            label = func or "未知任务"

        state = "外部环境不可用，可重试" if _is_expected(tail) else "需要排查"
        return f"任务失败（{state}）: {label} -> {tail}"
