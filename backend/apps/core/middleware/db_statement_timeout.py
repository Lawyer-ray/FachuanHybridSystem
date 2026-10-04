"""请求级 PostgreSQL statement_timeout 中间件（web 防慢 SQL，不误伤 Django-Q worker）。

背景：``settings._pg_options`` 里的 statement_timeout 仅 DEBUG 注入。生产不能全局
开（Django-Q worker 与 web 共用 default alias，批量分析/OA 同步的长 SQL 会被杀），
因此改为请求级方案：本中间件在进入视图前对当前线程的 default 连接执行
``SELECT set_config('statement_timeout', '<N>', false)``，请求结束（含异常路径）后
在 finally 中重置为 0。

为什么必须严格 set/reset 配对：生产 CONN_MAX_AGE=600（连接按线程持久复用），
session 级参数会跨请求残留——若只 set 不 reset，后续复用该连接的任意请求（含
Django admin 导入导出、流式响应后的后续查询）都会继承本请求的超时值。

与 ``SET LOCAL`` 的取舍：ATOMIC_REQUESTS=False，请求默认不在事务里，autocommit
下 ``SET LOCAL`` 在其所在语句结束时立即失效，无法覆盖整个请求，故用 session 级
set_config + 显式 reset。

防误伤 Django-Q worker：worker 由 ``manage.py qcluster`` 进程运行任务函数，
不经过 WSGI/ASGI 的中间件栈，本模块对其完全不可见；worker 连接的
statement_timeout 保持连接级默认（生产不注入）。

仅 sync 中间件（async_capable=False）：DB 写操作走 psycopg 同步协议。ASGI 下
Django 用 ``sync_to_async(thread_sensitive=True)`` 包装本中间件，与视图内
thread-sensitive 的 ORM 调用共享同一执行线程——thread-local 的
``django.db.connection`` 因此是同一个连接对象，set/reset 与视图查询严格落在
同一连接上，不存在连接错配。Django 在 async 链中会自动给 sync 中间件传入
sync 化的 get_response（async_to_sync 适配），__call__ 无需感知 async。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any, Final

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)

ENV_NAME: Final[str] = "DB_WEB_STATEMENT_TIMEOUT_MS"
# 默认 60s：依据 web 端最重的合法同步 SQL（admin「导出全部」的全表 JOIN COUNT +
# prefetch 主查询、合同列表 Sum/子查询 annotate、全局搜索 6 表 icontains LIKE 扫描）
# 当前数据量（contracts/cases 百行级、inbox/court_sms 数百行）下均为亚秒级单条语句，
# 60s 提供 2-3 个数量级余量；生产若出现合法长语句，调 env 即可，无需改代码。
DEFAULT_WEB_STATEMENT_TIMEOUT_MS: Final[int] = 60_000

# set_config 第三参 is_local=false → session 级（跨语句、跨事务生效），与 reset 配对。
_SET_SQL: Final[str] = "SELECT set_config('statement_timeout', %s, false)"
_RESET_SQL: Final[str] = "SELECT set_config('statement_timeout', '0', false)"


def _resolve_timeout_ms() -> int:
    """解析环境变量 DB_WEB_STATEMENT_TIMEOUT_MS；非法值回退默认并告警。"""
    raw = (os.environ.get(ENV_NAME, "") or "").strip()
    if not raw:
        return DEFAULT_WEB_STATEMENT_TIMEOUT_MS
    try:
        return int(raw)
    except ValueError:
        logger.warning("环境变量 %s=%r 不是合法整数，回退默认 %d ms", ENV_NAME, raw, DEFAULT_WEB_STATEMENT_TIMEOUT_MS)
        return DEFAULT_WEB_STATEMENT_TIMEOUT_MS


class DbStatementTimeoutMiddleware:
    """为每个 web 请求设置/重置 PostgreSQL statement_timeout。

    生效条件（三者同时满足，缺一跳过且不产生任何 SQL）：
    - settings.DEBUG 为 False（DEBUG 已由连接 options 全局注入，避免 reset 抹掉它）
    - default 连接 vendor 为 postgresql（sqlite/mysql 环境跳过）
    - 超时值 > 0（DB_WEB_STATEMENT_TIMEOUT_MS=0 可作为线上快速关闭开关）

    流式响应（SSE/StreamingHttpResponse）说明：finally 在响应对象返回时执行 reset，
    流式生成器在响应阶段之后执行的后继查询不受保护（与现状一致，无破坏）。
    """

    sync_capable = True
    async_capable = False

    timeout_ms: int
    get_response: Callable[..., Any]

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.timeout_ms = _resolve_timeout_ms()

    def __call__(self, request: HttpRequest) -> Any:
        if not self._should_apply():
            return self.get_response(request)
        if not self._apply():
            # SET 失败（连接异常等）：不 reset（未生效就无所谓残留），请求照常放行。
            return self.get_response(request)
        try:
            return self.get_response(request)
        finally:
            self._reset()

    def _should_apply(self) -> bool:
        if settings.DEBUG:
            return False
        if connection.vendor != "postgresql":
            return False
        return self.timeout_ms > 0

    def _apply(self) -> bool:
        try:
            with connection.cursor() as cursor:
                cursor.execute(_SET_SQL, [str(self.timeout_ms)])
        except Exception:
            logger.exception("设置 statement_timeout 失败，本请求跳过请求级保护")
            return False
        return True

    def _reset(self) -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute(_RESET_SQL)
        except Exception:
            # 连接已断开时 reset 失败是安全的：会话参数随连接关闭一起消失，
            # 不存在跨请求残留；仅记录日志便于排查。
            logger.warning("重置 statement_timeout 失败（连接可能已断开，无残留风险）", exc_info=True)
