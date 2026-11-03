"""复现：DB_POOL + sync_to_async(thread_sensitive=False) 导致的连接池泄漏。

背景（2026-11-03 事故）：
    /api/v1/oa-filing/session/105 每 2s 轮询一次，单请求只做一条 SELECT，
    却报 `PoolTimeout: couldn't get a connection after 10.00 sec`。
    现场 pg_stat_activity 有 44 条 idle 连接（非 idle in transaction），
    且按 08:27→09:56→11:26→12:56→13:56 的节奏在数小时内单调增长。

机理：
    1. Django 的 `connections` 是 thread_critical=True 的线程局部对象，
       每条线程各持一份 BaseDatabaseWrapper。
    2. 开启 OPTIONS["pool"] 后，CONN_MAX_AGE 被强制成 0，连接生命周期交给
       psycopg_pool；但「归还」只发生在该线程的 `close()` 里
       （postgresql/base.py::_close → pool.putconn），而 close 由
       request_finished 信号在**请求线程**触发。
    3. sync_to_async(thread_sensitive=False) 让 ORM 落到 anyio 默认线程池
       （每次调度可能是任意 worker 线程），连接借出发生在 worker 线程 W，
       而请求收尾的 close 发生在事件循环线程 / 另一个 worker —— W 上那份
       wrapper 的 connection 永远不会被归还，池里被永久借走一条。
    4. 线程池 worker 会随负载扩展并长期存活（空闲回收阈值以上才退出），
       于是「每条新 worker 线程 ≈ 永久泄漏 1 条连接」，增长速率与轮询频率
       / 并发量正相关，与单请求的 SQL 数量无关，所以看着像随机超时。

运行（不要连 fachuan_dev，连测试库名的库即可，本脚本只跑 SELECT 1）：
    DB_NAME=<任意可连接的库> .venv/bin/python devtools/repro_pool_leak.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# Django 的 LOGGING 配置会接管 root logger，basicConfig 会被覆盖，
# 所以自己的 logger 显式挂 handler 并关掉 propagate。
logger = logging.getLogger("repro_pool_leak")
logger.setLevel(logging.INFO)
logger.propagate = False
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_handler)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.apiSystem.settings")
os.environ.setdefault("DB_POOL", "true")
os.environ.setdefault("DB_POOL_MAX", "4")  # 池故意调小，快速触发池满
os.environ.setdefault("DEBUG", "true")

import django

django.setup()

from asgiref.sync import sync_to_async
from django.db import connections


def _one_query() -> int:
    """模拟 get_session：单条轻量 SELECT。"""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT 1")
        return int(cur.fetchone()[0])


def _pool_stats() -> str:
    """读取 psycopg_pool 的内部计数（Django 6.1 把池挂在 wrapper.pool 上）。"""
    conn = connections["default"]
    pool = getattr(conn, "pool", None)
    if pool is None:
        return "pool=<未启用>"
    st = pool.get_stats()
    return (
        f"pool_size={st.get('pool_size')} pool_available={st.get('pool_available')} "
        f"requests_waiting={st.get('requests_waiting')}"
    )


async def _hammer(n_concurrent: int, use_thread_sensitive: bool) -> None:
    logger.info("\n=== thread_sensitive=%s, 并发=%s ===", use_thread_sensitive, n_concurrent)

    async def task(i: int) -> None:
        try:
            await sync_to_async(_one_query, thread_sensitive=use_thread_sensitive)()
        finally:
            # 模拟真实请求收尾：request_finished 信号在**事件循环线程**上关闭连接。
            # 这正是 thread_sensitive=False 下「借出线程 ≠ 归还线程」的现场。
            from asgiref.sync import sync_to_async as _s2a

            await _s2a(connections.close_all, thread_sensitive=True)()

    # 分两批：第一批逼线程池扩容，第二批看连接是否已被借光
    for wave in range(2):
        try:
            await asyncio.gather(*(task(i) for i in range(n_concurrent)))
        except Exception as exc:
            logger.info("  第 %s 批失败：%s: %s", wave + 1, type(exc).__name__, exc)
            logger.info("  %s", _pool_stats())
            return
        logger.info("  第 %s 批成功  %s", wave + 1, _pool_stats())


def main() -> int:
    logger.info(
        "DEBUG=%s DB_POOL=%s DB_POOL_MAX=%s",
        os.environ.get("DEBUG"),
        os.environ.get("DB_POOL"),
        os.environ.get("DB_POOL_MAX"),
    )
    conn = connections["default"]
    logger.info(
        "CONN_MAX_AGE=%s  OPTIONS.pool=%s",
        conn.settings_dict["CONN_MAX_AGE"],
        conn.settings_dict["OPTIONS"].get("pool"),
    )

    # 对照组：thread_sensitive=True —— 所有 ORM 复用同一个单线程执行器，
    # 每条线程最多一条连接，且该线程的 close 能归还到池，不应耗尽。
    asyncio.run(_hammer(n_concurrent=8, use_thread_sensitive=True))

    # 实验组：thread_sensitive=False —— ORM 落到 anyio 默认线程池，
    # 连接借出在 worker 线程、归还却发生在别处，池被逐步借空。
    asyncio.run(_hammer(n_concurrent=8, use_thread_sensitive=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
